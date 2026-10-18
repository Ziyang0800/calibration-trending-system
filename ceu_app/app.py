"""CEU Validation Tool (prototype). Run:  python app.py"""
import os, sys
import webview

from service import Service
import store


class Api:
    """Methods here are callable from the UI as window.pywebview.api.<name>()."""

    def __init__(self):
        self._svc = Service()          # leading underscore: not exposed to the UI

    def get_state(self):            return self._svc.state()
    def get_sets(self):             return self._svc.sets()
    def refresh(self):              self._svc.refresh()
    def need_warning(self):         return self._svc.need_warning()
    def acknowledge_b2(self):       self._svc.acknowledge_b2()
    def choose_set(self, n):        self._svc.choose_set(int(n))
    def go_b1(self):                self._svc.go_b1()
    def set_so(self, so):           self._svc.set_so(so)
    def scan(self, code):           return self._svc.scan(code)
    def get_reminders(self):        return self._svc.reminders()
    def reminders_shown(self):      self._svc.reminders_shown()
    def reset_station(self):        self._svc.reset_station()
    def complete(self):             return self._svc.complete()

    def connect(self, user, password, remember):
        try:
            self._svc.connect(user, password, bool(remember))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def main():
    api = Api()
    api.refresh()                                     # refresh from MARS at start-up
    webview.create_window("CEU Validation Tool", store.resource_path(os.path.join("ui", "index.html")),
                          js_api=api, width=1360, height=860, min_size=(1100, 700),
                          background_color="#0b0b0c")
    webview.start()


if __name__ == "__main__":
    main()
