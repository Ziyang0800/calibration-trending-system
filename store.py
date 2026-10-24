"""
store.py - Local storage, setup configuration, and safe midnight network sync.
"""

import json
import logging
import os
import shutil
import sqlite3
import sys
import threading
import time
import socket
import uuid
import re
from datetime import datetime, date
from pathlib import Path

# Default shared network path (can be customized in setup.json)
DEFAULT_NETWORK_DB_PATH = r"\\romulus\v4\PGLab\Callab\Database\calibration.db"


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def data_dir():
    root = os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / "CalibrationSystem"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=Path(path).parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(obj, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def get_local_db_path():
    """Strictly locks to the real calibration.db in the WelcomeScreen project root."""
    configured = os.environ.get("CALIBRATION_LOCAL_DB")
    if configured:
        return str(Path(configured).expanduser().resolve())
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    project_db = base / "calibration.db"
    if project_db.exists():
        print(f"--> [DATABASE ACTIVE]: {project_db}")
        return str(project_db)

    # Fallback to APPDATA only if running as a frozen PyInstaller exe
    d = data_dir()
    fallback_db = d / "calibration.db"
    print(f"--> [DATABASE APPDATA FALLBACK]: {fallback_db}")
    return str(fallback_db)


class DatabaseSyncManager:
    """Manages automatic midnight backups and manual syncs to the shared network drive."""

    def __init__(self, setup_config):
        self.setup = setup_config
        self.lock = threading.Lock()
        self.last_sync = None
        self.last_status = "Not synced yet"
        self.is_syncing = False
        threading.Thread(target=self._midnight_daemon, daemon=True).start()

    def get_network_path(self):
        p = os.environ.get("CALIBRATION_NETWORK_DB") or self.setup.get("network_db_path") or DEFAULT_NETWORK_DB_PATH
        return str(p).strip()

    def sync_now(self):
        """Performs an online SQLite backup and always releases connections/lock state."""
        with self.lock:
            if self.is_syncing:
                return {"ok": False, "message": "Sync already in progress"}
            self.is_syncing = True

        src_conn = None
        dst_conn = None
        try:
            net_path = self.get_network_path()
            local_path = get_local_db_path()
            destination = Path(net_path)
            if Path(local_path).resolve() == destination.resolve():
                raise ValueError("The backup target must differ from the active database.")
            # Each workstation/run owns a unique snapshot; never replace a shared database.
            backup_root = destination.parent / (destination.stem + "_backups")
            host = re.sub(r"[^A-Za-z0-9_-]", "_", socket.gethostname())
            run_name = f"{datetime.now():%Y%m%d_%H%M%S}_{host[:16]}_{uuid.uuid4().hex[:8]}"
            staging = backup_root / (run_name + ".partial")
            staging.mkdir(parents=True, exist_ok=False)
            snapshot = staging / "calibration.db"
            src_conn = sqlite3.connect(Path(local_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30.0)
            dst_conn = sqlite3.connect(str(snapshot), timeout=30.0)
            src_conn.backup(dst_conn, pages=100)
            if dst_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed integrity validation.")
            documents = set()
            for column in ("cert_pdf_path", "reviewer_attachment_path"):
                documents.update(r[0] for r in dst_conn.execute(f"SELECT {column} FROM calibrations WHERE {column} IS NOT NULL") if r[0])
            manifest = {"source": local_path, "documents": {}, "missing_documents": []}
            import hashlib
            for document in sorted(documents):
                source = Path(document)
                if not source.is_file():
                    manifest["missing_documents"].append(document)
                    continue
                payload = source.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                relative = Path("documents") / (f"{len(manifest['documents']):06d}" + source.suffix.lower())
                target = staging / relative
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(payload)
                manifest["documents"][document] = {"path": relative.as_posix(), "sha256": digest}
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            dst_conn.close()
            dst_conn = None
            src_conn.close()
            src_conn = None
            completed = backup_root / run_name
            staging.rename(completed)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_sync = now_str
            self.last_status = f"Backup completed at {now_str}"
            logging.info("Network snapshot completed: %s", completed)
            return {"ok": True, "time": now_str, "target": str(completed),
                    "missing_documents": manifest["missing_documents"]}
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            self.last_status = f"Sync failed: {err_msg}"
            logging.error("Network DB sync failed: %s", err_msg)
            return {"ok": False, "error": err_msg}
        finally:
            for connection in (dst_conn, src_conn):
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        logging.exception("Failed to close a database sync connection")
            with self.lock:
                self.is_syncing = False

    def _midnight_daemon(self):
        """Monitors clock and triggers automatic backup exactly at midnight (00:00)."""
        last_synced_date = None
        while True:
            time.sleep(30)
            now = datetime.now()
            # If it is between 00:00 and 00:05 and hasn't synced today
            if now.hour == 0 and now.minute < 5 and last_synced_date != now.date():
                logging.info("Triggering scheduled midnight database sync...")
                res = self.sync_now()
                if res.get("ok"):
                    last_synced_date = now.date()
