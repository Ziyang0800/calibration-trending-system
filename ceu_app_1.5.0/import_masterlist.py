"""python import_masterlist.py ETEs.xlsm [setup.json]  (the app also has an Import button in the ETEs screen)"""
import json, sys
from pathlib import Path
import masterlist
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "AppData/Roaming/CEUTool/setup.json"
setup = json.loads(dst.read_text(encoding="utf-8-sig"))
setup["masterlist"] = masterlist.read_workbook(sys.argv[1])
dst.write_text(json.dumps(setup, indent=2, ensure_ascii=False), encoding="utf-8")
print("Saved %d ETEs into %s" % (len(setup["masterlist"]), dst))
