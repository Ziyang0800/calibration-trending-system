"""Business rules for the CEU tool. Pure functions, no UI and no network."""
from datetime import datetime, date

EXPIRING_DAYS = 30                      # same window as the Excel workbook
VALID_STATUSES = ("Valid", "Expiring Soon")
RESULT_TYPES = ("AS_REC", "AS_CMPL", "AS_REC & AS_CMPL")


def parse_due(rec):
    """Return the cal due date as a datetime, or None. e.g. 2027-02-19T10:16:56"""
    for key in ("Cal_Due_Date_ISO", "Cal_Due_Date", "Cal_Due_Date_Local_DateOnly"):
        v = rec.get(key)
        if not v:
            continue
        v = str(v).strip().replace("Z", "")
        try:
            return datetime.fromisoformat(v[:19])
        except ValueError:
            pass
        for fmt in ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                pass
    return None


def evaluate(equipment_id, rec, today=None):
    """Rules 1 and 2 (rule 3, station membership, is applied by the scan step).
       1. Current_Whereabout must be INU (RCV = sent for calibration)
       2. Cal due date must be later than today()
    """
    today = today or date.today()
    midnight = datetime(today.year, today.month, today.day)
    out = {"equipment_id": equipment_id, "model": "", "serial": "", "description": "", "whereabout": "",
           "due": None, "days_left": None, "status": "", "reason": "", "valid": False}
    if not rec:
        out.update(status="Not found", reason="No record in MARS")
        return out

    out["model"] = rec.get("Model_No") or ""
    out["serial"] = rec.get("Serial_No") or ""
    out["description"] = rec.get("Model_Description") or ""
    where = str(rec.get("Current_Whereabout") or "").strip().upper()
    out["whereabout"] = where
    due = parse_due(rec)
    if due:
        out["due"] = due.strftime("%Y-%m-%d")
        out["days_left"] = (due.date() - today).days

    if where == "RCV":
        out.update(status="Sent for Cal", reason="Whereabout is RCV (sent for calibration)")
    elif where != "INU":
        out.update(status="Not in use", reason="Whereabout is %s, expected INU" % (where or "empty"))
    elif due is None:
        out.update(status="No due date", reason="MARS has no cal due date")
    elif not due > midnight:
        out.update(status="Expired", reason="Cal due date %s has passed" % out["due"])
    elif out["days_left"] <= EXPIRING_DAYS:
        out.update(status="Expiring Soon", reason="Due in %d days" % out["days_left"], valid=True)
    else:
        out.update(status="Valid", valid=True)
    return out


def normalise_scan(code):
    return (code or "").strip().upper()


def fmt_due(iso):
    """2027-02-19 -> '19 Feb 2027' (the format used on the MARS print-out)."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return "%d %s %d" % (d.day, d.strftime("%b"), d.year)
    except (TypeError, ValueError):
        return iso or ""


def norm_model(m):
    """'FLU 5720A' and 'flu5720a' are the same model."""
    return "".join(ch for ch in str(m or "").upper() if ch.isalnum() or ch in "&.-")
