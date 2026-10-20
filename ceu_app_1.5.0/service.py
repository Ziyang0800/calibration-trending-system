"""App state and actions. The UI calls these through app.py (Api)."""
import logging, os, re, threading, time
from collections import deque
from datetime import datetime, date
from pathlib import Path

import logic, mars, names, plugins, report, store, updater
from version import __version__

DAY = 24 * 3600
REFRESH_MINUTES = 45                             # automatic MARS refresh while the app is open (override: "refresh_minutes" in setup.json)


class Service:
    def __init__(self):
        self.dir = store.data_dir()
        self.setup, self.setup_error = store.load_setup(self.dir)
        self.cache = store.read_json(self.dir / "cache.json", {"fetched_at": None, "records": {}})
        self.app = store.read_json(self.dir / "state.json", {"last_reminder": None, "last_set": None})
        self.lock = threading.RLock()
        self.packs, self.pack_info, self.pack_problems, self.pack_notice = {}, {}, [], ""
        self.product = None                              # None = start screen, else a product (pack) id
        self.refreshing, self.fetch_error = False, None
        self._load_packs()                               # a pack that fails to load never stops the shell
        self.creds = mars.load_credentials()
        self.demo_ok = os.environ.get("CEU_DEMO") == "1"       # demo data only on purpose (tests, development)
        self.pending_import = None
        self.last_report = None
        self.update = {"state": "unknown"}
        updater.cleanup_old()
        self.greeting = names.lookup(self.dir, self.setup)
        threading.Thread(target=self.check_update, daemon=True).start()
        threading.Thread(target=self._daily, daemon=True).start()

    # ---------- plug-in packs ----------
    def _load_packs(self):
        targets = (store.read_json(self.dir / "packs_state.json", {}) or {}).get("targets", {})
        self.packs, self.pack_info, self.pack_problems = plugins.load_all(
            self, __version__, store.resource_path("packs"), self.dir / "packs", targets)

    def pack_ui(self, pid):
        """The screen files of a pack: {html, js, css} (strings)."""
        info = self.pack_info.get(pid)
        if not info or pid not in self.packs:
            raise ValueError("Product %s is not loaded" % pid)
        ui, folder = info["manifest"].get("ui") or {}, Path(info["folder"])
        read = lambda k: (folder / ui[k]).read_text(encoding="utf-8-sig") if ui.get(k) else ""
        return {"html": read("html"), "js": read("js"), "css": read("css")}

    def product_call(self, name, args):
        pk = self._pack()
        if not pk:
            raise ValueError("No product is open")
        return pk.rpc(name, *args)

    # ---------- data ----------
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
            ids = list(dict.fromkeys(i for pk in self.packs.values() for i in pk.ids() + pk.master_ids()))
            if self.creds:
                client = mars.MarsClient(*self.creds)
                recs = mars.fetch_many(client, ids)
            elif not self.demo_ok:
                return                                   # no login: never invent data
            else:
                recs = mars.demo_records(ids, {k: v for pk in self.packs.values() for k, v in pk.demo_models().items()})
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
        """Checks every minute and fetches again once the data is REFRESH_MINUTES old (45 by default).
        Checking the age, not sleeping, also copes with the PC being asleep."""
        while True:
            time.sleep(60)
            try:
                limit = max(5, int(self.setup.get("refresh_minutes") or REFRESH_MINUTES)) * 60
            except (TypeError, ValueError):
                limit = REFRESH_MINUTES * 60
            f = self.cache["fetched_at"]
            if not f or (datetime.now() - datetime.fromisoformat(f)).total_seconds() >= limit:
                self.refresh()
                self.check_update()

    # ---------- updates ----------
    def check_update(self):
        folder = updater.release_dir(self.setup)
        names.sync(folder, self.dir)                  # names.json from the shared folder, if reachable
        self.greeting = names.lookup(self.dir, self.setup)
        self._sync_packs(folder)
        r = updater.check(folder, __version__)
        with self.lock:
            self.update = r

    def _sync_packs(self, folder):
        """Download newer (or pinned, or pilot) pack versions. They start at the next launch of the app."""
        try:
            res = plugins.sync(folder, self.dir / "packs", __version__, os.environ.get("COMPUTERNAME", ""), names.login_name())
            notes = list(res["notices"])
            if res["targets"]:
                state = store.read_json(self.dir / "packs_state.json", {}) or {}
                state.setdefault("targets", {}).update(res["targets"])
                store.write_json(self.dir / "packs_state.json", state)
            for pid, ver in res["targets"].items():
                info = self.pack_info.get(pid)
                have = (info or {}).get("manifest", {}).get("version") if info and not info.get("error") else None
                if info and not info.get("error") and have != ver:
                    notes.append("%s %s is downloaded. Restart the app to use it (running %s)." % (info["manifest"]["name"], ver, have))
                elif not info:
                    notes.append("New product %s %s is downloaded. Restart the app to use it." % (pid, ver))
            with self.lock:
                self.pack_notice = "\n".join(notes)
        except Exception:
            logging.exception("pack sync failed")

    def apply_update(self):
        with self.lock:
            info, folder = dict(self.update), updater.release_dir(self.setup)
        if info.get("state") != "available":
            raise ValueError("No update is available")
        updater.apply(folder, info)                 # swaps the exe and starts the new one
        return True

    def connect(self, user, password, remember):
        if not mars.requests:
            raise RuntimeError("The 'requests' package is not installed")
        c = mars.MarsClient(user, password)
        c.login()                        # raises if the account is rejected
        self.creds = (user, password)
        if remember:
            mars.save_credentials(user, password)
        self.refresh()

    # ---------- products (start screen) ----------
    def products(self):
        extra = []
        for pid, info in sorted(self.pack_info.items(), key=lambda kv: (kv[1]["manifest"].get("order", 100), kv[1]["manifest"]["name"])):
            m = info["manifest"]
            e = {"id": pid, "name": m["name"], "tag": m.get("tag", ""), "desc": m.get("desc", ""), "keywords": m.get("keywords", []),
                 "detail": m.get("detail", ""), "models": [], "modules": [], "version": m["version"], "ui": True}
            if pid in self.packs:
                e.update(self.packs[pid].publish())
            else:
                e["error"] = info["error"]
            extra.append(e)
        out = extra
        with self.lock:
            for p in out:
                bad, total = None, 0
                if p["id"] in self.packs:
                    bad, total = self.packs[p["id"]].health()
                if p.get("error"):
                    p["status"] = {"kind": "bad", "text": "Failed to load: " + p["error"][:120]}
                elif not self.creds and not self.demo_ok:
                    p["status"] = {"kind": "bad", "text": "No MARS login"}
                elif not self.cache["fetched_at"]:
                    p["status"] = {"kind": "", "text": "Waiting for MARS data"}
                elif bad is None:
                    p["status"] = None
                else:
                    p["status"] = {"kind": "bad" if bad else "ok", "text": ("%d need attention" % bad) if bad else "All ETEs valid"}
        return out

    def _need(self):
        pk = self._pack()
        if not pk:
            raise ValueError("No product is open")
        return pk

    def _pack(self):
        """The active pack object, or None on the start screen."""
        return self.packs.get(self.product)

    def open_product(self, pid, model="", module=""):
        if pid not in self.pack_info:
            raise ValueError("Unknown product %s" % pid)
        if pid not in self.packs:
            raise ValueError("Product %s is not available: %s" % (pid, self.pack_info.get(pid, {}).get("error", "unknown")))
        with self.lock:
            self.product = pid
            self.packs[pid].open(model, module)
        if model or module:
            it = self.packs[pid].recent_item()
            if it:
                self._recent_add(dict(it, pid=pid))

    def go_home(self):
        """Back to the start screen: whatever was in progress (scans, job, module choice, B-2 Set) is cleared."""
        with self.lock:
            for pk in self.packs.values():
                getattr(pk, "close", pk.new_session)()
            self.product = None

    # ---------- login / problems ----------
    def mode(self):
        return "live" if self.creds else ("demo" if self.demo_ok else "nologin")

    def dev(self):
        return str(self.setup.get("dev_name") or "Jacky")

    def no_login_msg(self):
        return "This PC has no MARS login. Please inform the developer to sign in to MARS on this PC."

    def problems(self):
        out = [self.setup_error, names.problem(self.dir)]
        out += self.pack_problems
        for pk in self.packs.values():
            out += pk.problems()
        return "\n".join(p for p in out if p)

    def _recent_add(self, item):
        with self.lock:
            lst = [x for x in self.app.get("recent", []) if (x.get("pid"), x.get("model"), x.get("module")) != (item["pid"], item["model"], item["module"])]
            self.app["recent"] = ([item] + lst)[:5]
            store.write_json(self.dir / "state.json", self.app)

    def diagnostics(self):
        """Plain text for the 'Copy diagnostics' button. No passwords."""
        with self.lock:
            lines = ["CEU Validation Tool %s" % __version__, "Time: %s" % datetime.now().isoformat(timespec="seconds"),
                     "PC user: %s" % names.login_name(), "Data folder: %s" % self.dir,
                     "MARS: mode=%s source=%s last fetch=%s error=%s" % (self.mode(), mars.SOURCE, self.cache.get("fetched_at"), self.fetch_error),
                     "Update: %s" % (self.update or {}).get("state"), "Product open: %s" % self.product,
                     "Problems: %s" % (self.problems().replace("\n", " | ") or "none")]
            for pk in self.packs.values():
                lines += getattr(pk, "diag", lambda: [])()
            for pid, info in sorted(self.pack_info.items()):
                m = info["manifest"]
                lines.append("Pack %s %s (%s)%s%s" % (pid, m["version"], info["source"], " ERROR: " + info["error"] if info["error"] else "",
                             "  active = " + ", ".join(self.packs[pid].ids()) if pid in self.packs else ""))
            if self.pack_notice:
                lines.append("Pack notices: " + self.pack_notice.replace("\n", " | "))
            log = self.dir / "app.log"
            if log.exists():
                try:
                    with open(log, encoding="utf-8", errors="replace") as f:
                        tail = list(deque(f, maxlen=40))
                    lines += ["", "--- last lines of app.log ---"] + [t.rstrip() for t in tail]
                except OSError:
                    pass
        return "\n".join(lines)

    def _common(self):
        fetched = self.cache["fetched_at"]
        stale = (not fetched) or (datetime.now() - datetime.fromisoformat(fetched)).total_seconds() > DAY
        return {"version": __version__, "update": self.update, "prefs": self.prefs(), "product": self.product, "greeting": self.greeting,
                "mode": self.mode(), "setup_error": self.problems(), "dev": self.dev(), "recent": self.app.get("recent", []), "pack_notice": self.pack_notice,
                "creds_source": mars.SOURCE if self.creds else None, "refreshing": self.refreshing,
                "fetched_at": fetched, "fetch_error": self.fetch_error, "stale": stale}

    def state(self):
        with self.lock:
            if self.product is None:
                return dict(self._common(), rows=[], verified=0, total=0, all_verified=False)
            return dict(self._common(), **self._pack().state())

    def preview_import(self, path):
        """Read the workbook and say what would change; nothing is replaced until confirm_import()."""
        import masterlist
        rows = masterlist.read_workbook(path)
        pk = self._pack()
        cur, active = pk.current_masterlist(), set(pk.active_ids())
        norm = lambda m: re.sub(r"\s+", "", str(m.get("equipment_id") or "")).upper()
        old, new = {norm(m): m for m in cur if norm(m)}, {norm(m): m for m in rows if norm(m)}
        added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
        changed = sorted(e for e in set(old) & set(new) if (str(old[e].get("model") or "").strip(), str(old[e].get("serial") or "").strip()) != (str(new[e].get("model") or "").strip(), str(new[e].get("serial") or "").strip()))
        self.pending_import = {"product": self.product, "rows": rows}
        return {"ok": True, "count": len(rows), "old_count": len(old), "added": [{"id": e, "model": new[e].get("model", "")} for e in added],
                "removed": [{"id": e, "model": old[e].get("model", ""), "active": e in active} for e in removed], "changed": changed}

    def confirm_import(self):
        p, self.pending_import = self.pending_import, None
        if not p or p["product"] != self.product:
            raise ValueError("Nothing to import (the preview was cancelled or the product changed)")
        return self._pack().apply_masterlist(p["rows"])

    def cancel_import(self):
        self.pending_import = None

    def get_setup(self):
        return self._need().get_setup()

    def save_setup(self, data):
        return self._need().save_setup(data)

    # ---------- ETE manager ----------
    def ete_list(self):
        """Every ETE the product knows with its MARS status and where it is used."""
        return self._need().ete_list()

    def export_etes(self):
        import csv
        d = Path.home() / "Documents" / "CEU Reports"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("ETE_Status_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        rows = self.ete_list()["rows"]
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Equipment ID", "Model", "Description", "Serial", "Set", "Used in", "Whereabout", "Cal due", "Days left", "Status"])
            for r in rows:
                w.writerow([r["equipment_id"], r["model"], r["description"], r["serial"], r["set"], "; ".join(r["used_in"]),
                            r["whereabout"], r["due"] or "", "" if r["days_left"] is None else r["days_left"], r["status"]])
        os.startfile(str(p.parent)) if hasattr(os, "startfile") else None
        return str(p)

    # ---------- actions (all product work is done by the open pack) ----------
    def set_job(self, so, serial, result):
        return self._need().set_job(so, serial, result)

    def new_session(self):
        return self._need().new_session()

    def open_report(self):
        if self.last_report and os.path.exists(self.last_report) and hasattr(os, "startfile"):
            os.startfile(self.last_report)

    def scan(self, code):
        return self._need().scan(code)

    def reminders(self):
        """ETEs due within 30 days, shown at most once per day (what is in use now, in every product)."""
        today = date.today().isoformat()
        with self.lock:
            if self.app.get("last_reminder") == today:
                return []
            ids = []
            for pk in self.packs.values():
                ids += getattr(pk, "reminder_ids", pk.ids)()
            return [e for e in (self._eval(i) for i in dict.fromkeys(ids)) if e["status"] == "Expiring Soon"]

    def reminders_shown(self):
        self.app["last_reminder"] = date.today().isoformat()
        store.write_json(self.dir / "state.json", self.app)

    def reset_station(self):
        return self._need().reset()

    def reuse_session(self):
        return self._need().reuse_session()

    def _table(self):
        """The verified ETE rows in station order: (model, serial, equipment ID, cal due)."""
        if self.mode() == "nologin":
            raise ValueError(self.no_login_msg())
        return self._need().table()

    def complete(self):
        """Step 1 of finishing: put the ETE rows (no header) on the clipboard, for pasting into MARS."""
        table = self._table()
        return {"copied": _copy("\n".join("\t".join(str(v or "") for v in t) for t in table))}

    def report_default(self):
        """Folder and file name offered in the Save dialog (last used folder, else Documents\\CEU Reports)."""
        with self.lock:
            last = self.app.get("last_report_dir")
            d = Path(last) if last else None
            if not (d and d.is_dir()):
                d = Path.home() / "Documents" / "CEU Reports"
                d.mkdir(parents=True, exist_ok=True)
            pk = self._pack()
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = "CEU_%s_%s_%s.pdf" % (pk.job["so"], pk.file_tag(), stamp)
            return str(d), name

    def save_report(self, path):
        """Step 2 of finishing: build the PDF where the user chose."""
        table = self._table()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        note = "MARS data as of %s" % (self.cache["fetched_at"] or "n/a")
        pk = self._pack()
        out = report.build_pdf(path, table, pk.job, pk.file_tag(), pk.procedure(), pk.unit_model(), note)
        it = pk.recent_item()
        if it:
            self._recent_add(dict(it, pid=self.product))
        with self.lock:
            self.last_report = str(out)
            self.app["last_report_dir"] = str(path.parent)
            store.write_json(self.dir / "state.json", self.app)
        return str(out)

    # ---------- preferences (kept in state.json, so they survive restarts) ----------
    PREFS = {"theme": ("dark", "light"), "sort_done": ("1", "0"), "reduce_motion": ("0", "1")}

    def set_pref(self, key, value):
        if key in self.PREFS and value in self.PREFS[key]:
            with self.lock:
                self.app.setdefault("prefs", {})[key] = value
                store.write_json(self.dir / "state.json", self.app)

    def prefs(self):
        got = self.app.get("prefs", {})
        return {k: (got.get(k) if got.get(k) in v else v[0]) for k, v in self.PREFS.items()}

def _copy(text):
    """Put text on the Windows clipboard with the Win32 API (no tkinter: a second GUI toolkit
    started from the bridge thread froze the window)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.GlobalAlloc.restype, k32.GlobalAlloc.argtypes = wintypes.HGLOBAL, [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalLock.restype, k32.GlobalLock.argtypes = wintypes.LPVOID, [wintypes.HGLOBAL]
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        u32.CreateWindowExA.restype = wintypes.HWND
        u32.CreateWindowExA.argtypes = [wintypes.DWORD, wintypes.LPCSTR, wintypes.LPCSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.DestroyWindow.argtypes = [wintypes.HWND]

        buf = ctypes.create_unicode_buffer(text.replace("\r\n", "\n").replace("\n", "\r\n"))
        size = ctypes.sizeof(buf)
        hwnd = u32.CreateWindowExA(0, b"STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)   # clipboard owner
        try:
            for _ in range(20):                                   # clipboard may be briefly busy
                if u32.OpenClipboard(hwnd):
                    break
                time.sleep(0.05)
            else:
                return False
            try:
                u32.EmptyClipboard()
                h = k32.GlobalAlloc(0x0002, size)                 # GMEM_MOVEABLE
                p = k32.GlobalLock(h)
                ctypes.memmove(p, buf, size)
                k32.GlobalUnlock(h)
                if not u32.SetClipboardData(13, h):               # CF_UNICODETEXT
                    k32.GlobalFree(h)
                    return False
                return True
            finally:
                u32.CloseClipboard()
        finally:
            if hwnd:
                u32.DestroyWindow(hwnd)
    except Exception:
        logging.exception("clipboard copy failed")
        return False
