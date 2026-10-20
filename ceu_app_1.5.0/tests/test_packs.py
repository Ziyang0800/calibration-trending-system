"""Plug-in loader, release tool, pilot ring, rollback and failure isolation. No browser needed."""
import json, os, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plugins, release_pack


def make_pack(root, pid="demo", ver="1.0.0", needs="1.0.0", code="class Pack:\n    def __init__(self, svc, folder, m): self.v = m['version']\n", extra=None):
    d = Path(root) / pid
    d.mkdir(parents=True, exist_ok=True)
    m = {"id": pid, "name": pid.title(), "version": ver, "contract": 1, "needs_shell": needs, "entry": "pack.py"}
    m.update(extra or {})
    (d / "product.json").write_text(json.dumps(m))
    (d / "pack.py").write_text(code)
    return d


def test_release_sync_and_load():
    share, cache, work = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    p = make_pack(work, ver="1.0.0")
    print("  ", release_pack.release(p, share, "first"))
    res = plugins.sync(share, cache, "1.5.0", "PC-A", "ann")
    assert res["targets"] == {"demo": "1.0.0"} and res["installed"] == [("demo", "1.0.0")], res
    packs, infos, problems = plugins.load_all(None, "1.5.0", tempfile.mkdtemp(), cache, res["targets"])
    assert packs["demo"].v == "1.0.0" and not problems


def test_pilot_ring_promote_rollback():
    share, work = tempfile.mkdtemp(), tempfile.mkdtemp()
    release_pack.release(make_pack(work, ver="1.0.0"), share)
    release_pack.release(make_pack(work, ver="1.1.0"), share, pilot_pcs=["PC-A"], pilot_users=["bob"])
    t = lambda pc, user: plugins.sync(share, tempfile.mkdtemp(), "1.5.0", pc, user)["targets"]["demo"]
    assert t("PC-A", "x") == "1.1.0" and t("pc-a", "x") == "1.1.0" and t("PC-B", "bob") == "1.1.0" and t("PC-B", "carl") == "1.0.0"
    release_pack.promote("demo", share)
    assert t("PC-B", "carl") == "1.1.0"
    release_pack.rollback("demo", "1.0.0", share)
    assert t("PC-B", "carl") == "1.0.0"
    try:
        release_pack.release(make_pack(work, ver="1.1.0"), share); assert False
    except SystemExit:
        pass                                              # an existing version is never overwritten


def test_pinned_older_version_wins_over_newer_cached():
    share, cache, work = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    release_pack.release(make_pack(work, ver="1.0.0"), share)
    release_pack.release(make_pack(work, ver="1.1.0"), share)
    plugins.sync(share, cache, "1.5.0")
    release_pack.rollback("demo", "1.0.0", share)
    tg = plugins.sync(share, cache, "1.5.0")["targets"]
    packs, infos, _ = plugins.load_all(None, "1.5.0", tempfile.mkdtemp(), cache, tg)
    assert packs["demo"].v == "1.0.0"


def test_checksum_and_zip_safety():
    share, cache, work = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    release_pack.release(make_pack(work, ver="1.0.0"), share)
    lj = Path(share) / "packs" / "demo" / "latest.json"
    d = json.loads(lj.read_text()); d["sha256"] = "0" * 64; lj.write_text(json.dumps(d))
    res = plugins.sync(share, cache, "1.5.0")
    assert not res["installed"] and "checksum" in " ".join(res["notices"])
    bad = Path(share) / "packs" / "evil"; bad.mkdir()
    with zipfile.ZipFile(bad / "evil_1.0.0.zip", "w") as z:
        z.writestr("../escape.txt", "x"); z.writestr("product.json", "{}")
    (bad / "latest.json").write_text(json.dumps({"version": "1.0.0", "file": "evil_1.0.0.zip", "needs_shell": "1.0.0"}))
    res = plugins.sync(share, cache, "1.5.0")
    assert not any(p == "evil" for p, _ in res["installed"]) and not (Path(cache) / "escape.txt").exists()


def test_too_new_for_this_shell_is_not_installed():
    share, cache, work = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    release_pack.release(make_pack(work, ver="2.0.0", needs="9.0.0"), share)
    res = plugins.sync(share, cache, "1.5.0")
    assert not res["installed"] and "needs CEU Tool 9.0.0" in " ".join(res["notices"])


def test_broken_pack_is_isolated_and_falls_back():
    cache, bundled = tempfile.mkdtemp(), tempfile.mkdtemp()
    make_pack(Path(cache) / "demo", "1.0.0", ver="1.0.0") if False else None
    for ver, code in (("1.0.0", None), ("1.1.0", "this is not python (")):
        d = Path(cache) / "demo" / ver; d.mkdir(parents=True)
        m = {"id": "demo", "name": "Demo", "version": ver, "contract": 1, "needs_shell": "1.0.0", "entry": "pack.py"}
        (d / "product.json").write_text(json.dumps(m))
        (d / "pack.py").write_text(code or "class Pack:\n    def __init__(self, svc, folder, m): self.v = m['version']\n")
    make_pack(bundled, "other", ver="1.0.0")
    packs, infos, problems = plugins.load_all(None, "1.5.0", bundled, cache, {"demo": "1.1.0"})
    assert packs["demo"].v == "1.0.0" and "other" in packs, (packs, problems)
    assert any("failed to load" in p and "using Demo 1.0.0" in p for p in problems), problems
    # when no version works the pack is reported, the others still load
    (Path(cache) / "demo" / "1.0.0" / "pack.py").write_text("raise RuntimeError('boom')")
    packs, infos, problems = plugins.load_all(None, "1.5.0", bundled, cache, {})
    assert "demo" not in packs and "other" in packs and "boom" in infos["demo"]["error"]


def test_manifest_validation():
    d = tempfile.mkdtemp()
    for bad in ({}, {"id": "Bad Id"}):
        Path(d, "product.json").write_text(json.dumps(bad))
        try:
            plugins.read_manifest(d); assert False
        except plugins.PackError:
            pass
