"""
queries.py - data access layer supporting multi-equipment trending, 
guaranteed chronological date sorting, and facility epoch detection.
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from trending import compute_trend
from stability_specs import assess_drift, get_spec_description

MIN_POINTS_FOR_TREND = 4


def to_date(d) -> Optional[date]:
    """Safely converts string, date, or datetime into datetime.date."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    s = str(d).strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            m, day, y = parts
            y = f"20{y}" if len(y) == 2 else y
            return date(int(y), int(m), int(day))
    return date.fromisoformat(s[:10])


def list_assets(conn) -> List[Dict[str, Any]]:
    assets = conn.execute(
        "SELECT id, serial, model, asset_number, nominal_ohms, source_sheet, set_id, category, unit FROM assets "
        "ORDER BY category, nominal_ohms, serial"
    ).fetchall()

    results = []
    for asset_id, serial, model, asset_number, nominal, source_sheet, set_id, category, unit in assets:
        category = category or "standard_resistor"
        unit = unit or "Ω"

        tp_rows = conn.execute(
            "SELECT id, nominal_value, point_name FROM test_points WHERE asset_id = ?",
            (asset_id,)
        ).fetchall()

        if tp_rows:
            worst_status = "ok"
            all_enough = True
            last_date = None
            last_val = None
            latest_event = conn.execute("SELECT MAX(cal_date) FROM calibrations WHERE asset_id=?", (asset_id,)).fetchone()[0]

            for tp_id, tp_nom, tp_name in tp_rows:
                readings = conn.execute(
                    "SELECT c.cal_date, cr.measured_value, (cr.excluded_from_regression OR c.excluded_from_regression), c.is_adjusted, "
                    "c.reviewer_comment, c.reviewer_attachment_path, c.location "
                    "FROM calibrations c JOIN calibration_readings cr ON cr.calibration_id = c.id "
                    "WHERE c.asset_id = ? AND cr.test_point_id = ?",
                    (asset_id, tp_id)
                ).fetchall()

                readings.sort(key=lambda r: to_date(r[0]))

                if readings:
                    last_date = str(to_date(readings[-1][0]))
                    last_val = readings[-1][1]
                    if last_date != latest_event:
                        all_enough = False

                if len(readings) >= MIN_POINTS_FOR_TREND:
                    dates = [to_date(r[0]) for r in readings]
                    measured = [r[1] for r in readings]
                    excluded = [bool(r[2]) for r in readings]

                    epoch_resets = []
                    prev_loc = None
                    for r in readings:
                        is_reset = bool(r[3])
                        loc = r[6] if len(r) > 6 else None
                        if category == "dcv_reference" and loc:
                            if prev_loc and loc != prev_loc:
                                is_reset = True
                            prev_loc = loc
                        epoch_resets.append(is_reset)

                    nom_val = tp_nom if tp_nom is not None else (measured[0] if measured else 0.0)
                    rows, stats = compute_trend(dates, measured, nom_val, excluded=excluded, adjustments=epoch_resets)
                    if stats is None or excluded[-1]:
                        all_enough = False
                    if rows and rows[-1]["out_of_trend"]:
                        has_rev = bool(readings[-1][4] or readings[-1][5])
                        if not has_rev:
                            worst_status = "out_of_trend"
                        elif worst_status != "out_of_trend":
                            worst_status = "reviewed_out_of_trend"

                else:
                    all_enough = False

            total_cals = conn.execute("SELECT COUNT(*) FROM calibrations WHERE asset_id = ?", (asset_id,)).fetchone()[0]
            # Every configured point needs a valid current-epoch trend and a latest-event reading.
            status = worst_status if worst_status != "ok" or all_enough else "insufficient_data"

            results.append({
                "id": asset_id, "serial": serial, "model": model, "asset_number": asset_number,
                "nominal_ohms": nominal, "source_sheet": source_sheet, "set_id": set_id,
                "category": category, "unit": unit,
                "num_calibrations": total_cals,
                "last_cal_date": last_date,
                "last_measured": last_val,
                "status": status,
            })
        else:
            cals = conn.execute(
                "SELECT cal_date, measured_value, excluded_from_regression, is_adjusted, "
                "reviewer_comment, reviewer_attachment_path, location "
                "FROM calibrations WHERE asset_id = ?",
                (asset_id,),
            ).fetchall()

            cals.sort(key=lambda c: to_date(c[0]))

            entry = {
                "id": asset_id, "serial": serial, "model": model, "asset_number": asset_number,
                "nominal_ohms": nominal, "source_sheet": source_sheet, "set_id": set_id,
                "category": category, "unit": unit,
                "num_calibrations": len(cals),
                "last_cal_date": str(to_date(cals[-1][0])) if cals else None,
                "last_measured": cals[-1][1] if cals else None,
                "status": "insufficient_data",
            }

            if len(cals) >= MIN_POINTS_FOR_TREND:
                dates = [to_date(c[0]) for c in cals]
                measured = [c[1] for c in cals]
                excluded = [bool(c[2]) for c in cals]

                epoch_resets = []
                prev_loc = None
                for c in cals:
                    is_reset = bool(c[3])
                    loc = c[6] if len(c) > 6 else None
                    if category == "dcv_reference" and loc:
                        if prev_loc and loc != prev_loc:
                            is_reset = True
                        prev_loc = loc
                    epoch_resets.append(is_reset)

                nom = nominal if nominal else (measured[0] if measured else 0.0)
                rows, stats = compute_trend(dates, measured, nom, excluded=excluded, adjustments=epoch_resets)
                if stats and rows and not excluded[-1]:
                    newest = rows[-1]
                    if newest["out_of_trend"]:
                        has_review = bool(cals[-1][4] or cals[-1][5])
                        entry["status"] = "reviewed_out_of_trend" if has_review else "out_of_trend"
                    else:
                        entry["status"] = "ok"
                elif rows:
                    entry["status"] = "ok"

            results.append(entry)

    return results


def list_assets_grouped_by_set(conn) -> List[Dict[str, Any]]:
    assets = list_assets(conn)
    groups = {}
    for a in assets:
        key = a["set_id"] or "Unassigned"
        groups.setdefault(key, []).append(a)

    def sort_key(name):
        return (1, name) if name == "Unassigned" else (0, name)

    result = []
    for set_name in sorted(groups.keys(), key=sort_key):
        group_assets = groups[set_name]
        result.append({
            "set_id": set_name,
            "assets": group_assets,
            "total": len(group_assets),
            "ok_count": sum(1 for a in group_assets if a["status"] in ("ok", "reviewed_out_of_trend")),
            "out_count": sum(1 for a in group_assets if a["status"] == "out_of_trend"),
            "insufficient_count": sum(1 for a in group_assets if a["status"] == "insufficient_data"),
        })
    return result


def get_asset_detail(conn, asset_id: int, selected_point_id: int = None) -> Optional[Dict[str, Any]]:
    asset_row = conn.execute(
        "SELECT id, serial, model, asset_number, nominal_ohms, source_workbook, source_sheet, set_id, category, unit "
        "FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    if not asset_row:
        return None

    asset = {
        "id": asset_row[0], "serial": asset_row[1], "model": asset_row[2],
        "asset_number": asset_row[3], "nominal_ohms": asset_row[4],
        "source_workbook": asset_row[5], "source_sheet": asset_row[6], "set_id": asset_row[7],
        "category": asset_row[8] or "standard_resistor", "unit": asset_row[9] or "Ω"
    }

    raw_test_points = conn.execute(
        "SELECT id, point_name, group_name, nominal_value, unit, display_order FROM test_points "
        "WHERE asset_id = ? ORDER BY display_order, id", (asset_id,)
    ).fetchall()

    test_point_list = []
    latest_event_date = conn.execute("SELECT MAX(cal_date) FROM calibrations WHERE asset_id=?", (asset_id,)).fetchone()[0]
    for tp in raw_test_points:
        tp_id, tp_name, tp_group, tp_nom, tp_unit, tp_order = tp

        r_rows = conn.execute(
            "SELECT c.cal_date, cr.measured_value, cr.uncertainty, (cr.excluded_from_regression OR c.excluded_from_regression), c.is_adjusted, "
            "c.reviewer_comment, c.reviewer_attachment_path, c.location "
            "FROM calibrations c JOIN calibration_readings cr ON cr.calibration_id = c.id "
            "WHERE c.asset_id = ? AND cr.test_point_id = ?",
            (asset_id, tp_id)
        ).fetchall()

        r_rows.sort(key=lambda r: to_date(r[0]))

        latest_val = r_rows[-1][1] if r_rows else None
        latest_date = str(to_date(r_rows[-1][0])) if r_rows else None
        prev_val = r_rows[-2][1] if len(r_rows) > 1 else None

        # Normalized drift calculation: strictly null / "—" if only 1 cal point exists
        drift = None
        drift_ppm = None
        drift_display = "—"

        if latest_val is not None and prev_val is not None:
            drift = latest_val - prev_val
            if tp_unit == "dB" or asset["unit"] == "dB":
                drift_display = f"{drift:+.4f} dB"
                drift_ppm = drift
            else:
                nom_ref = tp_nom if (tp_nom and tp_nom != 0) else asset["nominal_ohms"]
                if nom_ref and nom_ref != 0:
                    drift_ppm = (drift / nom_ref) * 1e6
                    drift_display = f"{drift_ppm:+.2f} ppm"
                else:
                    drift_display = f"{drift:+.4f}"
                    drift_ppm = drift

        tp_status = "insufficient_data"
        if len(r_rows) >= MIN_POINTS_FOR_TREND:
            tp_dates = [to_date(r[0]) for r in r_rows]
            tp_meas = [r[1] for r in r_rows]
            tp_excl = [bool(r[3]) for r in r_rows]

            epoch_resets = []
            prev_loc = None
            for r in r_rows:
                is_reset = bool(r[4])
                loc = r[7] if len(r) > 7 else None
                if asset["category"] == "dcv_reference" and loc:
                    if prev_loc and loc != prev_loc:
                        is_reset = True
                    prev_loc = loc
                epoch_resets.append(is_reset)

            tp_nom_val = tp_nom if tp_nom is not None else (tp_meas[0] if tp_meas else 0.0)
            tp_rows_res, tp_stats = compute_trend(tp_dates, tp_meas, tp_nom_val, excluded=tp_excl, adjustments=epoch_resets)
            if tp_stats is not None and not tp_excl[-1] and latest_date == latest_event_date:
                tp_status = "ok"
            if tp_rows_res and tp_rows_res[-1]["out_of_trend"]:
                has_rev = bool(r_rows[-1][5] or r_rows[-1][6])
                tp_status = "reviewed_out_of_trend" if has_rev else "out_of_trend"

        test_point_list.append({
            "id": tp_id, "point_name": tp_name, "group_name": tp_group,
            "nominal_value": tp_nom, "unit": tp_unit, "display_order": tp_order,
            "latest_value": latest_val, "latest_date": latest_date,
            "drift": drift, "drift_ppm": drift_ppm, "drift_display": drift_display,
            "status": tp_status
        })

    active_tp_id = selected_point_id or (test_point_list[0]["id"] if test_point_list else None)

    # Load calibrations selecting BOTH raw unitless mu_relative and reading-level uncertainty
    cal_rows = []
    if active_tp_id:
        # Never substitute the asset summary/first-point value for a missing reading
        # on the selected test point; doing so would contaminate that point's trend.
        cal_rows = conn.execute(
            "SELECT c.id, c.cal_date, cr.measured_value, c.mu_relative, cr.uncertainty, c.source, c.cert_number, "
            "c.cert_pdf_path, c.reviewer_comment, (cr.excluded_from_regression OR c.excluded_from_regression), c.reviewer_attachment_path, "
            "c.reviewer_url, c.pressure_hpa, c.is_adjusted, c.location "
            "FROM calibrations c "
            "JOIN calibration_readings cr ON cr.calibration_id = c.id "
            "WHERE c.asset_id = ? AND cr.test_point_id = ?",
            (asset_id, active_tp_id)
        ).fetchall()
    else:
        cal_rows = conn.execute(
            "SELECT id, cal_date, measured_value, mu_relative, NULL, source, cert_number, cert_pdf_path, "
            "reviewer_comment, excluded_from_regression, reviewer_attachment_path, reviewer_url, "
            "pressure_hpa, is_adjusted, location "
            "FROM calibrations WHERE asset_id = ?", (asset_id,)
        ).fetchall()

    calibrations = [{
        "id": r[0], "date": str(to_date(r[1])), "measured_value": r[2],
        "mu_relative": r[3] if r[3] is not None else 0.0,
        "uncertainty": r[4],  # Specific reading uncertainty (e.g. 35.0 nV or 23.0 ppm)
        "source": r[5], "cert_number": r[6], "cert_pdf_path": r[7],
        "reviewer_comment": r[8], "excluded_from_regression": bool(r[9]),
        "reviewer_attachment_path": r[10], "reviewer_url": r[11],
        "pressure_hpa": r[12], "is_adjusted": bool(r[13]),
        "location": r[14],
    } for r in cal_rows]

    calibrations.sort(key=lambda c: to_date(c["date"]))

    active_tp_rec = next((p for p in test_point_list if p["id"] == active_tp_id), None)
    nom = asset["nominal_ohms"]
    if active_tp_rec and active_tp_rec["nominal_value"] is not None:
        nom = active_tp_rec["nominal_value"]

    d0 = to_date(calibrations[0]["date"]) if calibrations else None
    prev_val = None
    for cal in calibrations:
        d = to_date(cal["date"])
        cal["accumulated_days"] = (d - d0).days if d0 else 0
        val = cal["measured_value"]

        if asset["unit"] == "dB":
            cal["error_ppm"] = val
            cal["drift_ppm"] = (val - prev_val) if prev_val is not None else None
            prev_val = val
        elif nom and nom != 0.0:
            err = (val - nom) / nom * 1e6
            cal["error_ppm"] = err
            cal["drift_ppm"] = (err - prev_val) if prev_val is not None else None
            prev_val = err
        else:
            cal["error_ppm"] = val
            cal["drift_ppm"] = (val - prev_val) if prev_val is not None else None
            prev_val = val

        cal["predicted"] = None
        cal["lower"] = None
        cal["upper"] = None
        cal["out_of_trend"] = False
        cal["in_fit"] = False
        cal["in_active_epoch"] = True
        cal["display_status"] = "baseline"

    trend = None
    if len(calibrations) >= MIN_POINTS_FOR_TREND:
        dates = [to_date(c["date"]) for c in calibrations]
        measured = [c["measured_value"] for c in calibrations]
        excluded = [c["excluded_from_regression"] for c in calibrations]

        epoch_resets = []
        prev_loc = None
        for c in calibrations:
            is_reset = bool(c["is_adjusted"])
            loc = c.get("location")
            if asset.get("category") == "dcv_reference" and loc:
                if prev_loc and loc != prev_loc:
                    is_reset = True
                prev_loc = loc
            epoch_resets.append(is_reset)

        rows, stats = compute_trend(dates, measured, nom, excluded=excluded, adjustments=epoch_resets)
        if rows:
            for cal, r in zip(calibrations, rows):
                cal.update(r)
        trend = stats

    for cal in calibrations:
        has_review = bool(cal.get("reviewer_comment") or cal.get("reviewer_attachment_path"))
        if cal.get("excluded_from_regression"):
            cal["display_status"] = "excluded"
        elif cal.get("in_active_epoch") is False:
            cal["display_status"] = "prior_epoch"
        elif cal.get("out_of_trend"):
            cal["display_status"] = "reviewed_out_of_trend" if has_review else "out_of_trend"
        elif cal.get("predicted") is not None:
            cal["display_status"] = "ok"

    stability = None
    if asset["category"] == "standard_resistor" and len(calibrations) >= 2:
        latest, previous = calibrations[-1], calibrations[-2]
        latest_d = to_date(latest["date"])
        prev_d = to_date(previous["date"])
        elapsed_days = (latest_d - prev_d).days
        if latest.get("error_ppm") is not None and previous.get("error_ppm") is not None:
            observed_drift = latest["error_ppm"] - previous["error_ppm"]
            res = assess_drift(asset["model"], observed_drift, elapsed_days)
            stability = {
                "previous_date": str(prev_d), "previous_error_ppm": previous["error_ppm"],
                "latest_date": str(latest_d), "latest_error_ppm": latest["error_ppm"],
                "observed_drift_ppm": observed_drift, "elapsed_days": elapsed_days,
                "allowance_ppm": res["allowance_ppm"], "exceeds": res["exceeds"],
                "spec_description": get_spec_description(asset["model"]),
            }

    return {
        "asset": asset, "calibrations": calibrations, "trend": trend,
        "stability": stability, "test_points": test_point_list,
        "active_test_point": active_tp_rec,
        "active_test_point_id": active_tp_id
    }
