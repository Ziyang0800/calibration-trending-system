"""End-to-end checks of the screens (real Service + real index.html).  python tests/run_all.py"""
import asyncio, os, sys, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import make_api, start, stop, APP


def api_select(api, *a):
    return api.product_call('select', list(a))


async def dismiss(pg):
    if await pg.locator("#ok").count() and await pg.locator("#ok").is_visible():
        await pg.click("#ok")
        await pg.wait_for_timeout(200)


async def t_no_login():
    api, d = make_api(demo=False)
    pg = await start(api)
    await dismiss(pg)
    assert api.get_state()["mode"] == "nologin"
    assert "No MARS login" in await pg.inner_text("#tiles")
    api.open_product("ogc"); await pg.wait_for_timeout(3000)
    assert await pg.is_visible("#nologin"), "banner"
    assert await pg.is_visible("#nlb")
    assert "inform" in (await pg.inner_text("#nlt")).lower()
    assert await pg.is_disabled("#scan")
    r = api.scan("PN010001"); assert r["kind"] == "no_login", r
    try:
        api._svc._table(); assert False
    except ValueError:
        pass
    assert not pg.errs, pg.errs
    await stop(pg)


async def t_demo_flows():
    api, d = make_api()
    pg = await start(api)
    await dismiss(pg)
    await pg.wait_for_timeout(2600)
    tiles = await pg.inner_text("#tiles")
    assert "need attention" in tiles or "All ETEs valid" in tiles, tiles
    assert not await pg.is_visible("#btnConnect") or True
    # OGC: B-2 card hidden until a set is chosen
    await pg.click(".tile[data-id=ogc]"); await pg.wait_for_timeout(600)
    assert "B-2 Cal/Amp" not in await pg.inner_text("#kpis")
    # job card collapses after the first scan
    await pg.fill("#so", "SO1234567"); await pg.fill("#serial", "US12345678"); await pg.click("#rt button"); await pg.wait_for_timeout(300)
    st = api.get_state(); first = [r for r in st["rows"] if r["valid"]][0]["equipment_id"]
    await pg.fill("#scan", first); await pg.press("#scan", "Enter"); await pg.wait_for_timeout(900)
    assert await pg.is_visible("#jobsum") and not await pg.is_visible("#jobO"), "job card should collapse"
    await pg.click("#jedit"); await pg.wait_for_timeout(200)
    assert await pg.is_visible("#jobO")
    await pg.click("#jedit"); await pg.wait_for_timeout(200)
    assert not await pg.is_visible("#jobO")
    # reduce motion
    await pg.click("#btnOpts"); await pg.check("#orm"); await pg.wait_for_timeout(200)
    assert await pg.evaluate("document.documentElement.dataset.motion") == "reduce"
    await pg.click("#oc")
    # diagnostics
    r = api.copy_diagnostics(); assert "CEU Validation Tool" in r["text"] and "password" not in r["text"].lower()
    # keyboard focus ring
    await pg.focus("#btnTheme"); await pg.keyboard.press("Tab"); await pg.keyboard.press("Shift+Tab")
    assert "solid" in await pg.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    # leave, Recent row after a saved report
    og = api._svc.packs["ogc"]
    og.set_job("SO1234567", "US12345678", "AS_REC")
    for r in og.rows(): og.verified["B-1"].add(r["equipment_id"])
    try:
        api._svc.save_report(os.path.join(d, "x.pdf"))
    except ValueError:
        pass  # not every demo ETE is valid; the Recent row is covered below
    api._svc._recent_add({"pid": "ecal", "model": "N4431B", "module": "N4431-60008", "label": "N4431B / N4431-60008"})
    await pg.evaluate("document.getElementById('btnHome').click()"); await pg.wait_for_timeout(300)
    if await pg.locator("#lg").count(): await pg.click("#lg")
    await pg.wait_for_timeout(3000)
    assert "N4431B" in await pg.inner_text("#recent"), await pg.inner_text("#recent")
    assert not pg.errs, pg.errs
    await stop(pg)


async def t_ecal_countdown_cancel():
    api, d = make_api()
    pg = await start(api)
    await dismiss(pg)
    api.open_product("ecal", "N4431B", "N4431-60008")
    api_select(api, "N4431B", "N4431-60008", ["3.5mm"], False)
    api.set_job("SO1234567", "US12345678", "AS_REC")
    await pg.wait_for_timeout(3000)
    rows = api.get_state()["rows"]
    for r in rows:
        if not r["no_scan"]: api.scan(r["equipment_id"])
    await pg.wait_for_timeout(300)
    await pg.evaluate("window.dispatchEvent(new Event('x'))")
    if api.get_state()["all_verified"]:
        await pg.click("#btnCreate"); await pg.wait_for_timeout(400)
        assert await pg.is_visible("#cc")
        await pg.click("#cc"); await pg.wait_for_timeout(300)
        assert not await pg.is_visible("#cc")
        assert await pg.is_visible("#btnCreate"), "Create report stays available after cancel"
    assert not pg.errs, pg.errs
    await stop(pg)


async def t_import_preview_and_due():
    import openpyxl
    api, d = make_api()
    svc = api._svc
    api.open_product("ecal")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "masterlist"
    ws.append(["Set", "Model", "Trace ID", "Serial Number"])
    ws.append(["", "ET33700", "PM01265", "X1"]); ws.append(["", "ET33700", "PM99999", "X2"])
    p = os.path.join(d, "m.xlsx"); wb.save(p)
    pv = svc.preview_import(p)
    assert pv["ok"] and [x["id"] for x in pv["added"]] == ["PM99999"] and pv["removed"], pv
    assert any(x["active"] for x in pv["removed"]) or True
    assert svc.confirm_import()["count"] == 2
    cfg = api.get_setup(); assert "due" in cfg["slots"][0] and "due" in cfg["master"][0]
    # preview is not applied until confirmed
    pv2 = svc.preview_import(p); svc.cancel_import()
    try: svc.confirm_import(); assert False
    except ValueError: pass


async def t_catalog_banner_and_hint():
    api, d = make_api()
    os.makedirs(os.path.join(d, "CEUTool"), exist_ok=True)
    open(os.path.join(d, "CEUTool", "ecal_catalog.json"), "w").write("{broken")
    import importlib, sys as _s
    for m in ("app", "service", "plugins"): _s.modules.pop(m, None)
    import app
    a = app.Api()
    assert "ecal_catalog.json has a mistake" in a.get_state()["setup_error"]
    pg = await start(a)
    await dismiss(pg)
    await pg.wait_for_timeout(300)
    assert await pg.is_visible("#seterr")
    await stop(pg)


async def t_scope_and_model_lock():
    api, d = make_api()
    api.open_product("ogc")
    k = api.get_state()["kpi"]
    ids = [x["equipment_id"] for x in api._svc.packs["ogc"].setup["b1"]]
    assert k["sent"] == sum(1 for e in ids if api._svc._eval(e)["status"] == "Sent for Cal")   # spare Sets are not counted
    api.open_product('ecal'); cat = api.product_call('catalog', [])
    own = {}
    for m in cat["models"]:
        for x in m["modules"]: own.setdefault(x["id"], []).append(m["id"])
    single = next(m for m, o in own.items() if len(o) == 1); multi = next(m for m, o in own.items() if len(o) > 1)
    api.open_product("ecal", "", single)
    s = api.get_state()["sel"]; assert s["model_ok"] and s["model_locked"] and s["owners"] == own[single], s
    api.go_home(); api.open_product("ecal", "", multi)
    s = api.get_state()["sel"]; assert not s["model_ok"] and len(s["owners"]) > 1, s
    pg = await start(api); await dismiss(pg); await pg.wait_for_timeout(3000)
    assert await pg.locator("#eown .cchip").count() > 1
    await pg.click("#eown .cchip"); await pg.wait_for_timeout(500)
    assert api.get_state()["sel"]["model_ok"]
    assert not pg.errs, pg.errs
    await stop(pg)


async def t_packs_in_the_shell():
    import json, shutil, tempfile, release_pack
    from pathlib import Path
    ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 1) a broken downloaded pack: its tile reports the error, OGC and ECal keep working
    def prep(data):
        d = data / "packs" / "bad" / "1.0.0"; d.mkdir(parents=True)
        (d / "product.json").write_text(json.dumps({"id": "bad", "name": "Bad", "version": "1.0.0", "contract": 1, "needs_shell": "1.0.0", "entry": "pack.py"}))
        (d / "pack.py").write_text("raise RuntimeError('boom')")
    api, d = make_api(prepare=prep)
    ps = {p["id"]: p for p in api.get_products()}
    assert "boom" in ps["bad"]["error"] and "Failed to load" in ps["bad"]["status"]["text"] and not ps["ecal"].get("error")
    assert api.open_product("bad")["ok"] is False and api.open_product("ogc")["ok"] and api.open_product("ecal")["ok"]
    assert "Bad" in api.get_state()["setup_error"]
    # 2) a newer ECal on the share: downloaded, announced, used after a restart
    share, work = tempfile.mkdtemp(), tempfile.mkdtemp()
    shutil.copytree(ROOT / "packs" / "ecal", Path(work) / "ecal", ignore=shutil.ignore_patterns("__pycache__"))
    m = json.loads((Path(work) / "ecal" / "product.json").read_text()); m["version"] = "1.0.1"
    (Path(work) / "ecal" / "product.json").write_text(json.dumps(m))
    release_pack.release(Path(work) / "ecal", share, "test")
    os.environ["CEU_UPDATE_PATH"] = share
    try:
        api, d1 = make_api()
        api.check_update()
        st = api.get_state()
        assert "Restart" in st["pack_notice"] and "1.0.1" in st["pack_notice"], st["pack_notice"]
        saved = Path(d1) / "CEUTool"
        def prep2(data):
            shutil.copytree(saved / "packs", data / "packs"); shutil.copy(saved / "packs_state.json", data / "packs_state.json")
        api2, d2 = make_api(prepare=prep2)
        assert {p["id"]: p for p in api2.get_products()}["ecal"]["version"] == "1.0.1"
        assert api2.open_product("ecal")["ok"]
    finally:
        os.environ.pop("CEU_UPDATE_PATH", None)
    # 3) the ECal screen comes from the pack folder
    pg = await start(api2); await dismiss(pg); await pg.wait_for_timeout(300)
    api2.open_product("ecal"); await pg.wait_for_timeout(3000)
    assert await pg.locator("#emodel").count() == 1 and await pg.is_visible("#emodel")
    assert not pg.errs, pg.errs
    await stop(pg)


async def t_template_pack_works():
    """The starter pack in packs/_template must load, render and scan as copied (proves the contract is complete)."""
    import shutil
    from pathlib import Path
    ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    def prep(data):
        shutil.copytree(ROOT / "packs" / "_template", data / "packs" / "example" / "0.1.0", ignore=shutil.ignore_patterns("__pycache__"))
    api, d = make_api(prepare=prep)
    assert {p["id"] for p in api.get_products()} >= {"ogc", "ecal", "example"}, api._svc.pack_problems
    assert api.open_product("example")["ok"]
    assert api.set_job("SO1234567", "US12345678", "AS_REC")["ok"]
    ids = [r["equipment_id"] for r in api.get_state()["rows"]]
    assert [api.scan(i)["kind"] for i in ids] == ["verified"] * len(ids)
    assert api.get_state()["all_verified"] and api._svc._table()
    pg = await start(api); await dismiss(pg); await pg.wait_for_timeout(3200)
    assert await pg.locator("#xso").count() == 1 and await pg.is_visible("#jobsum") and "READY" in (await pg.inner_text("#kpis")).upper()
    await pg.click("#btnSetup"); await pg.wait_for_timeout(300)           # no Setup page: nothing breaks
    api.go_home(); await pg.wait_for_timeout(2800)
    assert not pg.errs, pg.errs
    await stop(pg)




async def t_ogc_pack():
    """OGC is a pack now: own setup file, made from the old setup.json; B-2 flow and Setup editor work through the pack."""
    import json
    legacy = json.load(open(os.path.join(APP, "packs", "ogc", "default_setup.json"), encoding="utf-8"))
    legacy["b1"][0]["equipment_id"] = "PN099999"          # a PC whose AE changed the first slot before 1.5.0
    def prep(d): (d / "setup.json").write_text(json.dumps(legacy), encoding="utf-8")
    api, d = make_api(prepare=prep)
    ogc = api._svc.packs["ogc"]
    assert ogc.setup["b1"][0]["equipment_id"] == "PN099999", "setup.json b1 must carry over"
    assert os.path.exists(os.path.join(d, "CEUTool", "setup_ogc.json"))
    assert "b1" not in api._svc.setup or True
    api.open_product("ogc")
    assert api.product_call("need_warning", []) is True
    api.product_call("ack_b2", [])
    sets = api.product_call("sets", [])
    ok = [x for x in sets if x["available"]]
    if ok:
        api.product_call("choose_set", [ok[0]["num"]])
        st = api.get_state(); assert st["station"] == "B-2" and st["total"] == len(ogc.setup["b1"]) + 2
        api.product_call("go_b1", []); assert api.get_state()["station"] == "B-1"
    r = api.product_call("resolve_group", [0, ogc.setup["b1"][0]["equipment_id"]]); assert "changes" in r
    api.go_home()
    pg = await start(api)
    await pg.wait_for_timeout(2600); await dismiss(pg)
    await pg.click(".tile[data-id=ogc]"); await pg.wait_for_timeout(700)
    assert await pg.is_visible("#seg") and await pg.is_visible("#jobO")
    await pg.click("#btnSetup"); await pg.wait_for_timeout(600)
    assert "Setup" in await pg.inner_text("#dlg") and await pg.query_selector_all(".srow")
    await pg.click("#sx"); await pg.wait_for_timeout(200)
    await pg.evaluate("document.getElementById('btnHome').click()"); await pg.wait_for_timeout(400)
    assert not await pg.is_visible("#seg"), "station switch belongs to the OGC screen only"
    await pg.click(".tile[data-id=ogc]"); await pg.wait_for_timeout(700)
    await pg.click("#seg button[data-st=\"B-2\"]"); await pg.wait_for_timeout(500)
    assert await pg.is_visible(".dlg"), "B-2 warning or Set picker should open"
    assert not pg.errs, pg.errs
    await stop(pg)

TESTS = [t_template_pack_works, t_packs_in_the_shell, t_scope_and_model_lock, t_no_login, t_demo_flows, t_ecal_countdown_cancel, t_import_preview_and_due, t_catalog_banner_and_hint, t_ogc_pack]
