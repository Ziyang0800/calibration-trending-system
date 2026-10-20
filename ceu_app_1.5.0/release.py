"""Publish dist\\CEUTool.exe to the release folder.

  python release.py "\\\\server\\share\\CEUTool" --notes "What changed" [--min-version 1.0.0]

Leave the folder out to use the built-in shared release folder (DEFAULT_UPDATE_PATH in updater.py).
--min-version makes every older copy update before it can be used (use it when validation rules change).
"""
import argparse, hashlib, json, shutil, sys
from pathlib import Path
from version import __version__

ap = argparse.ArgumentParser()
ap.add_argument("folder", nargs="?")
ap.add_argument("--notes", default="")
ap.add_argument("--min-version", default="")
ap.add_argument("--allow-no-account", action="store_true", help="release an exe that has no built-in MARS account")
a = ap.parse_args()

folder = a.folder
if not folder:
    from updater import DEFAULT_UPDATE_PATH
    folder = DEFAULT_UPDATE_PATH
exe = Path("dist/CEUTool.exe")
if not exe.exists():
    sys.exit("dist\\CEUTool.exe not found - run build_exe.bat first")
info = Path("dist/build_info.txt")
if not a.allow_no_account and not (info.exists() and "embedded_account=yes" in info.read_text()):
    sys.exit("This build has no built-in MARS account (put mars_account.json next to build_exe.bat and rebuild),\n"
             "or run release.py with --allow-no-account if that is intended.")
dst = Path(folder)
dst.mkdir(parents=True, exist_ok=True)
name = "CEUTool_%s.exe" % __version__
if (dst / name).exists():
    sys.exit("%s already exists in the release folder. Raise the version in version.py first." % name)
digest = hashlib.sha256(exe.read_bytes()).hexdigest()
shutil.copyfile(exe, dst / name)
shutil.copyfile(exe, dst / "CEUTool.exe")
if Path("install.bat").exists():
    shutil.copyfile("install.bat", dst / "install.bat")
data = {"version": __version__, "file": name, "sha256": digest, "notes": a.notes, "min_version": a.min_version or ""}
(dst / "latest.json").write_text(json.dumps(data, indent=2), encoding="utf-8")      # written last: the release goes live now
print("Released", name, "to", dst)
