"""MARS WebAPI client (based on your mars_client.py) plus demo data for offline use."""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

try:
    import requests
except ImportError:          # demo mode still works without it
    requests = None

BASE_URL = os.environ.get("MARS_BASE_URL", "https://mars.keysight.com")
TIMEOUT = 30
KEEP = ["Equipment_ID", "Model_No", "Serial_No", "Model_Description", "Equipment_Status",
        "Calibration_Status", "Cal_Due_Date_ISO", "Cal_Due_Date", "Cal_Due_Date_Local_DateOnly",
        "Current_Whereabout", "Placement_ID", "Placement_Description"]


class MarsClient:
    def __init__(self, user, password, base_url=BASE_URL):
        self.user, self.password = user, password
        self.base_url = base_url.rstrip("/")
        self.access_token = self.refresh_token = None
        self.expires_in, self.issued_at = 3600, 0
        self._lock = threading.Lock()

    def login(self):
        r = requests.post(self.base_url + "/webapi/auth/token",
                          headers={"USER": self.user, "PASSWORD": self.password}, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()["ret"]
        self.access_token, self.refresh_token = d["access_token"], d["refresh_token"]
        self.expires_in, self.issued_at = d.get("expires_in", 3600), time.time()

    def refresh(self):
        r = requests.post(self.base_url + "/webapi/auth/refresh",
                          headers={"USER": self.user, "REFRESH-TOKEN": self.refresh_token}, timeout=TIMEOUT)
        if r.status_code == 401:
            return self.login()
        r.raise_for_status()
        d = r.json()["ret"]
        self.access_token, self.expires_in, self.issued_at = d["access_token"], d.get("expires_in", 3600), time.time()

    def ensure_token(self):
        with self._lock:
            if self.access_token is None:
                self.login()
            elif time.time() - self.issued_at >= 0.8 * self.expires_in:
                self.refresh()

    def get(self, endpoint, **params):
        self.ensure_token()
        hdr = lambda: {"Authorization": "Bearer " + self.access_token}
        r = requests.get("%s/webapi/%s" % (self.base_url, endpoint), headers=hdr(), params=params, timeout=TIMEOUT)
        if r.status_code == 401:
            with self._lock:
                self.refresh()
            r = requests.get("%s/webapi/%s" % (self.base_url, endpoint), headers=hdr(), params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_equipment(self, equipment_id):
        return self.get("ExtractEquipmentList", equipment_id=equipment_id)


def _slim(rec):
    return {k: rec.get(k) for k in KEEP}


def fetch_many(client, ids):
    """Returns {id: slim record, or None if MARS has no record}. Raises if nothing could be fetched."""
    client.ensure_token()                       # log in once before the worker threads start
    out, errors = {}, []

    def one(eid):
        try:
            ret = client.get_equipment(eid).get("ret") or []
            match = [r for r in ret if str(r.get("Equipment_ID", "")).upper() == eid.upper()]
            return eid, (_slim(match[0]) if match else (_slim(ret[0]) if ret else None)), None
        except Exception as e:                  # one bad ID must not stop the rest
            return eid, None, e

    with ThreadPoolExecutor(max_workers=4) as pool:
        for eid, rec, err in pool.map(one, ids):
            if err is not None:
                errors.append(err)
            else:
                out[eid] = rec
    if errors and not out:
        raise errors[0]
    return out


# ---- credentials: environment, then mars_account.json bundled into the exe, then Windows Credential Manager
SOURCE = None


def load_credentials():
    global SOURCE
    u, p = os.environ.get("MARS_USER"), os.environ.get("MARS_PASSWORD")
    if u and p:
        SOURCE = "env"
        return (u, p)
    try:                                               # bundled at build time by build_exe.bat
        import json
        from store import resource_path
        with open(resource_path("mars_account.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
        if d.get("user") and d.get("password"):
            SOURCE = "embedded"
            return (d["user"], d["password"])
    except (OSError, ValueError):
        pass
    try:
        import keyring
        u, p = keyring.get_password("CEUTool", "user"), keyring.get_password("CEUTool", "password")
        if u and p:
            SOURCE = "keyring"
            return (u, p)
    except Exception:
        pass
    return None


def save_credentials(user, password):
    try:
        import keyring
        keyring.set_password("CEUTool", "user", user)
        keyring.set_password("CEUTool", "password", password)
        return True
    except Exception:
        return False


def demo_records(ids, models=None):
    """Fake MARS data so the app runs without a login. Matches the default_setup.json demo IDs."""
    today = date.today()
    out = {}
    for i in ids:
        out[i] = {"Equipment_ID": i, "Model_No": (models or {}).get(i, "DEMO-%s" % i[-3:]), "Serial_No": "S" + i[-4:],
                  "Model_Description": "Demo equipment", "Current_Whereabout": "INU",
                  "Cal_Due_Date_ISO": (today + timedelta(days=200)).isoformat() + "T10:16:56"}
    if "PN010005" in out:
        out["PN010005"]["Cal_Due_Date_ISO"] = (today + timedelta(days=12)).isoformat() + "T10:16:56"
    if "PN010009" in out:
        out["PN010009"]["Cal_Due_Date_ISO"] = (today - timedelta(days=3)).isoformat() + "T10:16:56"
    if "PN020003" in out:
        out["PN020003"]["Current_Whereabout"] = "RCV"
    return out
