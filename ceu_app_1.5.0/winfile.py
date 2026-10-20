"""Native Windows Open / Save dialogs, run on their own STA thread.
pywebview opens its dialogs from the thread that handles the JavaScript call; on some PCs the dialog then
comes up with no mouse pointer and cannot be clicked. A dialog on a dedicated STA thread behaves normally.
Both functions return a path, None if cancelled, or raise if the dialog cannot be shown (the caller falls back)."""
import os, threading

_ok = os.name == "nt"
if _ok:
    import ctypes
    from ctypes import wintypes

    class _OFN(ctypes.Structure):
        _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
                    ("lpstrFilter", ctypes.c_void_p), ("lpstrCustomFilter", ctypes.c_void_p), ("nMaxCustFilter", wintypes.DWORD),
                    ("nFilterIndex", wintypes.DWORD), ("lpstrFile", ctypes.c_void_p), ("nMaxFile", wintypes.DWORD),
                    ("lpstrFileTitle", ctypes.c_void_p), ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", ctypes.c_void_p),
                    ("lpstrTitle", ctypes.c_void_p), ("Flags", wintypes.DWORD), ("nFileOffset", wintypes.WORD),
                    ("nFileExtension", wintypes.WORD), ("lpstrDefExt", ctypes.c_void_p), ("lCustData", ctypes.c_void_p),
                    ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", ctypes.c_void_p), ("pvReserved", ctypes.c_void_p),
                    ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD)]


def _show(save, title, folder, name, filt, ext):
    comdlg, ole = ctypes.windll.comdlg32, ctypes.windll.ole32
    ole.CoInitializeEx(None, 2)                      # COINIT_APARTMENTTHREADED
    try:
        fbuf = ctypes.create_unicode_buffer(name or "", 4096)
        flt = ctypes.create_unicode_buffer(filt)
        keep = [ctypes.create_unicode_buffer(x or "") for x in (folder, title, ext)]
        o = _OFN()
        o.lStructSize = ctypes.sizeof(_OFN)
        o.lpstrFilter = ctypes.addressof(flt)
        o.nFilterIndex = 1
        o.lpstrFile, o.nMaxFile = ctypes.addressof(fbuf), 4096
        o.lpstrInitialDir = ctypes.addressof(keep[0]) if folder else None
        o.lpstrTitle = ctypes.addressof(keep[1])
        o.lpstrDefExt = ctypes.addressof(keep[2]) if ext else None
        # OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | (OFN_OVERWRITEPROMPT | OFN_FILEMUSTEXIST)
        o.Flags = 0x80000 | 0x800 | 0x8 | (0x2 if save else 0x1000)
        r = (comdlg.GetSaveFileNameW if save else comdlg.GetOpenFileNameW)(ctypes.byref(o))
        if r:
            return fbuf.value
        err = comdlg.CommDlgExtendedError()
        if err:
            raise OSError("file dialog error %d" % err)
        return None
    finally:
        ole.CoUninitialize()


def _on_thread(*a):
    out = {}

    def run():
        try:
            out["v"] = _show(*a)
        except Exception as e:
            out["e"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join()
    if "e" in out:
        raise out["e"]
    return out.get("v")


def save_file(title, folder, name, filt="PDF files (*.pdf)\0*.pdf\0All files\0*.*\0", ext="pdf"):
    if not _ok:
        raise OSError("not Windows")
    return _on_thread(True, title, folder, name, filt, ext)


def open_file(title, filt="Excel files (*.xlsx;*.xlsm)\0*.xlsx;*.xlsm\0All files\0*.*\0"):
    if not _ok:
        raise OSError("not Windows")
    return _on_thread(False, title, "", "", filt, "")
