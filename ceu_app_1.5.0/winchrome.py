"""Windows title bar colours that follow the app theme (Windows 11: caption, text and border colour;
Windows 10: dark / light caption only). Edit PALETTE to change the colours."""
import logging, os

TITLE = "CEU Validation Tool"
#            caption     text       border
PALETTE = {"dark": ("#0f3b39", "#ffffff", "#1fb5a8"),     # deep teal, white text, teal edge
           "light": ("#cdeeea", "#122033", "#1fb5a8")}    # soft teal tint, dark text, teal edge


def _bgr(hex_colour):
    h = hex_colour.lstrip("#")
    return int(h[4:6] + h[2:4] + h[0:2], 16)           # COLORREF is 0x00BBGGRR


def apply(theme, wait=True):
    """Colour the title bar for 'dark' or 'light'. Safe to call any time; does nothing off Windows."""
    if os.name != "nt":
        return False
    try:
        import ctypes, time
        theme = "light" if theme == "light" else "dark"
        u, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        hwnd = 0
        for _ in range(50 if wait else 1):
            hwnd = u.FindWindowW(None, TITLE)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            return False

        def put(attr, value):
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        for attr in (20, 19):                           # DWMWA_USE_IMMERSIVE_DARK_MODE (20 = Win10 20H1+/11, 19 = older)
            if put(attr, 1 if theme == "dark" else 0) == 0:
                break
        cap, txt, brd = PALETTE[theme]
        put(35, _bgr(cap))                              # DWMWA_CAPTION_COLOR   (Windows 11 only)
        put(36, _bgr(txt))                              # DWMWA_TEXT_COLOR
        put(34, _bgr(brd))                              # DWMWA_BORDER_COLOR
        return True
    except Exception:
        logging.exception("could not colour the title bar")
        return False
