"""Update check and self-update from a release folder (a shared drive path, set as "update_path" in setup.json).

Release folder layout (made by release.py):
    latest.json          {"version": "1.0.1", "file": "CEUTool_1.0.1.exe", "sha256": "...", "notes": "...", "min_version": "1.0.0"}
    CEUTool_1.0.1.exe    every released build
    CEUTool.exe          copy of the newest build, used by install.bat for first installs
"""
import hashlib, json, logging, os, shutil, subprocess, sys
from pathlib import Path


def vtuple(v):
    parts = []
    for p in str(v or "0").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))


# Shared release folder. A PC can override it with "update_path" in setup.json (or the CEU_UPDATE_PATH variable).
DEFAULT_UPDATE_PATH = r"\\romulus\v4\PGLab\Callab\Software\CEU_Reporting_Tool"


def release_dir(setup):
    p = os.environ.get("CEU_UPDATE_PATH") or (setup or {}).get("update_path") or DEFAULT_UPDATE_PATH
    return str(p).strip()


def check(folder, current):
    """-> {"state": "disabled|unreachable|current|available", ...}. Never raises."""
    if not folder:
        return {"state": "disabled"}
    try:
        with open(Path(folder) / "latest.json", encoding="utf-8-sig") as f:
            info = json.load(f)
        latest = str(info["version"])
    except Exception as e:
        logging.info("update check failed: %s", e)
        return {"state": "unreachable", "error": "%s: %s" % (type(e).__name__, e)}
    required = vtuple(current) < vtuple(info.get("min_version") or "0")
    if vtuple(latest) > vtuple(current):
        return {"state": "available", "version": latest, "notes": str(info.get("notes") or ""),
                "file": str(info.get("file") or ""), "sha256": str(info.get("sha256") or ""), "required": required}
    return {"state": "current", "version": latest}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cleanup_old(exe=None):
    """Remove the previous build left behind by the last update."""
    exe = Path(exe or sys.executable)
    old = exe.with_name(exe.stem + ".old")
    try:
        if old.exists():
            old.unlink()
    except OSError:
        pass


def apply(folder, info, exe=None, relaunch=True):
    """Copy the new exe next to the running one, verify it, swap them, start the new one.
    Windows cannot overwrite a running exe but can rename it, so: running exe -> .old, new -> CEUTool.exe."""
    exe = Path(exe or sys.executable)
    if not getattr(sys, "frozen", False) and exe == Path(sys.executable):
        raise RuntimeError("Updates only work in the built CEUTool.exe, not when running from Python")
    if not info.get("file"):
        raise RuntimeError("latest.json has no file name")
    src = Path(folder) / info["file"]
    new = exe.with_name(exe.stem + ".new")
    old = exe.with_name(exe.stem + ".old")
    try:
        shutil.copyfile(src, new)
        if info.get("sha256") and _sha256(new).lower() != info["sha256"].lower():
            raise RuntimeError("The downloaded file is damaged (checksum does not match). Nothing was changed.")
        if old.exists():
            old.unlink()
        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)               # put the old build back
            raise
    except Exception:
        try:
            if new.exists():
                new.unlink()
        except OSError:
            pass
        raise
    if relaunch:
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0     # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([str(exe)], close_fds=True, creationflags=flags)
