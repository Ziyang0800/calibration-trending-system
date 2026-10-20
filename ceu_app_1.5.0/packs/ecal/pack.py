"""ECal pack (a plug-in of the CEU Validation Tool, contract 1): ECal modules (2- and 4-port) and torque testers.
Required ETEs = the VNA + the cal kit of each connector type of the DUT (+ torque testers when a torque wrench is
available). Every required ETE is the ACTIVE unit chosen in Setup (like the OGC), so a scan can only confirm it.
Torque testers sit in the mech-lab: they are listed on the report but never scanned."""
import json, logging, re, shutil
from datetime import date, datetime
from pathlib import Path

import logic, store

PROCEDURE = "Orion, ECAL (5959-9575), ECAL.CAL.N882"
SO_RE_TXT = r"^(WO-\d{4,}|SO\d{4,}(-\d+)?)$"
SERIAL_RE_TXT = r"^[A-Z0-9]{10}$"


def _up(t):
    return re.sub(r"\s+", "", str(t or "")).upper()


def validate_catalog(d):
    """'' when the catalog is usable, else a short reason (shown in the red banner)."""
    if not isinstance(d, dict):
        return "the file is not a JSON object"
    for k in ("models", "modules", "connectors", "vna", "torque"):
        if not d.get(k):
            return 'missing or empty "%s"' % k
    if not isinstance(d["models"], dict) or not isinstance(d["modules"], dict) or not isinstance(d["connectors"], dict):
        return '"models", "modules" and "connectors" must be objects'
    for name, m in d["models"].items():
        if not isinstance(m, dict) or not isinstance(m.get("modules"), list) or "ports" not in m:
            return 'model %s needs "ports" and a "modules" list' % name
        for mod in m["modules"]:
            if mod not in d["modules"]:
                return 'model %s lists module %s, which is not in "modules"' % (name, mod)
    for mod, mi in d["modules"].items():
        if not isinstance(mi, dict) or mi.get("type") not in ("Fixed", "Mixed") or "ports" not in mi:
            return 'module %s needs "type" (Fixed or Mixed) and "ports"' % mod
        if mi["type"] == "Fixed" and (mi.get("kit") not in d["connectors"].values() or not isinstance(mi.get("options"), list)):
            return 'Fixed module %s needs "options" and a "kit" that appears under "connectors"' % mod
        if mi["type"] == "Mixed" and (not isinstance(mi.get("connectors"), list) or any(c not in d["connectors"] for c in mi["connectors"])):
            return 'Mixed module %s needs a "connectors" list using connector names from "connectors"' % mod
    return ""


def load_catalog(data_dir, folder):
    """ecal_catalog.json: the %APPDATA%\\CEUTool copy wins over the bundled one. Returns (catalog, error_text):
    a broken local copy is reported (red banner) and the bundled catalog is used instead."""
    local, err = Path(data_dir) / "ecal_catalog.json", ""
    if local.exists():
        try:
            with open(local, encoding="utf-8-sig") as f:
                d = json.load(f)
            why = validate_catalog(d)
        except (OSError, ValueError) as e:
            d, why = None, str(e)
        if not why:
            return d, ""
        err = "ecal_catalog.json has a mistake: %s - using the built-in catalog instead  [%s]" % (why, local)
    d = store.read_json(Path(folder) / "ecal_catalog.json", None)
    why = validate_catalog(d)
    if why:
        raise ValueError("the built-in ecal_catalog.json is broken: " + why)
    return d, err


class Pack:
    def __init__(self, svc, folder, manifest):
        self.svc, self.folder, self.manifest = svc, Path(folder), manifest
        self.cat, self.cat_error = load_catalog(svc.dir, self.folder)
        self.path = svc.dir / "setup_ecal.json"
        self.setup, self.error = self._load()
        self.sel = self._blank_sel()
        self.job = {"so": "", "serial": "", "result": ""}
        self.verified, self.reuse = set(), None
        self._norm_models = {_up(m): m for m in self.cat["models"]}
        self._norm_modules = {_up(m): m for m in self.cat["modules"]}

    def problems(self):
        return [p for p in (self.cat_error, self.error) if p]

    def health(self):
        """(units needing attention, units in the active setup) for the start-screen tile."""
        ev = [self._eval(x["equipment_id"], x["key"]) for x in self.slots()]
        return sum(1 for v in ev if not v["valid"]), len(ev)

    @staticmethod
    def _blank_sel():
        return {"model": "", "module": "", "conn": [], "torque": False}

    # ---------- files ----------
    def _load(self):
        if not self.path.exists():
            shutil.copy(self.folder / "default_ecal_setup.json", self.path)
        d = store.read_json(self.path, None)
        if not isinstance(d, dict) or not isinstance(d.get("active"), dict):
            default = store.read_json(self.folder / "default_ecal_setup.json", {"active": {}, "masterlist": []})
            return default, "setup_ecal.json has a mistake - using the default (%s)" % self.path
        d.setdefault("masterlist", [])
        if not d["active"].get("TORQUE"):                      # older files kept one entry per torque tester model
            d["active"]["TORQUE"] = next((d["active"][t] for t in self.cat.get("torque", []) if d["active"].get(t)), "")
        return d, None

    def publish(self):
        """Describe this product to the start screen (models and module IDs are searchable)."""
        mods = {}
        for model, m in self.cat["models"].items():
            for mod in m["modules"]:
                mods.setdefault(mod, []).append(model)
        mods = [{"id": mod, "model": owners[0] if len(owners) == 1 else "",
                 "desc": self._mod_text(mod, self.cat["modules"][mod]) + " - " + ", ".join(owners)} for mod, owners in mods.items()]
        p = {"models": list(self.cat["models"]), "modules": mods}
        p["mdesc"] = {k: v.get("description", "") for k, v in self.cat["models"].items()}
        return p

    def open(self, model, module):
        """The start screen opened this product, possibly with a Model ID / Module ID typed there."""
        if model or module:
            self.set_selection(model, module, [], False)

    def recent_item(self):
        """What the start screen's Recent row stores for this product, or None."""
        s = self._sel_info()
        if not (s["model"] or s["module"]):
            return None
        return {"model": s["model"], "module": s["module"], "label": " / ".join(x for x in (s["model"], s["module"]) if x)}

    def rpc(self, name, *a):
        """Calls from this product's screen (shell.call(name, ...))."""
        if name == "catalog":
            return self.catalog_view()
        if name == "select":
            return self.set_selection(*a)
        raise ValueError("Unknown call %s" % name)

    # ---------- catalog ----------
    def _mod_text(self, mod, mi, model=""):
        if mi["type"] == "Mixed":
            return "Mixed connectors (%s) - %d ports" % ("/".join(mi["connectors"]), mi["ports"])
        conn = next((c for c, k in self.cat["connectors"].items() if k == mi.get("kit")), "?")
        return "Opt %s - Fixed %s (%s) - %d ports" % ("/".join(mi["options"]), conn, mi.get("kit"), mi["ports"])

    def catalog_view(self):
        out = {"models": [], "connectors": self.cat["connectors"], "torque": self.cat["torque"],
               "max": self.cat.get("max_connector_types", {"2": 2, "4": 3})}
        for model, m in self.cat["models"].items():
            mods = []
            for mod in m["modules"]:
                mi = self.cat["modules"][mod]
                mods.append({"id": mod, "type": mi["type"], "ports": mi["ports"], "opt": "/".join(mi["options"]) if mi["type"] == "Fixed" else "Mixed",
                             "text": self._mod_text(mod, mi, model), "connectors": mi.get("connectors", []), "kit": mi.get("kit", "")})
            out["models"].append({"id": model, "desc": m.get("description", ""), "ports": m["ports"], "modules": mods})
        return out

    def _models_of_module(self, mod):
        return [k for k, m in self.cat["models"].items() if mod in m["modules"]]

    # ---------- slots / ETEs ----------
    def slots(self):
        c = self.cat
        s = [{"key": m, "label": "Vector Network Analyzer", "group": "VNA", "model": m, "models": [m]} for m in c["vna"]]
        for conn, kit in c["connectors"].items():
            s.append({"key": kit, "label": c.get("kit_names", {}).get(kit, conn + " Cal Kit"), "group": "Cal kits", "model": kit, "models": [kit]})
        s.append({"key": "TORQUE", "label": "Torque Tester", "group": "Torque tester", "model": "", "models": list(c["torque"])})
        for x in s:
            x["equipment_id"] = _up(self.setup["active"].get(x["key"], ""))
        return s

    def _with_due(self, slots):
        for x in slots:
            r = self.svc._eval(x["equipment_id"]) if x["equipment_id"] else None
            x["due"], x["days_left"], x["status"] = (r["due"], r["days_left"], r["status"]) if r else (None, None, "Not set up")
        return slots

    def ids(self):
        return [x["equipment_id"] for x in self.slots() if x["equipment_id"]]

    def master_ids(self):
        return [_up(m.get("equipment_id")) for m in self.setup.get("masterlist") or [] if m.get("equipment_id")]

    def demo_models(self):
        out = {_up(m.get("equipment_id")): str(m.get("model") or "") for m in self.setup.get("masterlist") or []}
        for x in self.slots():
            if x["equipment_id"]:
                out.setdefault(x["equipment_id"], x["model"] or x["models"][0])
        return out

    # ---------- selection / job ----------
    def _sel_info(self):
        s, c = self.sel, self.cat
        model = self._norm_models.get(_up(s["model"]), "")
        mod = self._norm_modules.get(_up(s["module"]), "")
        mi = c["modules"].get(mod)
        if model and mod and mod not in c["models"][model]["modules"]:
            mi = None
        info = {"model": model or s["model"], "module": mod or s["module"], "model_ok": bool(model), "module_ok": bool(mi),
                "type": mi["type"] if mi else "", "ports": mi["ports"] if mi else (c["models"][model]["ports"] if model else 0),
                "allowed": mi.get("connectors", []) if mi else [], "max": 0, "conn": [], "kits": [], "text": ""}
        info["owners"] = self._models_of_module(mod) if mi else []
        info["model_locked"] = bool(mi and info["model"] and info["model_ok"] and len(info["owners"]) == 1)
        if mi:
            info["text"] = self._mod_text(mod, mi)
            if mi["type"] == "Fixed":
                info["kits"] = [mi["kit"]]
            else:
                info["max"] = min(len(info["allowed"]), int(c.get("max_connector_types", {}).get(str(mi["ports"]), 2)))
                info["conn"] = [x for x in s["conn"] if x in info["allowed"]][:info["max"]]
                info["kits"] = [c["connectors"][x] for x in c["connectors"] if x in info["conn"]]   # catalog order
        return info

    def set_selection(self, model, module, conn, torque):
        with self.svc.lock:
            self.sel = {"model": str(model or ""), "module": str(module or ""), "conn": [str(x) for x in (conn or [])],
                        "torque": bool(torque)}
            m = self._norm_models.get(_up(self.sel["model"]))
            mod = self._norm_modules.get(_up(self.sel["module"]))
            if mod and not m:                                 # a module ID typed first: fill in the model when it is unambiguous
                owners = self._models_of_module(mod)
                if len(owners) == 1:
                    self.sel["model"] = owners[0]
            m = self._norm_models.get(_up(self.sel["model"]))
            if m:
                self.sel["model"] = m
                mods = self.cat["models"][m]["modules"]
                if mod and mod not in mods:
                    self.sel["module"] = ""                   # module belongs to another model
                elif not mod and len(mods) == 1:
                    self.sel["module"] = mods[0]
            if mod and (not m or mod in self.cat["models"][m]["modules"]):
                self.sel["module"] = mod
            mi = self.cat["modules"].get(self._norm_modules.get(_up(self.sel["module"]), ""))
            if mi and mi["type"] == "Mixed" and len(mi["connectors"]) == 1:
                self.sel["conn"] = list(mi["connectors"])       # only one connector type is possible
            return self._sel_info()

    def set_job(self, so, serial, result):
        with self.svc.lock:
            self.job = {"so": _up(so), "serial": _up(serial), "result": result if result in logic.RESULT_TYPES else ""}
            return self._job_view()

    def _job_errors(self):
        j, i, e = self.job, self._sel_info(), {}
        if not re.match(SO_RE_TXT, j["so"]):
            e["so"] = "Service Order: WO-######### or SO#########"
        if not re.match(SERIAL_RE_TXT, j["serial"]):
            e["serial"] = "Serial # must be 10 letters/digits"
        if j["result"] not in logic.RESULT_TYPES:
            e["result"] = "Choose a result type"
        if not i["model_ok"]:
            e["model"] = "Choose the module model"
        elif not i["module_ok"]:
            e["module"] = "Choose the module ID"
        elif i["type"] == "Mixed" and not i["conn"]:
            e["conn"] = "Choose the connector type(s) installed"
        if self.sel["torque"] and not self._by_key()["TORQUE"]["equipment_id"]:
            e["tt"] = "No torque tester is set up - choose one in Setup"
        return e

    def _job_view(self):
        e = self._job_errors()
        return dict(self.job, ok=not e, errors=e)

    # ---------- required rows ----------
    def _by_key(self):
        return {x["key"]: x for x in self.slots()}

    def required(self):
        """[(label, key, scan_needed)] in report order: VNA, torque tester, cal kits."""
        by_key = self._by_key()
        out = [(by_key[k]["label"], k, True) for k in self.cat["vna"]]
        if self.sel["torque"]:
            out.append((by_key["TORQUE"]["label"], "TORQUE", False))
        out += [(by_key[k]["label"], k, True) for k in self._sel_info()["kits"]]
        return out

    def _eval(self, eid, key=""):
        if not eid:
            r = logic.evaluate("", None)
            r.update(status="Not set up", reason="Choose the active %s in Setup" % ("torque tester" if key == "TORQUE" else key))
            return r
        return self.svc._eval(eid)

    def _alt(self, models, active):
        """Another unit of the same model(s) that is valid - shown when the active one is not."""
        want = {logic.norm_model(m) for m in models}
        for m in self.setup.get("masterlist") or []:
            e = _up(m.get("equipment_id"))
            if e and e != active and logic.norm_model(m.get("model")) in want and self._eval(e)["valid"]:
                return e
        return ""

    def rows(self):
        out, by_key = [], self._by_key()
        for label, key, scan in self.required():
            eid = by_key[key]["equipment_id"]
            r = self._eval(eid, key)
            r["slot"], r["no_scan"], r["key"] = label, not scan, key
            r["verified"] = r["valid"] and (not scan or eid in self.verified)
            r["hint"] = ""
            if not r["valid"]:
                alt = self._alt(by_key[key]["models"], eid)
                r["hint"] = ("%s is valid - change the active %s in Setup" % (alt, by_key[key]["model"] or "torque tester")) if alt else ""
            out.append(r)
        return out

    # ---------- state ----------
    def _check_reuse(self):
        r = self.reuse
        if r and r["day"] != date.today().isoformat():
            self.reuse = None
            self.verified = set()
            self.job = {"so": "", "serial": "", "result": ""}

    def state(self):
        with self.svc.lock:
            self._check_reuse()
            rows = self.rows()
            ev = {x["key"]: self._eval(x["equipment_id"], x["key"]) for x in self.slots()}
            need = [r for r in rows if not r["no_scan"]]
            bad = [r["equipment_id"] for r in rows if not r["verified"]]
            tq = self._by_key()["TORQUE"]["equipment_id"]
            tr = self._eval(tq, "TORQUE") if tq else None
            return {"product": "ecal", "sel": self._sel_info(), "torque": self.sel["torque"],
                    "torque_active": {"id": tq, "model": (tr or {}).get("model", ""), "status": (tr or {}).get("status", "Not set up")},
                    "job": self._job_view(), "rows": rows, "verified": sum(1 for r in rows if r["verified"]), "total": len(rows),
                    "need_scan": len(need), "scanned": sum(1 for r in need if r["verified"]),
                    "all_verified": bool(rows) and all(r["verified"] for r in rows),
                    "reuse": None if not self.reuse else {"since": self.reuse["since"], "bad": bad},
                    "kpi": {"req_ready": sum(1 for r in rows if r["valid"]), "req_total": len(rows),
                            "act_ready": sum(1 for v in ev.values() if v["valid"]), "act_total": len(ev),
                            "expiring": sum(1 for r in rows if r["status"] == "Expiring Soon"),     # the ETEs this module needs
                            "expired": sum(1 for r in rows if r["status"] == "Expired"),
                            "sent": sum(1 for r in rows if r["status"] == "Sent for Cal")}}

    # ---------- scanning ----------
    def scan(self, code):
        code = logic.normalise_scan(code)
        with self.svc.lock:
            if not code:
                return {"kind": "ignore"}
            if self.svc.mode() == "nologin":
                return {"kind": "no_login", "message": self.svc.no_login_msg()}
            if self._job_errors():
                return {"kind": "need_job", "message": "Fill in the module, serial number, Service Order and result type first"}
            rows = self.rows()
            hit = [r for r in rows if r["equipment_id"].upper() == code]
            if not hit:
                return {"kind": "not_in_station", "code": code, "message": self._why_not(code, rows)}
            r = hit[0]
            if r["no_scan"]:
                return {"kind": "dup", "code": code, "message": "%s is a torque tester: no scan needed (it is listed on the report)" % code}
            if r["verified"]:
                return {"kind": "dup", "code": code, "message": "%s is already verified" % code}
            if not r["valid"]:
                return {"kind": "invalid", "code": code, "message": "%s cannot be verified: %s" % (code, r["reason"] or r["status"])}
            self.verified.add(r["equipment_id"])
            return {"kind": "verified", "code": code, "message": "%s verified (%s)" % (code, r["slot"])}

    def _why_not(self, code, rows):
        by_key = self._by_key()
        for m in self.setup.get("masterlist") or []:
            if _up(m.get("equipment_id")) == code:
                key = next((k for k, v in by_key.items() if logic.norm_model(m.get("model")) in {logic.norm_model(x) for x in v["models"]}), "")
                if key and any(r["key"] == key for r in rows):
                    return "%s is a %s but the active one is %s. Change it in Setup first." % (code, m.get("model") or key, by_key[key]["equipment_id"] or "not set")
                return "%s (%s) is not needed for this module" % (code, m.get("model") or "ETE")
        return "%s is not part of the ECal setup. Add it in Setup." % code

    def new_session(self):
        """Everything is cleared: module choice, connectors, torque, job fields and scans."""
        self.reuse = None
        self.verified = set()
        self.sel = self._blank_sel()
        self.job = {"so": "", "serial": "", "result": ""}

    def reset(self):
        self.reuse = None
        self.verified = set()

    def reuse_session(self):
        """Next DUT: keep the module choice, clear serial/SO/result, refresh MARS and re-verify every ETE that is still valid."""
        import time
        svc = self.svc
        with svc.lock:
            if not (self.rows() and svc.last_report):
                raise ValueError("Nothing to re-use yet")
        deadline = time.time() + 60
        while True:
            with svc.lock:
                if not svc.refreshing:
                    svc.refreshing, svc.fetch_error = True, None
                    break
            if time.time() > deadline:
                raise RuntimeError("MARS refresh is still running, try again")
            time.sleep(0.3)
        svc._do_refresh()
        with svc.lock:
            self.verified = {x for x in self.verified if self._eval(x)["valid"]}
            self.job = {"so": "", "serial": "", "result": ""}
            self.reuse = {"day": date.today().isoformat(), "since": datetime.now().isoformat(timespec="seconds")}
            rows = self.rows()
            return {"total": len(rows), "verified": sum(1 for r in rows if r["verified"]), "fetch_error": svc.fetch_error}

    # ---------- report ----------
    def table(self):
        with self.svc.lock:
            rows = self.rows()
            if not (rows and all(r["verified"] for r in rows)):
                raise ValueError("Not every ETE is verified (or one is no longer valid)")
            if self._job_errors():
                raise ValueError("Complete the module, serial number, Service Order and result type")
            return [(r["model"], r["serial"], r["equipment_id"], logic.fmt_due(r["due"])) for r in rows]

    def unit_model(self):
        return self._sel_info()["model"]

    def procedure(self):
        return self.setup.get("procedure") or PROCEDURE

    def file_tag(self):
        return "ECAL"

    # ---------- setup page ----------
    def _master(self):
        rows = {}
        for m in self.setup.get("masterlist") or []:
            e = _up(m.get("equipment_id"))
            if e:
                rows[e] = {"equipment_id": e, "model": str(m.get("model") or "").strip(), "serial": str(m.get("serial") or ""), "set": ""}
        for e in self.ids():
            rows.setdefault(e, {"equipment_id": e, "model": "", "serial": "", "set": ""})
        for e, m in rows.items():
            r = self.svc._eval(e)
            m["description"] = r["description"] or r["model"] or ""
            m["serial"] = m["serial"] or r["serial"] or ""
            m["status"] = r["status"]
            m["due"], m["days_left"] = r["due"], r["days_left"]
        return rows

    def get_setup(self):
        with self.svc.lock:
            return {"slots": self._with_due(self.slots()), "master": sorted(self._master().values(), key=lambda m: m["equipment_id"])}

    def save_setup(self, data):
        with self.svc.lock:
            master, slots = self._master(), self.slots()
        new, errors, active = data.get("active", {}), [], {}
        for s in slots:
            eid, want = _up(new.get(s["key"])), {logic.norm_model(x) for x in s["models"]}
            if not eid:
                if any(logic.norm_model(m["model"]) in want for m in master.values()):
                    errors.append("%s: choose the active %s" % (s["label"], s["model"] or "unit"))
            elif eid not in master:
                errors.append("%s: %s is not in the masterlist" % (s["label"], eid))
            elif master[eid]["model"] and logic.norm_model(master[eid]["model"]) not in want:
                errors.append("%s: %s is a %s, expected %s" % (s["label"], eid, master[eid]["model"], " or ".join(s["models"])))
            active[s["key"]] = eid
        if errors:
            return {"ok": False, "errors": errors}
        with self.svc.lock:
            if self.path.exists():
                shutil.copy(self.path, self.svc.dir / "setup_ecal.json.bak")
            self.setup["active"] = active
            store.write_json(self.path, self.setup)
            self.error = None
            self.reuse = None
            self.verified &= set(self.ids())
        self.svc.refresh()
        return {"ok": True, "warnings": []}

    def current_masterlist(self):
        return self.setup.get("masterlist") or []

    def active_ids(self):
        return self.ids()

    def apply_masterlist(self, rows):
        with self.svc.lock:
            if self.path.exists():
                shutil.copy(self.path, self.svc.dir / "setup_ecal.json.bak")
            self.setup["masterlist"] = rows
            store.write_json(self.path, self.setup)
        self.svc.refresh()
        return {"ok": True, "count": len(rows), "sets": 0}

    def import_masterlist(self, path):
        import masterlist
        rows = masterlist.read_workbook(path)
        with self.svc.lock:
            if self.path.exists():
                shutil.copy(self.path, self.svc.dir / "setup_ecal.json.bak")
            self.setup["masterlist"] = rows
            store.write_json(self.path, self.setup)
        self.svc.refresh()
        return {"ok": True, "count": len(rows), "sets": 0}

    def ete_list(self):
        with self.svc.lock:
            master, used = self._master(), {}
            for s in self.slots():
                if s["equipment_id"]:
                    used.setdefault(s["equipment_id"], []).append("ECal: " + s["label"])
            out = []
            for e, m in master.items():
                r = self.svc._eval(e)
                out.append({"equipment_id": e, "model": m["model"] or r["model"], "description": m["description"], "serial": m["serial"],
                            "set": "", "used_in": used.get(e, []), "whereabout": r["whereabout"], "due": r["due"],
                            "days_left": r["days_left"], "status": r["status"], "reason": r["reason"]})
            out.sort(key=lambda x: x["equipment_id"])
            return {"rows": out, "fetched_at": self.svc.cache.get("fetched_at")}


EcalPack = Pack
