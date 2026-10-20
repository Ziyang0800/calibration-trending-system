"""Headless harness: the real Service/Api in Python and the real ui/index.html in Chromium, bridged like pywebview.
Needs:  pip install playwright openpyxl  (and a Chromium; set CHROMIUM=/path/to/chromium if it is not the default)."""
import sys, os, types, tempfile, time
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from playwright.async_api import async_playwright

CHROMIUM = os.environ.get("CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)


def make_api(demo=True, prepare=None):
    """A fresh Api with an empty data folder. demo=False behaves like a PC that has no MARS login."""
    d = tempfile.mkdtemp(prefix="ceu_")
    os.environ["APPDATA"] = d
    for k in ("MARS_USER", "MARS_PASSWORD"):
        os.environ.pop(k, None)
    if demo:
        os.environ["CEU_DEMO"] = "1"
    else:
        os.environ.pop("CEU_DEMO", None)
    sys.modules.setdefault("webview", types.ModuleType("webview"))
    for m in ("app", "service", "store", "logic", "mars", "report", "updater", "names", "plugins"):
        sys.modules.pop(m, None)
    if prepare:
        from pathlib import Path
        (Path(d) / "CEUTool").mkdir(parents=True, exist_ok=True)
        prepare(Path(d) / "CEUTool")
    import app
    a = app.Api()
    a.refresh()
    for _ in range(50):
        if not a._svc.refreshing:
            break
        time.sleep(0.1)
    return a, d


def load_pack_module(pid):
    """Import the entry module of a bundled pack (for rules tests that need no Service)."""
    import plugins
    folder = os.path.join(APP, "packs", pid)
    return plugins._import(plugins.read_manifest(folder), folder), folder


async def start(api, w=1360, h=860):
    p = await async_playwright().start()
    kw = {"executable_path": CHROMIUM} if CHROMIUM else {}
    b = await p.chromium.launch(**kw)
    pg = await b.new_page(viewport={"width": w, "height": h})
    pg.errs = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: pg.errs.append("console:" + m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)

    async def call(name, args):
        try:
            return getattr(api, name)(*args)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    await pg.expose_function("__call", call)
    await pg.add_init_script("window.pywebview={api:new Proxy({},{get:(t,n)=>(...a)=>window.__call(n,a)})};")
    await pg.goto("file://" + APP + "/ui/index.html")
    await pg.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
    await pg.wait_for_timeout(500)
    pg._b, pg._p = b, p
    return pg


async def stop(pg):
    await pg._b.close()
    await pg._p.stop()
