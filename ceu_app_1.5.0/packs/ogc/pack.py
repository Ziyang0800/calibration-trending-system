"""3458A OGC product pack (Station B-1 / B-2). Own setup file: %APPDATA%\\CEUTool\\setup_ogc.json.
On the first start it is made from the old setup.json of the shell (b1, sets, masterlist, procedure), so nothing is lost."""
import re, shutil, time
from datetime import datetime, date
from pathlib import Path

import logic, store

SO_RE = re.compile(r"^(WO-\d{4,}|SO\d{4,}(-\d+)?)$")   # Service Order: WO-012345617 or SO12345617
SERIAL_RE = re.compile(r"^[A-Z0-9]{10}$")             # 10-character unit serial, e.g. US28032151
PROCEDURE = "RMB, HP3458A (9000-0083), 3458A_OGC.MX.N1091"   # can be overridden by "procedure" in setup_ogc.json
UNIT_MODEL = "3458A"
norm = lambda t: re.sub(r"\s+", "", str(t or "")).upper()


def b1_rows(setup):
    return [(s["slot"], s["equipment_id"]) for s in setup["b1"]]


def set_by_num(setup, n):
    for s in setup["sets"]:
        if s["num"] == n:
            return s
    return None


def station_rows(setup, station, b2_set):
    """B-2 mirrors B-1 and adds the two Cal/Amp rows of the chosen Set."""
    rows = b1_rows(setup)
    if station == "B-2" and b2_set:
        s = set_by_num(setup, b2_set)
        if s:
            rows = rows + [("Calibrator (Set %d)" % b2_set, s["calibrator"]),
                           ("Amplifier (Set %d)" % b2_set, s["amplifier"])]
    return rows


def load_setup(d, folder):
    """-> (setup, error text). Made from the shell's old setup.json (or the bundled default) when there is no setup_ogc.json yet."""
    p = Path(d) / "setup_ogc.json"
    if not p.exists():
        legacy = store.read_json(Path(d) / "setup.json", {}) or {}
        if isinstance(legacy.get("b1"), list) and isinstance(legacy.get("sets"), list):
            store.write_json(p, {k: legacy[k] for k in ("procedure", "b1", "sets", "masterlist") if k in legacy})
        else:
            shutil.copy(Path(folder) / "default_setup.json", p)
    try:
        data = store.read_json_strict(p)
        if not isinstance(data.get("b1"), list) or not isinstance(data.get("sets"), list):
            raise ValueError('it needs a "b1" list and a "sets" list')
        for s in data["b1"]:
            s["equipment_id"], s["slot"]
        for s in data["sets"]:
            s["num"], s["calibrator"], s["amplifier"]
        return data, None
    except (KeyError, TypeError) as e:
        return {"b1": [], "sets": []}, "setup_ogc.json is missing a field %s  [%s]" % (e, p)
    except (ValueError, OSError) as e:
        return {"b1": [], "sets": []}, "setup_ogc.json has a mistake: %s  [%s]" % (e, p)


# ---------------------------------------------------------------------------
# Slot rules for Station B-1 (same mapping as the Excel "Validation List" sheet).
# Slot order is fixed, so rules are looked up by position. Each slot may only be filled by
# an ETE of one of the listed model numbers. Slots in a group must come from the same Set.
# ---------------------------------------------------------------------------
GROUP_LABELS = {"cal_amp": "Calibrator & Amplifier", "ac_div": "AC Dividers", "resistors": "Standard Resistors"}
_R = lambda models, group=None: {"models": models, "group": group}
SLOT_RULES = [
    _R(["FLU 5720A", "FLU 5730A"], "cal_amp"), _R(["FLU 5725A"], "cal_amp"),          # 1-2
    _R(["3458A"]),                                                                    # 3
    _R(["ET 100MV"], "ac_div"), _R(["ET 10MV"], "ac_div"),                            # 4-5
    _R(["L&N 4221B", "9334A-0.1"]),                                                   # 6   0.1 ohm: three units, so not grouped
    _R(["FLU 742A-1"], "resistors"), _R(["FLU 742A-10"], "resistors"),                # 7-8
    _R(["FLU 742A-100"], "resistors"), _R(["FLU 742A-1K"], "resistors"),              # 9-10
    _R(["ESI SR104"], "resistors"), _R(["FLU 742A-100K"], "resistors"),               # 11-12
    _R(["FLU 742A-1M"], "resistors"), _R(["FLU 742A-10M"], "resistors"),              # 13-14
    _R(["GUI 9334"], "resistors"), _R(["9334A-1G"], "resistors"),                     # 15-16
    _R(["33622A"]), _R(["FLU 5790A"]),                                                # 17-18
    _R(["FLU 732C", "FLU 732A"]),                                                     # 19
]


def slot_rules(b1):
    """Rules for the current setup (b1 = list of slot dicts), or empty rules if the slot count does not match
    the workbook layout. The two AC divider slots are matched by name, so their order does not matter."""
    n = len(b1)
    if n != len(SLOT_RULES):
        return [{"models": [], "group": None} for _ in range(n)]
    rules = [dict(r) for r in SLOT_RULES]
    for i in (3, 4):
        name = str(b1[i].get("slot", "")).replace(" ", "").lower()
        if "100mv" in name:
            rules[i] = _R(["ET 100MV"], "ac_div")
        elif "10mv" in name:
            rules[i] = _R(["ET 10MV"], "ac_div")
    return rules


class Pack:
    def __init__(self, svc, folder, manifest):
        self.svc, self.folder, self.manifest = svc, Path(folder), manifest
        self.setup, self.setup_error = load_setup(svc.dir, self.folder)
        self.station, self.b2_set, self.ack_b2 = "B-1", None, False
        self.reuse = None                                # "another DUT, same setup" session (in memory only)
        self.verified = {"B-1": set(), "B-2": set()}
        self.job = {"so": "", "serial": "", "result": ""}

    # ---------- start screen and refresh ----------
    def problems(self):
        return [self.setup_error] if self.setup_error else []
    def publish(self):
        return {"models": ["3458A"], "modules": [], "mdesc": {}}
    def all_ids(self):
        ids = [s["equipment_id"] for s in self.setup["b1"]]
        for s in self.setup["sets"]:
            ids += [s["calibrator"], s["amplifier"]]
        return list(dict.fromkeys(ids))
    def ids(self):
        return self.all_ids()
    def master_ids(self):
        return [norm(m.get("equipment_id")) for m in self.setup.get("masterlist") or [] if m.get("equipment_id")]
    def health(self):                                    # the active setup (B-1), not every spare Set
        ids = [x["equipment_id"] for x in self.setup["b1"]]
        return sum(1 for e in ids if not self._eval(e)["valid"]), len(ids)
    def demo_models(self):
        rules, out = self._rules(), {}
        for r, x in zip(rules, self.setup["b1"]):
            if r["models"]:
                out[x["equipment_id"]] = r["models"][0]
        for s in self.setup["sets"]:
            out.setdefault(s["calibrator"], "FLU 5720A")
            out.setdefault(s["amplifier"], "FLU 5725A")
        return out
    def open(self, model, module):
        pass
    def recent_item(self):
        return {"model": "", "module": "", "label": "3458A OGC"}
    def reminder_ids(self):                              # what is in use now: B-1 and the chosen B-2 Set
        ids = [x["equipment_id"] for x in self.setup["b1"]]
        if self.b2_set:
            s = set_by_num(self.setup, self.b2_set)
            ids += [s["calibrator"], s["amplifier"]] if s else []
        return ids
    def diag(self):
        return ["OGC setup: %d B-1 slots, %d sets, %d masterlist rows" % (len(self.setup.get("b1", [])), len(self.setup.get("sets", [])), len(self.setup.get("masterlist") or []))]
    def rpc(self, name, *a):
        if name == "sets": return self.sets()
        if name == "choose_set": return self.choose_set(int(a[0]))
        if name == "go_b1": return self.go_b1()
        if name == "need_warning": return not self.ack_b2
        if name == "ack_b2": self.ack_b2 = True; return True
        if name == "resolve_group": return self.resolve_group(*a)
        raise ValueError("Unknown call %s" % name)

    def _eval(self, eid):
        return self.svc._eval(eid)
    def _rules(self):
        return slot_rules(self.setup["b1"])

    # ---------- rows and state ----------
    def rows(self):
        out = []
        ver = self.verified[self.station]
        rules = self._rules()
        for i, (slot, eid) in enumerate(station_rows(self.setup, self.station, self.b2_set)):
            r = self._eval(eid)
            r["slot"], r["verified"] = slot, (eid in ver and r["valid"])   # an ETE that became invalid loses its tick
            r["hint"] = ""
            if not r["valid"] and i < len(rules) and rules[i]["models"]:   # B-1 slots: name a valid unit of the same model
                alt = self._alt(rules[i]["models"], eid)
                if alt:
                    r["hint"] = "%s is valid - change the active %s in Setup" % (alt, rules[i]["models"][0])
            out.append(r)
        return out

    def _alt(self, models, active):
        want, used = {logic.norm_model(m) for m in models}, set(self.all_ids())
        for m in self.setup.get("masterlist") or []:
            e = norm(m.get("equipment_id"))
            if e and e != active and e not in used and logic.norm_model(m.get("model")) in want and self._eval(e)["valid"]:
                return e
        return ""

    def state(self):
        svc = self.svc
        with svc.lock:
            self._check_reuse()
            rows = self.rows()
            ev = {e: self._eval(e) for e in self.all_ids()}
            b1 = [ev[s["equipment_id"]] for s in self.setup["b1"]]
            b2 = None
            if self.b2_set:
                s = set_by_num(self.setup, self.b2_set)
                b2 = [ev[s["calibrator"]], ev[s["amplifier"]]]
            return {
                "product": "ogc", "station": self.station, "b2_set": self.b2_set, "ack_b2": self.ack_b2,
                "job": self._job_view(), "reuse": self._reuse_view(rows), "rows": rows,
                "verified": sum(1 for r in rows if r["verified"]), "total": len(rows),
                "need_scan": len(rows), "scanned": sum(1 for r in rows if r["verified"]),
                "all_verified": bool(rows) and all(r["verified"] for r in rows),
                "kpi": {
                    "b1_ready": sum(1 for r in b1 if r["valid"]), "b1_total": len(b1),
                    "b2_ready": None if b2 is None else sum(1 for r in b2 if r["valid"]),
                    "expiring": sum(1 for r in rows if r["status"] == "Expiring Soon"),      # this station only, not every Set in the setup
                    "expired": sum(1 for r in rows if r["status"] == "Expired"),
                    "sent": sum(1 for r in rows if r["status"] == "Sent for Cal"),
                    "other": sum(1 for r in rows if r["status"] in ("Not found", "Not in use", "No due date")),
                },
            }

    def sets(self):
        svc = self.svc
        with svc.lock:
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
                            "last_used": svc.app.get("last_set") == s["num"]})
            return out

    # ---------- setup editor ----------
    def _master(self):
        """Masterlist rows: [{equipment_id, model, serial, set, description, status}]."""
        rows = {}
        for m in self.setup.get("masterlist") or []:
            eid = norm(m.get("equipment_id"))
            if eid:
                rows[eid] = {"equipment_id": eid, "model": str(m.get("model") or "").strip(), "serial": str(m.get("serial") or ""), "set": str(m.get("set") or "").strip()}
        for e in self.all_ids():
            rows.setdefault(e, {"equipment_id": e, "model": "", "serial": "", "set": ""})
        for e, m in rows.items():
            r = self._eval(e)
            m["description"] = r["description"] or r["model"] or ""
            m["serial"] = m["serial"] or r["serial"] or ""
            m["status"] = r["status"]
            m["due"], m["days_left"] = r["due"], r["days_left"]
        return rows

    def get_setup(self):
        with self.svc.lock:
            master = self._master()
            return {"b1": [dict(x) for x in self.setup["b1"]], "sets": [dict(x) for x in self.setup["sets"]],
                    "rules": self._rules(), "group_labels": GROUP_LABELS,
                    "master": sorted(master.values(), key=lambda m: m["equipment_id"])}

    def resolve_group(self, idx, eid):
        """The ETE in slot idx was changed to eid. If the slot belongs to a group (Calibrator/Amplifier,
        AC Dividers, Standard Resistors) the rest of the group must come from the same Set."""
        idx, eid = int(idx), norm(eid)
        with self.svc.lock:
            rules, master = self._rules(), self._master()
            g = rules[idx]["group"] if 0 <= idx < len(rules) else None
            out = {"group": GROUP_LABELS.get(g, ""), "set": "", "changes": [], "missing": []}
            if not g or eid not in master:
                return out
            st = master[eid]["set"]
            out["set"] = st
            if not st:
                return out
            for j, r in enumerate(rules):
                if j == idx or r["group"] != g:
                    continue
                want = {logic.norm_model(x) for x in r["models"]}
                cands = sorted(m["equipment_id"] for m in master.values() if m["set"] == st and logic.norm_model(m["model"]) in want)
                if cands:
                    out["changes"].append({"index": j, "equipment_id": cands[0]})
                else:
                    out["missing"].append(self.setup["b1"][j]["slot"])
            return out

    def _save(self):
        p = self.svc.dir / "setup_ogc.json"
        if p.exists():
            shutil.copy(p, self.svc.dir / "setup_ogc.json.bak")             # keep the previous version
        store.write_json(p, self.setup)

    def save_setup(self, data):
        """Slots are fixed: only the Equipment ID of each B-1 slot can change. The B-2 Sets are display only."""
        errors, warnings, b1 = [], [], []
        svc = self.svc
        with svc.lock:
            master = self._master()
            cur_b1, cur_sets = [dict(x) for x in self.setup["b1"]], [dict(x) for x in self.setup["sets"]]
            rules = self._rules()
        known = set(master)
        new_b1 = data.get("b1", [])
        if len(new_b1) != len(cur_b1):
            return {"ok": False, "errors": ["The number of slots is fixed and cannot be changed"]}
        for i, (cur, x) in enumerate(zip(cur_b1, new_b1), 1):
            eid = norm(x.get("equipment_id"))
            if not eid:
                errors.append("B-1 slot %d (%s): choose an Equipment ID" % (i, cur["slot"]))
            elif eid not in known:
                errors.append("B-1 slot %d: %s is not in the masterlist" % (i, eid))
            else:
                mdl = master[eid]["model"]
                want = {logic.norm_model(m) for m in rules[i - 1]["models"]}
                if mdl and want and logic.norm_model(mdl) not in want:
                    errors.append("B-1 slot %d (%s): %s is a %s, expected %s" % (i, cur["slot"], eid, mdl, " or ".join(rules[i - 1]["models"])))
            b1.append({"slot": cur["slot"], "equipment_id": eid})
        ids = [x["equipment_id"] for x in b1 if x["equipment_id"]]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            errors.append("Duplicate Equipment ID in B-1: " + ", ".join(dups))
        for g, label in GROUP_LABELS.items():          # a group must come from one Set
            found = {master[b1[j]["equipment_id"]]["set"] for j, r in enumerate(rules) if r["group"] == g
                     and b1[j]["equipment_id"] in master and master[b1[j]["equipment_id"]]["set"]}
            if len(found) > 1:
                errors.append("%s mix Sets %s - they must all come from the same Set" % (label, ", ".join(sorted(found))))
        if errors:
            return {"ok": False, "errors": errors}
        with svc.lock:
            self.reuse = None
            self.setup["b1"], self.setup["sets"] = b1, cur_sets             # Station B-2 Sets are display only
            self._save()
            self.setup_error = None
            keep = set(self.all_ids())
            for st in self.verified:
                self.verified[st] &= keep
        svc.refresh()                                                       # fetch any new IDs from MARS
        return {"ok": True, "warnings": warnings}

    # ---------- ETE manager / masterlist ----------
    def ete_list(self):
        """Every ETE the app knows (masterlist + setup) with its MARS status and where it is used."""
        with self.svc.lock:
            master = self._master()
            used = {}
            for x in self.setup["b1"]:
                used.setdefault(x["equipment_id"], []).append("B-1: " + x["slot"])
            for s in self.setup["sets"]:
                used.setdefault(s["calibrator"], []).append("B-2 Set %d: Calibrator" % s["num"])
                used.setdefault(s["amplifier"], []).append("B-2 Set %d: Amplifier" % s["num"])
            out = []
            for e, m in master.items():
                r = self._eval(e)
                out.append({"equipment_id": e, "model": m["model"] or r["model"], "description": m["description"], "serial": m["serial"],
                            "set": m["set"], "used_in": used.get(e, []), "whereabout": r["whereabout"], "due": r["due"],
                            "days_left": r["days_left"], "status": r["status"], "reason": r["reason"]})
            out.sort(key=lambda x: x["equipment_id"])
            return {"rows": out, "fetched_at": self.svc.cache.get("fetched_at")}
    def current_masterlist(self):
        return self.setup.get("masterlist") or []
    def active_ids(self):
        return self.all_ids()
    def apply_masterlist(self, rows):
        with self.svc.lock:
            self.setup["masterlist"] = rows
            self._save()
        self.svc.refresh()
        return {"ok": True, "count": len(rows), "sets": len({r["set"] for r in rows if r["set"]})}

    # ---------- station / job / scanning ----------
    def need_warning(self):
        return not self.ack_b2
    def choose_set(self, num):
        svc = self.svc
        with svc.lock:
            s = next((x for x in self.sets() if x["num"] == num), None)
            if not s or not s["available"]:
                raise ValueError("Set %s is not available" % num)
            self.reuse = None
            self.b2_set, self.station = num, "B-2"
            self.verified["B-2"] = set()
            svc.app["last_set"] = num
            store.write_json(svc.dir / "state.json", svc.app)
    def go_b1(self):
        self.reuse = None
        self.station = "B-1"

    def _errors(self):
        j, e = self.job, {}
        if not SO_RE.match(j["so"]):
            e["so"] = "Service Order: WO-######### or SO#########"
        if not SERIAL_RE.match(j["serial"]):
            e["serial"] = "Serial # must be 10 letters/digits"
        if j["result"] not in logic.RESULT_TYPES:
            e["result"] = "Choose a result type"
        return e
    def _job_view(self):
        e = self._errors()
        return dict(self.job, ok=not e, errors=e)
    def set_job(self, so, serial, result):
        clean = lambda t: re.sub(r"\s+", "", t or "").upper()
        self.job = {"so": clean(so), "serial": clean(serial), "result": result if result in logic.RESULT_TYPES else ""}
        return self._job_view()

    def new_session(self):
        self.reuse = None
        self.verified[self.station] = set()
        self.job = {"so": "", "serial": "", "result": ""}
    def close(self):                                     # back to the start screen: everything is cleared
        self.reuse = None
        self.verified = {"B-1": set(), "B-2": set()}
        self.job = {"so": "", "serial": "", "result": ""}
        self.station, self.b2_set = "B-1", None
    def reset(self):
        self.reuse = None
        self.verified[self.station] = set()

    def scan(self, code):
        code = logic.normalise_scan(code)
        svc = self.svc
        with svc.lock:
            if not code:
                return {"kind": "ignore"}
            if svc.mode() == "nologin":
                return {"kind": "no_login", "message": svc.no_login_msg()}
            if self._errors():
                return {"kind": "need_job", "message": "Fill in the SO number, unit serial number and result type first"}
            rows = self.rows()
            match = [r for r in rows if r["equipment_id"].upper() == code]
            if not match:                                   # rule 3: must belong to this station
                return {"kind": "not_in_station", "code": code, "message": "%s is not part of Station %s" % (code, self.station)}
            r = match[0]
            if r["verified"]:
                return {"kind": "dup", "code": code, "message": "%s is already verified" % code}
            if not r["valid"]:                              # rules 1 and 2
                return {"kind": "invalid", "code": code, "message": "%s cannot be verified: %s" % (code, r["reason"] or r["status"])}
            self.verified[self.station].add(r["equipment_id"])
            return {"kind": "verified", "code": code, "message": "%s verified (%s)" % (code, r["slot"])}

    # ---------- another DUT on the same setup ----------
    def _check_reuse(self):
        """The reuse session ends on a new day, a station switch or a different B-2 Set."""
        r = self.reuse
        if r and (r["day"] != date.today().isoformat() or r["station"] != self.station or r["set"] != self.b2_set):
            self.reuse = None
            self.verified[r["station"]] = set()
            self.job = {"so": "", "serial": "", "result": ""}
    def _reuse_view(self, rows):
        r = self.reuse
        if not r:
            return None
        return {"since": r["since"], "bad": [x["equipment_id"] for x in rows if not x["verified"]]}
    def reuse_session(self):
        """Same setup, next DUT: clear the job fields, fetch MARS again and re-verify every ETE that is still valid."""
        svc = self.svc
        with svc.lock:
            if not (self.rows() and svc.last_report):
                raise ValueError("Nothing to re-use yet")
        deadline = time.time() + 60
        while True:                                      # wait for a refresh already under way
            with svc.lock:
                if not svc.refreshing:
                    svc.refreshing, svc.fetch_error = True, None
                    break
            if time.time() > deadline:
                raise RuntimeError("MARS refresh is still running, try again")
            time.sleep(0.3)
        svc._do_refresh()
        with svc.lock:
            rows = self.rows()
            ver = {r["equipment_id"] for r in rows if r["valid"]}
            self.verified[self.station] = ver
            self.job = {"so": "", "serial": "", "result": ""}
            self.reuse = {"day": date.today().isoformat(), "station": self.station, "set": self.b2_set,
                          "since": datetime.now().isoformat(timespec="seconds")}
            return {"total": len(rows), "verified": len(ver), "fetch_error": svc.fetch_error}

    # ---------- report ----------
    def table(self):
        with self.svc.lock:
            rows = self.rows()
            if not (rows and all(r["verified"] for r in rows)):
                raise ValueError("Not every ETE is verified (or one is no longer valid)")
            if self._errors():
                raise ValueError("Service Order, Serial # and Result Type are required")
            return [(r["model"], r["serial"], r["equipment_id"], logic.fmt_due(r["due"])) for r in rows]
    def unit_model(self): return UNIT_MODEL
    def procedure(self): return self.setup.get("procedure", PROCEDURE)
    def file_tag(self): return self.station
