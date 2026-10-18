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
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def load_setup(d):
    """Returns (setup, error_text). A mistake in setup.json is reported, never silently ignored."""
    p = d / "setup.json"
    if not p.exists():
        shutil.copy(resource_path("default_setup.json"), p)
    try:
        with open(p, encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data.get("b1"), list) or not isinstance(data.get("sets"), list):
            raise ValueError('setup.json needs a "b1" list and a "sets" list')
        for s in data["b1"]:
            s["equipment_id"], s["slot"]
        for s in data["sets"]:
            s["num"], s["calibrator"], s["amplifier"]
        return data, None
    except ValueError as e:            # includes json.JSONDecodeError (line and column are in the text)
        return {"b1": [], "sets": []}, "setup.json has a mistake: %s  [%s]" % (e, p)
    except (KeyError, TypeError) as e:
        return {"b1": [], "sets": []}, "setup.json is missing a field %s  [%s]" % (e, p)
    except OSError as e:
        return {"b1": [], "sets": []}, "Cannot read setup.json: %s" % e
