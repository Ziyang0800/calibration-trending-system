"""mars_sync.py - keep a local SQLite table of equipment in step with MARS.

* Your equipment IDs live in the table `ete_status` (column Equipment_ID).
* sync_all() asks MARS about every ID and updates that row.
* DailySync runs it when the app starts, and again once per new day
  while the app stays open (a background thread, so the UI never freezes).

Needs mars_client.py in the same folder.
"""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, time as dtime

import requests

from mars_client import MarsClient, FIELDS

# ---------------------------------------------------------------- settings
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ete.db")
TABLE = "ete_status"

SYNC_AFTER = dtime(7, 0)       # on a new day, do not sync before 07:00
CHECK_EVERY_SECONDS = 600      # the open app checks "is a new day?" every 10 min

# FIELDS (from mars_client.py) become real columns you can query.
# The full MARS record is also kept as text in raw_json.
COLUMNS = [
    f for f in FIELDS
    if f != "Equipment_ID" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", f)
]
EXTRA = ["raw_json", "last_synced_at", "sync_error"]


# ---------------------------------------------------------------- database
def connect():
    """Open a NEW connection. Every thread must use its own connection."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema(conn):
    """Create the tables if missing and add any missing columns."""
    conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (Equipment_ID TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    have = {r["name"] for r in conn.execute(f"PRAGMA table_info({TABLE})")}
    for col in COLUMNS + EXTRA:
        if col not in have:
            conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN "{col}" TEXT')
    conn.commit()


def add_ids(conn, ids):
    """Add equipment IDs to follow (existing ones are left alone)."""
    conn.executemany(
        f"INSERT OR IGNORE INTO {TABLE} (Equipment_ID) VALUES (?)",
        [(i.strip(),) for i in ids if i.strip()],
    )
    conn.commit()


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


# ---------------------------------------------------------------- the sync
def _text(value):
    return None if value is None else str(value)


def sync_all(client, conn, progress=None):
    """Update every ID in the table from MARS. Returns a summary dict."""
    ids = [r["Equipment_ID"] for r in conn.execute(
        f"SELECT Equipment_ID FROM {TABLE} ORDER BY Equipment_ID")]
    now = datetime.now().isoformat(timespec="seconds")
    ok, failed, aborted = 0, 0, None

    set_cols = ", ".join(f'"{c}" = ?' for c in COLUMNS + ["raw_json", "last_synced_at"])
    sql_ok = f"UPDATE {TABLE} SET {set_cols}, sync_error = NULL WHERE Equipment_ID = ?"
    sql_err = f"UPDATE {TABLE} SET sync_error = ? WHERE Equipment_ID = ?"

    for n, eid in enumerate(ids, start=1):
        try:
            records = (client.get_equipment(eid).get("ret") or [])
            if not records:
                raise ValueError("MARS returned no record for this ID")
            rec = records[0]
            values = [_text(rec.get(c)) for c in COLUMNS]
            values += [json.dumps(rec, ensure_ascii=False), now, eid]
            conn.execute(sql_ok, values)
            ok += 1
        except (requests.ConnectionError, requests.Timeout) as e:
            aborted = f"Cannot reach MARS (VPN / network?): {e}"
            break                                   # no point trying the rest
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (401, 403):
                aborted = f"MARS rejected the login (HTTP {code})"
                break
            conn.execute(sql_err, (str(e), eid))
            failed += 1
        except Exception as e:
            conn.execute(sql_err, (str(e), eid))
            failed += 1
        conn.commit()
        if progress:
            progress(n, len(ids), eid)

    conn.commit()
    if ok > 0:                                      # remember "done for today"
        set_meta(conn, "last_sync_date", datetime.now().date().isoformat())
        set_meta(conn, "last_sync_at", now)
    return {"total": len(ids), "ok": ok, "failed": failed, "aborted": aborted}


def is_due(conn, ignore_time=False, now=None):
    """True if we have not synced yet today (and it is past SYNC_AFTER)."""
    now = now or datetime.now()
    if get_meta(conn, "last_sync_date") == now.date().isoformat():
        return False
    return ignore_time or now.time() >= SYNC_AFTER


# ---------------------------------------------------------------- scheduler
class DailySync:
    """Runs sync at app start and once per new day while the app is open.

    on_done(summary) is called FROM THE BACKGROUND THREAD. If your UI is
    Tkinter / PyQt, hand the result to the UI thread (root.after / a signal)
    instead of touching widgets directly.
    """

    def __init__(self, client, on_done=None, progress=None):
        self.client = client
        self.on_done = on_done
        self.progress = progress
        self._stop = threading.Event()
        self._busy = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def sync_now(self):
        """For a 'Refresh now' button."""
        threading.Thread(target=self._run_once, kwargs={"force": True}, daemon=True).start()

    def _loop(self):
        first = True
        while not self._stop.is_set():
            self._run_once(ignore_time=first)      # at start-up, ignore the 07:00 rule
            first = False
            self._stop.wait(CHECK_EVERY_SECONDS)

    def _run_once(self, force=False, ignore_time=False):
        if not self._busy.acquire(blocking=False):
            return                                  # a sync is already running
        try:
            conn = connect()
            try:
                ensure_schema(conn)
                if force or is_due(conn, ignore_time=ignore_time):
                    summary = sync_all(self.client, conn, self.progress)
                    if self.on_done:
                        self.on_done(summary)
            finally:
                conn.close()
        finally:
            self._busy.release()


# ---------------------------------------------------------------- try it
if __name__ == "__main__":
    client = MarsClient(os.environ["MARS_USER"], os.environ["MARS_PASSWORD"])

    conn = connect()
    ensure_schema(conn)
    add_ids(conn, ["PN010064"])                    # your real list goes here / already in DB
    print(sync_all(client, conn, lambda n, t, e: print(f"  {n}/{t} {e}")))

    for row in conn.execute(
            f"SELECT Equipment_ID, Model_No, Cal_Due_Date_Local_DateOnly, last_synced_at, sync_error "
            f"FROM {TABLE}"):
        print(dict(row))
    conn.close()
