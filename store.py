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
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def get_local_db_path():
    d = data_dir()
    db_file = d / "calibration.db"
    # If not present in APPDATA yet, copy from current directory if available
    if not db_file.exists():
        src = Path("calibration.db")
        if src.exists():
            shutil.copy(src, db_file)
    return str(db_file)


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
        """Performs an atomic online SQLite backup to the network drive."""
        with self.lock:
            if self.is_syncing:
                return {"ok": False, "message": "Sync already in progress"}
            self.is_syncing = True

        net_path = self.get_network_path()
        local_path = get_local_db_path()

        try:
            net_dir = Path(net_path).parent
            net_dir.mkdir(parents=True, exist_ok=True)

            # Atomic Online SQLite Backup API
            src_conn = sqlite3.connect(local_path)
            dst_conn = sqlite3.connect(net_path)
            with dst_conn:
                src_conn.backup(dst_conn, pages=100)
            dst_conn.close()
            src_conn.close()

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_sync = now_str
            self.last_status = f"Synced successfully at {now_str}"
            logging.info("Network DB sync completed successfully to %s", net_path)
            return {"ok": True, "time": now_str, "target": net_path}
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            self.last_status = f"Sync failed: {err_msg}"
            logging.error("Network DB sync failed: %s", err_msg)
            return {"ok": False, "error": err_msg}
        finally:
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