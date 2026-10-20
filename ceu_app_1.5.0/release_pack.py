"""Publish one product pack to the release folder, without touching the exe or any other product.

  python release_pack.py packs\\ecal --notes "New 85097C module"                    release to everyone
  python release_pack.py packs\\ecal --notes "..." --pilot-pcs PC123,PC456          pilot ring first (also --pilot-users login1,login2)
  python release_pack.py ecal --promote                                              pilot version -> everyone
  python release_pack.py ecal --rollback 1.0.0                                       everyone goes back to an older released version
  python release_pack.py ecal --list                                                 show what is released

Leave --share out to use the built-in shared release folder (updater.DEFAULT_UPDATE_PATH, or CEU_UPDATE_PATH).
Layout:  <share>\\packs\\<id>\\latest.json  and  <id>_<version>.zip   (latest.json is written last: that is the moment it goes live).
PCs pick it up at the next start-up / 45-minute check and run it after a restart of the app."""
import argparse, hashlib, json, os, sys, zipfile
from pathlib import Path

import plugins

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "tests"}
SKIP_SUFFIX = {".pyc", ".pyo", ".bak", ".tmp"}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _latest(d):
    p = d / "latest.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def _write(d, info):
    (d / "latest.json").write_text(json.dumps(info, indent=2), encoding="utf-8")        # last: now it is live


def make_zip(pack_dir, dest):
    pack_dir = Path(pack_dir)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pack_dir.rglob("*")):
            rel = p.relative_to(pack_dir)
            if p.is_dir() or SKIP_DIRS & set(rel.parts) or p.suffix in SKIP_SUFFIX:
                continue
            z.write(p, rel.as_posix())


def release(pack_dir, share, notes="", pilot_pcs=(), pilot_users=()):
    m = plugins.read_manifest(pack_dir)
    pid, ver = m["id"], str(m["version"])
    d = Path(share) / "packs" / pid
    d.mkdir(parents=True, exist_ok=True)
    zp = d / ("%s_%s.zip" % (pid, ver))
    if zp.exists():
        raise SystemExit("%s already exists in the release folder. Raise \"version\" in product.json first." % zp.name)
    make_zip(pack_dir, zp)
    entry = {"version": ver, "file": zp.name, "sha256": _sha(zp), "notes": notes,
             "needs_shell": str(m["needs_shell"]), "contract": m["contract"]}
    info = _latest(d)
    if pilot_pcs or pilot_users:
        if not info.get("version"):
            raise SystemExit("Release %s to everyone once before using a pilot ring." % pid)
        info["pilot"] = dict(entry, pcs=list(pilot_pcs), users=list(pilot_users))
        where = "pilot ring (%s)" % ", ".join(list(pilot_pcs) + list(pilot_users))
    else:
        info = dict(entry)
        where = "everyone"
    _write(d, info)
    return "Released %s %s to %s" % (m["name"], ver, where)


def promote(pid, share):
    d = Path(share) / "packs" / pid
    info = _latest(d)
    pilot = info.get("pilot")
    if not pilot:
        raise SystemExit("%s has no pilot release to promote." % pid)
    new = {k: v for k, v in pilot.items() if k not in ("pcs", "users", "ring")}
    _write(d, new)
    return "%s %s now goes to everyone" % (pid, new["version"])


def rollback(pid, version, share):
    d = Path(share) / "packs" / pid
    zp = d / ("%s_%s.zip" % (pid, version))
    if not zp.exists():
        raise SystemExit("%s is not in the release folder." % zp.name)
    with zipfile.ZipFile(zp) as z:
        m = json.loads(z.read("product.json").decode("utf-8-sig"))
    _write(d, {"version": str(version), "file": zp.name, "sha256": _sha(zp), "notes": "Rolled back to %s" % version,
               "needs_shell": str(m["needs_shell"]), "contract": m["contract"]})
    return "%s rolled back to %s for everyone" % (pid, version)


def listing(share):
    out = []
    root = Path(share) / "packs"
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        i = _latest(d)
        line = "%s: everyone gets %s" % (d.name, i.get("version", "-"))
        if i.get("pilot"):
            line += "; pilot %s for %s" % (i["pilot"]["version"], ", ".join(i["pilot"].get("pcs", []) + i["pilot"].get("users", [])))
        out.append(line + "   (zips: %s)" % ", ".join(sorted(p.stem.split("_", 1)[1] for p in d.glob("*.zip"))))
    return "\n".join(out) or "No packs released yet."


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", nargs="?", help="pack folder (to release) or pack id (for --promote/--rollback)")
    ap.add_argument("--share")
    ap.add_argument("--notes", default="")
    ap.add_argument("--pilot-pcs", default="", help="comma separated COMPUTERNAMEs")
    ap.add_argument("--pilot-users", default="", help="comma separated Windows logins")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--rollback", metavar="VERSION")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    share = a.share or os.environ.get("CEU_UPDATE_PATH")
    if not share:
        from updater import DEFAULT_UPDATE_PATH as share
    split = lambda t: [x.strip() for x in t.split(",") if x.strip()]
    if a.list:
        print(listing(share))
    elif a.promote:
        print(promote(a.pack, share))
    elif a.rollback:
        print(rollback(a.pack, a.rollback, share))
    elif a.pack:
        print(release(a.pack, share, a.notes, split(a.pilot_pcs), split(a.pilot_users)))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
