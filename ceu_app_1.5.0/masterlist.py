"""Read the workbook's masterlist sheet (columns Set, Model, Trace ID, Serial Number)."""
import re


def read_workbook(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    want = {"set": "set", "model": "model", "model id": "model", "trace id": "equipment_id", "serial number": "serial"}
    sheets = sorted(wb.worksheets, key=lambda w: w.title.strip().lower() != "masterlist")   # try "masterlist" first
    for ws in sheets:
        hdr, rows = None, []
        for r in ws.iter_rows(values_only=True):
            cells = [str(c).strip().lower() if c is not None else "" for c in r]
            if hdr is None:
                if "trace id" in cells and ("model" in cells or "model id" in cells):
                    hdr = {want[c]: i for i, c in enumerate(cells) if c in want}
                continue
            eid = re.sub(r"\s+", "", str(r[hdr["equipment_id"]] or "")).upper()
            if eid:
                row = {k: ("" if r[i] is None else str(r[i]).strip()) for k, i in hdr.items()}
                row["equipment_id"] = eid
                rows.append({"set": row.get("set", ""), "model": row.get("model", ""),
                             "equipment_id": eid, "serial": row.get("serial", "")})
        if rows:
            return rows
    raise ValueError("No sheet with the columns Set, Model, Trace ID and Serial Number was found")
