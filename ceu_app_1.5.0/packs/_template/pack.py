"""Starting point for a new product. Copy packs\\_template to packs\\<your_id>, change product.json and this file.
This minimal pack needs a fixed list of ETEs (config.json). Every method below is part of pack contract 1 (see CONTRACT.md).
`svc` is the shell: svc._eval(equipment_id) gives the MARS status of an ETE, svc.lock guards shared state."""
import re
from pathlib import Path

import logic, store

SO_RE = re.compile(r"^(WO-\d{4,}|SO\d{4,}(-\d+)?)$")
SERIAL_RE = re.compile(r"^[A-Z0-9]{10}$")


class Pack:
    def __init__(self, svc, folder, manifest):
        self.svc, self.folder, self.manifest = svc, Path(folder), manifest
        self.cfg = store.read_json(self.folder / "config.json", {"required": []})
        self.job = {"so": "", "serial": "", "result": ""}
        self.verified = set()

    # ---- start screen and refresh ----
    def problems(self):                         # texts for the red banner (broken data files...)
        return [] if self.cfg.get("required") else ["%s: config.json has no required ETEs" % self.manifest["name"]]
    def publish(self):                          # extra search terms: Model IDs / Module IDs typed on the start screen
        return {"models": [], "modules": [], "mdesc": {}}
    def health(self):                           # (ETEs needing attention, ETEs in the active setup) for the tile status
        rows = self.rows()
        return sum(1 for r in rows if not r["valid"]), len(rows)
    def ids(self):                              # ETEs the shell must fetch from MARS
        return [x["equipment_id"] for x in self.cfg["required"]]
    def master_ids(self):
        return []
    def demo_models(self):                      # only used by demo mode
        return {}
    def open(self, model, module):              # the start screen opened this product
        pass
    def recent_item(self):                      # {"model","module","label"} for the Recent row, or None
        return None
    def rpc(self, name, *args):                 # calls from ui/*.js: shell.call(name, ...)
        raise ValueError("Unknown call %s" % name)

    # ---- job and scanning ----
    def _errors(self):
        j, e = self.job, {}
        if not SO_RE.match(j["so"]): e["so"] = "Service Order: WO-######### or SO#########"
        if not SERIAL_RE.match(j["serial"]): e["serial"] = "Serial # must be 10 letters/digits"
        if j["result"] not in logic.RESULT_TYPES: e["result"] = "Choose a result type"
        return e
    def _job_view(self):
        e = self._errors()
        return dict(self.job, ok=not e, errors=e)
    def set_job(self, so, serial, result):
        clean = lambda t: re.sub(r"\s+", "", t or "").upper()
        self.job = {"so": clean(so), "serial": clean(serial), "result": result if result in logic.RESULT_TYPES else ""}
        return self._job_view()
    def rows(self):
        out = []
        for x in self.cfg["required"]:
            r = self.svc._eval(x["equipment_id"])
            r["slot"], r["no_scan"], r["hint"] = x["slot"], False, ""
            r["verified"] = r["valid"] and x["equipment_id"] in self.verified
            out.append(r)
        return out
    def scan(self, code):
        code = logic.normalise_scan(code)
        with self.svc.lock:
            if not code: return {"kind": "ignore"}
            if self.svc.mode() == "nologin": return {"kind": "no_login", "message": self.svc.no_login_msg()}
            if self._errors(): return {"kind": "need_job", "message": "Fill in the job fields first"}
            hit = [r for r in self.rows() if r["equipment_id"].upper() == code]
            if not hit: return {"kind": "not_in_station", "code": code, "message": "%s is not part of this product" % code}
            r = hit[0]
            if r["verified"]: return {"kind": "dup", "code": code, "message": "%s is already verified" % code}
            if not r["valid"]: return {"kind": "invalid", "code": code, "message": "%s cannot be verified: %s" % (code, r["reason"] or r["status"])}
            self.verified.add(r["equipment_id"])
            return {"kind": "verified", "code": code, "message": "%s verified (%s)" % (code, r["slot"])}
    def new_session(self):                      # everything cleared (also when the user goes back to the start screen)
        self.job = {"so": "", "serial": "", "result": ""}
        self.verified = set()
    def reset(self):                            # "Clear scans"
        self.verified = set()
    def reuse_session(self):                    # "another DUT, same setup"; raise if you do not support it
        raise ValueError("Not supported by this product")

    # ---- state for the screen ----
    def state(self):
        with self.svc.lock:
            rows = self.rows()
            ev = lambda s: sum(1 for r in rows if r["status"] == s)
            return {"product": self.manifest["id"], "job": self._job_view(), "rows": rows,
                    "verified": sum(1 for r in rows if r["verified"]), "total": len(rows),
                    "need_scan": len(rows), "scanned": sum(1 for r in rows if r["verified"]),
                    "all_verified": bool(rows) and all(r["verified"] for r in rows), "reuse": None,
                    "kpi": {"ready": sum(1 for r in rows if r["valid"]), "total": len(rows), "expiring": ev("Expiring Soon"),
                            "expired": ev("Expired"), "sent": ev("Sent for Cal")}}

    # ---- report ----
    def table(self):                            # [(model, serial, equipment ID, cal due text)] in report order
        with self.svc.lock:
            rows = self.rows()
            if not (rows and all(r["verified"] for r in rows)): raise ValueError("Not every ETE is verified")
            if self._errors(): raise ValueError("Service Order, Serial # and Result Type are required")
            return [(r["model"], r["serial"], r["equipment_id"], logic.fmt_due(r["due"])) for r in rows]
    def unit_model(self): return self.manifest["name"]
    def procedure(self): return self.manifest.get("procedure", "")
    def file_tag(self): return "EXAMPLE"

    # ---- Setup page / ETE manager (stubs: add real ones when the product needs them) ----
    def get_setup(self): return {}
    def save_setup(self, data): return {"ok": True, "warnings": []}
    def current_masterlist(self): return []
    def active_ids(self): return self.ids()
    def apply_masterlist(self, rows): return {"ok": True, "count": 0, "sets": 0}
    def ete_list(self):
        with self.svc.lock:
            out = [dict(equipment_id=r["equipment_id"], model=r["model"], description=r["description"], serial=r["serial"], set="",
                        used_in=[r["slot"]], whereabout=r["whereabout"], due=r["due"], days_left=r["days_left"], status=r["status"], reason=r["reason"])
                   for r in self.rows()]
            return {"rows": out, "fetched_at": self.svc.cache.get("fetched_at")}
