"""Local storage on this PC (JSON files for now; the same functions can move to SQLite later)."""
import json, os, shutil, sys
from pathlib import Path


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def data_dir():
    root = os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / "CEUTool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:      # utf-8-sig: tolerates the BOM Notepad adds
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_json_strict(path):
    """Like read_json, but errors are raised (the caller reports them)."""
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_setup(d):
    """Shell settings (setup.json: update_path, refresh_minutes, greeting_name ...). Returns (settings, error_text).
    Product data lives in each pack's own file (OGC: setup_ogc.json), not here."""
    p = d / "setup.json"
    if not p.exists():
        write_json(p, {})
    try:
        data = read_json_strict(p)
        if not isinstance(data, dict):
            raise ValueError("it must be a JSON object { ... }")
        return data, None
    except ValueError as e:            # includes json.JSONDecodeError (line and column are in the text)
        return {}, "setup.json has a mistake: %s  [%s]" % (e, p)
    except OSError as e:
        return {}, "Cannot read setup.json: %s" % e
