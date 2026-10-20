"""Writes version_info.txt (Windows file properties of the exe) from version.py. Called by build_exe.bat."""
from version import __version__
v = (list(map(int, __version__.split("."))) + [0, 0, 0])[:3] + [0]
t = tuple(v)
open("version_info.txt", "w", encoding="utf-8").write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Keysight Technologies'),
    StringStruct('FileDescription', 'CEU Validation Tool'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'CEU Validation Tool'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""")
