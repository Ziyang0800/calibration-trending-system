from pathlib import Path
exec(compile((Path(SPEC).resolve().parent / "CalibrationSystem.spec").read_text(encoding="utf-8"), "CalibrationSystem.spec", "exec"))
