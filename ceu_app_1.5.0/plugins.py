"""Plug-in packs: products that load into the shell from folders.

A pack folder holds:  product.json (manifest), the entry module (pack.py: class Pack), data files and a screen (ui/).
Where packs live, newest compatible version wins (or the version the release folder pins):
    <app>\\packs\\<id>\\                       bundled with the exe (baseline, works offline)
    %APPDATA%\\CEUTool\\packs\\<id>\\<ver>\\   downloaded from the release folder
Release folder layout (made by release_pack.py):
    packs\\<id>\\latest.json   {"version","file","sha256","notes","needs_shell","pilot":{...}}
    packs\\<id>\\<id>_<ver>.zip
A pack that fails to load never stops the shell: the tile shows the error, other products keep working,
and an older version of the same pack is tried first.  See CONTRACT.md."""
import hashlib, importlib.util, json, logging, os, re, shutil, sys, zipfile
from pathlib import Path

import store
from updater import vtuple

CONTRACT = 1                                   # pack contract this shell speaks (see CONTRACT.md)
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,20}$")
KEEP_VERSIONS = 3                              # downloaded versions kept per pack (rollback)


class PackError(Exception):
    pass


def read_manifest(folder):
    folder = Path(folder)
    d = store.read_json(folder / "product.json", None)
    if not isinstance(d, dict):
        raise PackError("product.json is missing or is not valid JSON")
    for k in ("id", "name", "version", "contract", "needs_shell"):
        if d.get(k) in (None, ""):
            raise PackError('product.json needs "%s"' % k)
    if not ID_RE.match(str(d["id"])):
        raise PackError('"id" must be lower-case letters, digits or _ (2-21 characters)')
    d.setdefault("entry", "pack.py")
    if not (folder / d["entry"]).is_file():
        raise PackError("entry file %s is missing" % d["entry"])
    return d


def scan(root):
    """{pack id: [(version, folder, manifest)]} for every readable pack under root (a dir of <id>[/<ver>]/product.json),
    plus a list of problems."""
    found, problems = {}, []
    root = Path(root)
    if not root.is_dir():
        return found, problems
    for idir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        folders = [idir] if (idir / "product.json").exists() else sorted(p for p in idir.iterdir() if p.is_dir() and not p.name.startswith("."))
        for f in folders:
            if not (f / "product.json").exists():
                continue
            try:
                m = read_manifest(f)
                found.setdefault(m["id"], []).append((m["version"], f, m))
            except PackError as e:
                problems.append("%s: %s" % (f, e))
    for lst in found.values():
        lst.sort(key=lambda t: vtuple(t[0]), reverse=True)
    return found, problems


def compatible(manifest, shell_version):
    """'' when the shell can run this pack, else the reason."""
    if int(manifest.get("contract") or 0) != CONTRACT:
        return "uses pack contract %s, this app speaks %s" % (manifest.get("contract"), CONTRACT)
    if vtuple(shell_version) < vtuple(manifest.get("needs_shell")):
        return "needs CEU Tool %s or newer (this is %s)" % (manifest.get("needs_shell"), shell_version)
    return ""


def _import(manifest, folder):
    folder = Path(folder)
    vendor = folder / "vendor"                          # pure-Python libraries a pack brings with it
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    name = "ceu_pack_%s_%s" % (manifest["id"], re.sub(r"\W", "_", str(manifest["version"])))
    spec = importlib.util.spec_from_file_location(name, str(folder / manifest["entry"]))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Pack"):
        raise PackError("%s has no class Pack" % manifest["entry"])
    return mod


def load_all(svc, shell_version, bundled_root, cache_root, targets):
    """-> (packs {id: instance}, infos {id: {manifest, folder, source, error}}, problems [text])."""
    found, problems = {}, []
    for root, source in ((bundled_root, "bundled"), (cache_root, "downloaded")):
        f, pr = scan(root)
        problems += pr
        for pid, lst in f.items():
            for v, folder, m in lst:
                found.setdefault(pid, []).append((v, folder, m, source))
    packs, infos = {}, {}
    for pid, lst in sorted(found.items()):
        lst.sort(key=lambda t: vtuple(t[0]), reverse=True)
        want = (targets or {}).get(pid)
        order = sorted(lst, key=lambda t: (t[0] != want,))          # the pinned version first, the rest newest first
        errors, loaded = [], None
        for v, folder, m, source in order:
            why = compatible(m, shell_version)
            if why:
                errors.append("%s %s %s" % (m["name"], v, why))
                continue
            try:
                mod = _import(m, folder)
                pack = mod.Pack(svc, folder, m)
                loaded = (pack, {"manifest": m, "folder": str(folder), "source": source})
                break
            except Exception as e:
                logging.exception("pack %s %s failed to load", pid, v)
                errors.append("%s %s failed to load: %s: %s" % (m["name"], v, type(e).__name__, e))
        if loaded:
            packs[pid] = loaded[0]
            infos[pid] = dict(loaded[1], error="")
            if errors:                                              # an older version is running instead
                problems.append("%s - using %s %s instead" % ("; ".join(errors), loaded[1]["manifest"]["name"], loaded[1]["manifest"]["version"]))
        else:
            m = lst[0][2]
            infos[pid] = {"manifest": m, "folder": str(lst[0][1]), "source": lst[0][3], "error": "; ".join(errors) or "no loadable version"}
            problems.append("Product %s is not available: %s" % (m["name"], infos[pid]["error"]))
    return packs, infos, problems


# ---------------------------------------------------------------- downloads from the release folder
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_block(info, computer, user):
    """The release entry this PC should follow: the pilot one when this PC or login is on its list, else the main one."""
    pilot = info.get("pilot") if isinstance(info.get("pilot"), dict) else None
    if pilot and pilot.get("version"):
        pcs = {str(x).strip().lower() for x in pilot.get("pcs") or []}
        users = {str(x).strip().lower() for x in pilot.get("users") or []}
        if (computer or "").lower() in pcs or (user or "").lower() in users:
            return dict(pilot, ring="pilot")
    return dict(info, ring="main")


def _install(zip_path, dest_root, pid, version):
    tmp = Path(dest_root) / pid / (".tmp_" + version)
    final = Path(dest_root) / pid / version
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.startswith(("/", "\\")) or ".." in Path(n).parts or ":" in n:
                raise PackError("unsafe path in the zip: %s" % n)
        z.extractall(tmp)
    m = read_manifest(tmp)
    if m["id"] != pid or str(m["version"]) != version:
        raise PackError("the zip holds %s %s, expected %s %s" % (m["id"], m["version"], pid, version))
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)


def _prune(dest_root, pid, keep):
    d = Path(dest_root) / pid
    vers = sorted((p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: vtuple(p.name), reverse=True) if d.is_dir() else []
    for p in vers[KEEP_VERSIONS:]:
        if p.name not in keep:
            shutil.rmtree(p, ignore_errors=True)


def sync(share, cache_root, shell_version, computer="", user=""):
    """Look at <share>\\packs\\*\\latest.json and download what this PC should run.
    -> {"targets": {id: version}, "installed": [(id, version)], "notices": [text]}.  Never raises."""
    out = {"targets": {}, "installed": [], "notices": []}
    root = Path(share or "") / "packs"
    try:
        dirs = sorted(p for p in root.iterdir() if p.is_dir())
    except Exception as e:
        logging.info("pack folder not reachable: %s", e)
        return out
    for d in dirs:
        pid = d.name
        try:
            info = store.read_json(d / "latest.json", None)
            if not isinstance(info, dict) or not info.get("version"):
                continue
            blk = pick_block(info, computer, user)
            ver, need = str(blk["version"]), blk.get("needs_shell") or info.get("needs_shell") or "0"
            fake = {"contract": blk.get("contract", info.get("contract", CONTRACT)), "needs_shell": need}
            why = compatible(fake, shell_version)
            if why:
                out["notices"].append("%s %s %s. Keeping the version already installed." % (pid, ver, why))
                continue
            have = Path(cache_root) / pid / ver
            if not (have / "product.json").exists():
                zp = d / str(blk.get("file") or "%s_%s.zip" % (pid, ver))
                if not zp.is_file():
                    raise PackError("%s is missing from the release folder" % zp.name)
                local = Path(cache_root) / pid / (".dl_" + zp.name)
                local.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(zp, local)
                try:
                    if blk.get("sha256") and _sha256(local) != str(blk["sha256"]).lower():
                        raise PackError("checksum of %s does not match latest.json" % zp.name)
                    _install(local, cache_root, pid, ver)
                finally:
                    local.unlink(missing_ok=True)
                out["installed"].append((pid, ver))
            out["targets"][pid] = ver
            _prune(cache_root, pid, {ver})
        except Exception as e:
            logging.exception("pack sync %s failed", pid)
            out["notices"].append("%s: update not installed (%s: %s)" % (pid, type(e).__name__, e))
    return out
