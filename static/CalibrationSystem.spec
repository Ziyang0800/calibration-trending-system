from pathlib import Path
SPEC = str(Path(SPEC).resolve().parents[1] / "CalibrationSystem.spec")
exec(compile(Path(SPEC).read_text(encoding="utf-8"), SPEC, "exec"))
