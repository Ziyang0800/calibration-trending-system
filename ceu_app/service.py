"""App state and actions. The UI calls these through app.py (Api)."""
import subprocess, threading, time
from datetime import datetime, date
from pathlib import Path

import logic, mars, store

DAY = 24 * 3600


class Service:
    def __init__(self):
        self.dir = store.data_dir()
        self.setup, self.setup_error = store.load_setup(self.dir)
        self.cache = store.read_json(self.dir / "cache.json", {"fetched_at": None, "records": {}})
        self.app = store.read_json(self.dir / "state.json", {"last_reminder": None, "last_set": None})
        self.lock = threading.RLock()
        self.station, self.b2_set, self.ack_b2 = "B-1", None, False
        self.verified = {"B-1": set(), "B-2": set()}
        self.so = ""
        self.refreshing, self.fetch_error = False, None
        self.creds = mars.load_credentials()
        self.last_report = None
        threading.Thread(target=self._daily, daemon=True).start()

    # ---------- data ----------
    def all_ids(self):
        ids = [s["equipment_id"] for s in self.setup["b1"]]
        for s in self.setup["sets"]:
            ids += [s["calibrator"], s["amplifier"]]
        return list(dict.fromkeys(ids))

    def _eval(self, eid):
        return logic.evaluate(eid, self.cache["records"].get(eid))

    def refresh(self):
        with self.lock:
            if self.refreshing:
                return
            self.refreshing, self.fetch_error = True, None
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            ids = self.all_ids()
            if self.creds:
                client = mars.MarsClient(*self.creds)
                recs = mars.fetch_many(client, ids)
            else:
                recs = mars.demo_records(ids)
            with self.lock:
                self.cache["records"].update(recs)
                self.cache["fetched_at"] = datetime.now().isoformat(timespec="seconds")
                store.write_json(self.dir / "cache.json", self.cache)
        except Exception as e:
            with self.lock:
                self.fetch_error = "%s: %s" % (type(e).__name__, e)
        finally:
            with self.lock:
                self.refreshing = False

    def _daily(self):
        while True:                      # once a day while the app stays open
            time.sleep(DAY)
            self.refresh()

    def connect(self, user, password, remember):
        if not mars.requests:
            raise RuntimeError("The 'requests' package is not installed")
        c = mars.MarsClient(user, password)
        c.login()                        # raises if the account is rejected
        self.creds = (user, password)
        if remember:
            mars.save_credentials(user, password)
        self.refresh()

    # ---------- views ----------
    def rows(self):
        out = []
        ver = self.verified[self.station]
        for slot, eid in logic.station_rows(self.setup, self.station, self.b2_set):
            r = self._eval(eid)
            r["slot"], r["verified"] = slot, eid in ver
            out.append(r)
        return out

    def state(self):
        with self.lock:
            rows = self.rows()
            ev = {e: self._eval(e) for e in self.all_ids()}
            b1 = [ev[s["equipment_id"]] for s in self.setup["b1"]]
            b2 = None
            if self.b2_set:
                s = logic.set_by_num(self.setup, self.b2_set)
                b2 = [ev[s["calibrator"]], ev[s["amplifier"]]]
            fetched = self.cache["fetched_at"]
            stale = (not fetched) or (datetime.now() - datetime.fromisoformat(fetched)).total_seconds() > DAY
            return {
                "station": self.station, "b2_set": self.b2_set, "ack_b2": self.ack_b2, "so": self.so,
                "mode": "live" if self.creds else "demo", "setup_error": self.setup_error, "refreshing": self.refreshing,
                "fetched_at": fetched, "fetch_error": self.fetch_error, "stale": stale,
                "rows": rows,
                "verified": sum(1 for r in rows if r["verified"]), "total": len(rows),
                "all_verified": bool(rows) and all(r["verified"] for r in rows),
                "kpi": {
                    "b1_ready": sum(1 for r in b1 if r["valid"]), "b1_total": len(b1),
                    "b2_ready": None if b2 is None else sum(1 for r in b2 if r["valid"]),
                    "expiring": sum(1 for r in ev.values() if r["status"] == "Expiring Soon"),
                    "expired": sum(1 for r in ev.values() if r["status"] == "Expired"),
                    "sent": sum(1 for r in ev.values() if r["status"] == "Sent for Cal"),
                    "other": sum(1 for r in ev.values() if r["status"] in ("Not found", "Not in use", "No due date")),
                },
            }

    def sets(self):
        with self.lock:
            b1_pair = {x["equipment_id"] for x in self.setup["b1"][:2]}   # B-1 Calibrator + Amplifier
            out = []
            for s in self.setup["sets"]:
                cal, amp = self._eval(s["calibrator"]), self._eval(s["amplifier"])
                in_use = bool({s["calibrator"], s["amplifier"]} & b1_pair)   # shares an instrument with B-1
                bad = [x for x in (cal, amp) if not x["valid"]]
                reason = ""
                if in_use:
                    reason = "In use at Station B-1"
                elif bad:
                    reason = "; ".join("%s: %s" % (x["equipment_id"], x["status"]) for x in bad)
                out.append({"num": s["num"], "calibrator": cal, "amplifier": amp,
                            "available": not in_use and not bad, "reason": reason,
                            "last_used": self.app.get("last_set") == s["num"]})
            return out

    # ---------- actions ----------
    def need_warning(self):
        return not self.ack_b2

    def acknowledge_b2(self):
        self.ack_b2 = True

    def choose_set(self, num):
        with self.lock:
            s = next((x for x in self.sets() if x["num"] == num), None)
            if not s or not s["available"]:
                raise ValueError("Set %s is not available" % num)
            self.b2_set, self.station = num, "B-2"
            self.verified["B-2"] = set()
            self.app["last_set"] = num
            store.write_json(self.dir / "state.json", self.app)

    def go_b1(self):
        self.station = "B-1"

    def set_so(self, so):
        self.so = "".join(c for c in (so or "") if c.isalnum() or c in "-_")[:30]

    def scan(self, code):
        code = logic.normalise_scan(code)
        with self.lock:
            if not code:
                return {"kind": "ignore"}
            rows = self.rows()
            match = [r for r in rows if r["equipment_id"].upper() == code]
            if not match:                                   # rule 3: must belong to this station
                return {"kind": "not_in_station", "code": code,
                        "message": "%s is not part of Station %s" % (code, self.station)}
            r = match[0]
            if r["verified"]:
                return {"kind": "dup", "code": code, "message": "%s is already verified" % code}
            if not r["valid"]:                              # rules 1 and 2
                return {"kind": "invalid", "code": code,
                        "message": "%s cannot be verified: %s" % (code, r["reason"] or r["status"])}
            self.verified[self.station].add(r["equipment_id"])
            return {"kind": "verified", "code": code,
                    "message": "%s verified (%s)" % (code, r["slot"])}

    def reminders(self):
        """ETEs due within 30 days, shown at most once per day."""
        today = date.today().isoformat()
        with self.lock:
            if self.app.get("last_reminder") == today:
                return []
            return [e for e in (self._eval(i) for i in self.all_ids()) if e["status"] == "Expiring Soon"]

    def reminders_shown(self):
        self.app["last_reminder"] = date.today().isoformat()
        store.write_json(self.dir / "state.json", self.app)

    def reset_station(self):
        self.verified[self.station] = set()

    def complete(self):
        with self.lock:
            rows = self.rows()
            if not (rows and all(r["verified"] for r in rows)):
                raise ValueError("Not every ETE is verified")
            lines = ["Slot\tEquipment ID\tModel\tCal Due\tWhereabout"]
            lines += ["%s\t%s\t%s\t%s\t%s" % (r["slot"], r["equipment_id"], r["model"], r["due"], r["whereabout"])
                      for r in rows]
            text = "\n".join(lines)
            copied = _copy(text)
            folder = Path.home() / "Documents" / "CEU Reports"
            folder.mkdir(parents=True, exist_ok=True)
            name = "CEU_%s_%s_%s.txt" % (("SO-" + self.so) if self.so else "NO-SO", self.station,
                                          datetime.now().strftime("%Y%m%d_%H%M%S"))
            path = folder / name
            head = "CEU validation  Station %s  %s\nSO: %s\nMARS data as of: %s\n\n" % (
                self.station, datetime.now().strftime("%Y-%m-%d %H:%M"), self.so or "-", self.cache["fetched_at"])
            path.write_text(head + text + "\n", encoding="utf-8")
            self.last_report = str(path)
            return {"path": str(path), "copied": copied}


def _copy(text):
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        try:
            subprocess.run(["clip"], input=text.encode("ascii", "replace"), check=True)
            return True
        except Exception:
            return False
