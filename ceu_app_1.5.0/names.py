"""Short name for the start-screen greeting, looked up from the Windows login name.
names.json maps login name -> short name, e.g. {"ziyanang": "Jacky"}. Lookup is not case-sensitive.
Sources, first hit wins: %APPDATA%\\CEUTool\\names.json (this PC) -> the copy in the shared release folder
(downloaded to this PC at start-up, so an edit there reaches every PC without a new build) -> the bundled default.
No match: "Cal AE"."""
import getpass, logging, os, shutil
import store

FALLBACK = "Cal AE"


def login_name():
    try:
        u = getpass.getuser()
    except Exception:
        u = os.environ.get("USERNAME") or ""
    return u.split("\\")[-1].strip().lower()


def upn():
    """User principal name (usually looks like the e-mail address on a domain PC), or ''."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        n, buf = ctypes.c_ulong(256), ctypes.create_unicode_buffer(256)
        if ctypes.windll.secur32.GetUserNameExW(8, buf, ctypes.byref(n)):      # NameUserPrincipal
            return buf.value.strip().lower()
    except Exception:
        logging.info("could not read the user principal name", exc_info=True)
    return ""


def sync(release_folder, data_dir):
    """Copy names.json from the shared release folder to this PC (silently ignores an unreachable share)."""
    try:
        src = os.path.join(release_folder, "names.json")
        if os.path.isfile(src) and isinstance(store.read_json(src, None), dict):
            shutil.copyfile(src, os.path.join(str(data_dir), "names.json"))
    except Exception:
        logging.info("names.json not synced", exc_info=True)


def problem(data_dir):
    """Text for the red banner when this PC's names.json cannot be read, else ''."""
    p = os.path.join(str(data_dir), "names.json")
    if not os.path.isfile(p):
        return ""
    if isinstance(store.read_json(p, None), dict):
        return ""
    return "names.json has a mistake - greeting names are ignored  [%s]" % p


def lookup(data_dir, setup=None):
    """greeting_name in setup.json wins; then the login name; then the UPN/e-mail; then Cal AE."""
    forced = str((setup or {}).get("greeting_name") or "").strip()
    if forced:
        return forced
    keys = [k for k in (login_name(), upn()) if k]
    for path in (os.path.join(str(data_dir), "names.json"), store.resource_path("default_names.json")):
        d = store.read_json(path, None)
        if isinstance(d, dict):
            m = {str(k).strip().lower(): str(v).strip() for k, v in d.items() if not str(k).startswith("_")}
            for k in keys:
                if m.get(k):
                    return m[k]
    return FALLBACK
