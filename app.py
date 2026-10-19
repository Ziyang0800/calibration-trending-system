"""
app.py - Calibration Trending System Desktop Application.
Run with: python app.py
"""

import logging
import os
import sys
import webview

import store
from service import CalibrationService
import winfile


class Api:
    def __init__(self):
        self._svc = CalibrationService()

    def get_dashboard(self):
        return self._svc.get_dashboard()

    def get_asset_detail(self, asset_id, tp_id=None):
        return self._svc.get_asset_detail(asset_id, tp_id)

    def get_calibration_for_edit(self, calibration_id):
        return self._svc.get_calibration_for_edit(calibration_id)

    def save_calibration_edit(self, data):
        return self._svc.save_calibration_edit(data)

    def get_htbasic_context(self, set_name="Set 1", zero_pt_one_pn="PN010034", wfg_serial="SG53800187"):
        return self._svc.get_htbasic_context(set_name, zero_pt_one_pn, wfg_serial)

    def generate_htbasic(self, set_name, zero_pt_one_pn, wfg_serial):
        return self._svc.generate_htbasic_zip(set_name, zero_pt_one_pn, wfg_serial)

    def import_certificate(self):
        return self._svc.import_certificate_file()

    def save_report(self, asset_ids=None):
        return self._svc.save_pdf_report(asset_ids)

    def export_excel(self, asset_id):
        return self._svc.export_excel(asset_id)

    def sync_database(self):
        return self._svc.sync_database()

    def get_sync_status(self):
        return self._svc.get_sync_status()


def set_window_icon(window):
    """Sets the Windows taskbar and window title icon via Win32 API."""
    try:
        import ctypes
        ico = store.resource_path("app.ico")
        if not os.path.exists(ico):
            return
        u = ctypes.windll.user32
        for _ in range(50):
            hwnd = u.FindWindowW(None, "Calibration Trending System")
            if hwnd:
                break
            import time
            time.sleep(0.1)
        else:
            return
        for size, which in ((32, 1), (16, 0)):
            h = u.LoadImageW(None, ico, 1, size, size, 0x10)
            if h:
                u.SendMessageW(hwnd, 0x80, which, h)
    except Exception:
        logging.exception("Could not set the window icon")


def main():
    log_file = os.path.join(str(store.data_dir()), "app.log")
    logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api = Api()
    ui_html = store.resource_path(os.path.join("ui", "index.html"))

    window = webview.create_window(
        "Calibration Trending System",
        ui_html,
        js_api=api,
        width=1380,
        height=880,
        min_size=(1240, 720),
        background_color="#f6f8fb",
    )
    webview.start(set_window_icon, window, debug=True)

if __name__ == "__main__":
    main()