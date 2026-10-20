"""CEU Validation Tool (prototype). Run:  python app.py"""
import faulthandler, logging, os, sys, threading
import webview

from service import Service
import store
import winfile
import winchrome


def _dlg(kind):
    """webview.FileDialog.SAVE on new pywebview, webview.SAVE_DIALOG on older ones."""
    fd = getattr(webview, "FileDialog", None)
    return getattr(fd, kind) if fd else getattr(webview, kind + "_DIALOG")


class Api:
    """Methods here are callable from the UI as window.pywebview.api.<name>()."""

    def __init__(self):
        self._svc = Service()          # leading underscore: not exposed to the UI

    def get_setup(self):            return self._svc.get_setup()
    def save_setup(self, data):     return self._svc.save_setup(data)
    def pick_import(self):
        """Step 1: choose the workbook and preview what would change."""
        try:
            try:
                path = winfile.open_file("Import masterlist")
            except Exception:
                logging.exception("native open dialog failed, using the pywebview one")
                r = webview.windows[0].create_file_dialog(_dlg("OPEN"), file_types=("Excel files (*.xlsx;*.xlsm)",))
                path = r[0] if r else None
            if not path:
                return {"ok": False, "cancelled": True}
            return self._svc.preview_import(path)
        except Exception as e:
            logging.exception("pick_import failed")
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def confirm_import(self):
        try:
            return self._svc.confirm_import()
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def cancel_import(self):        self._svc.cancel_import()
    def copy_diagnostics(self):
        text = self._svc.diagnostics()
        from service import _copy
        return {"copied": _copy(text), "text": text}
    def get_etes(self):             return self._svc.ete_list()
    def export_etes(self):          return self._svc.export_etes()
    def check_update(self):         self._svc.check_update(); return self._svc.update
    def apply_update(self):
        try:
            self._svc.apply_update()
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        threading.Timer(0.5, lambda: os._exit(0)).start()      # the new copy is already starting
        return {"ok": True}
    def get_products(self):         return self._svc.products()
    def open_product(self, pid, model="", module=""):
        try:
            self._svc.open_product(pid, model, module); return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def go_home(self):              self._svc.go_home()
    def get_product_ui(self, pid):
        try:
            return dict(self._svc.pack_ui(pid), ok=True)
        except Exception as e:
            logging.exception("get_product_ui failed")
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def product_call(self, name, args):
        try:
            return self._svc.product_call(name, list(args or []))
        except Exception as e:
            logging.exception("product_call %s failed", name)
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def get_state(self):            return self._svc.state()
    def refresh(self):              self._svc.refresh()
    def set_job(self, so, serial, result): return self._svc.set_job(so, serial, result)
    def new_session(self):          self._svc.new_session()
    def open_report(self):          self._svc.open_report()
    def scan(self, code):           return self._svc.scan(code)
    def get_reminders(self):        return self._svc.reminders()
    def reminders_shown(self):      self._svc.reminders_shown()
    def reset_station(self):        self._svc.reset_station()
    def reuse_session(self):
        try:
            return dict(self._svc.reuse_session(), ok=True)
        except Exception as e:
            logging.exception("reuse_session failed")
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    def complete(self):             return self._svc.complete()
    def set_pref(self, k, v):
        self._svc.set_pref(k, v)
        if k == "theme":                                # title bar follows the theme
            threading.Thread(target=winchrome.apply, args=(v, False), daemon=True).start()

    def save_report(self):
        """Ask where to save the report (Save dialog), then build the PDF there."""
        try:
            folder, name = self._svc.report_default()
            try:
                path = winfile.save_file("Save CEU report", folder, name)
            except Exception:
                logging.exception("native save dialog failed, using the pywebview one")
                r = webview.windows[0].create_file_dialog(_dlg("SAVE"), directory=folder, save_filename=name,
                                                          file_types=("PDF files (*.pdf)",))
                path = (r if isinstance(r, str) else r[0]) if r else None
            if not path:
                return {"ok": False, "cancelled": True}
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            return {"ok": True, "path": self._svc.save_report(path)}
        except Exception as e:
            logging.exception("save_report failed")
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

    def connect(self, user, password, remember):
        try:
            self._svc.connect(user, password, bool(remember))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def set_window_icon(window):
    """Windows: show app.ico in the title bar and taskbar (the exe icon itself comes from PyInstaller --icon)."""
    try:
        import ctypes
        ico = store.resource_path("app.ico")
        if not os.path.exists(ico):
            return
        u = ctypes.windll.user32
        for _ in range(50):
            hwnd = u.FindWindowW(None, "CEU Validation Tool")
            if hwnd:
                break
            import time; time.sleep(0.1)
        else:
            return
        for size, which in ((32, 1), (16, 0)):          # ICON_BIG, ICON_SMALL
            h = u.LoadImageW(None, ico, 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                u.SendMessageW(hwnd, 0x80, which, h)         # WM_SETICON
    except Exception:
        logging.exception("could not set the window icon")


def main():
    log = open(os.path.join(str(store.data_dir()), "app.log"), "a", encoding="utf-8")   # crash details end up here
    faulthandler.enable(log)
    logging.basicConfig(stream=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api = Api()
    api.refresh()                                     # refresh from MARS at start-up
    window = webview.create_window("CEU Validation Tool", store.resource_path(os.path.join("ui", "index.html")),
                          js_api=api, width=1360, height=860, min_size=(1240, 700),
                          background_color="#f4f5f7" if api._svc.prefs()["theme"] == "light" else "#0b0b0c")
    def on_start(w):
        set_window_icon(w)
        winchrome.apply(api._svc.prefs()["theme"])
    webview.start(on_start, window)


if __name__ == "__main__":
    main()
