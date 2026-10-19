"""
trending.py - Regression & Prediction Intervals for Metrology Standards.
Supports passive continuous standards (Resistors, Dividers, 732A) and
active instruments with adjustments (Keysight 33622A Epoch-based reset).
"""

from datetime import date, datetime
import numpy as np
from scipy import stats as scipy_stats


def _iso(d):
    if d is None:
        return ""
    if hasattr(d, "isoformat"):
        return d.isoformat()[:10]
    return str(d)[:10]


def compute_trend(dates: list, measured_values: list, nominal: float = 0.0,
                  excluded: list = None, adjustments: list = None) -> tuple:
    n_total = len(dates)
    if excluded is None:
        excluded = [False] * n_total
    if adjustments is None:
        adjustments = [False] * n_total

    if len(excluded) != n_total or len(adjustments) != n_total:
        raise ValueError("excluded and adjustments must match dates length.")
    if list(dates) != sorted(dates):
        raise ValueError("dates must be sorted ascending.")

    latest_adj_idx = -1
    for idx, is_adj in enumerate(adjustments):
        if is_adj:
            latest_adj_idx = idx

    fit_mask = np.ones(n_total, dtype=bool)
    for i in range(n_total):
        if excluded[i]:
            fit_mask[i] = False
        if latest_adj_idx != -1 and i < latest_adj_idx:
            fit_mask[i] = False

    fit_mask[-1] = False  # Hold out newest point

    # Strictly positive accumulated days (x >= 0, zero negative days)
    d0 = dates[0]
    accumulated_days = [(d - d0).days for d in dates]
    x_all = np.array(accumulated_days, dtype=float)
    y_all = np.array(measured_values, dtype=float)

    n = int(fit_mask.sum())
    if n < 3:
        error_ppm = ((y_all - nominal) / nominal * 1e6) if nominal != 0.0 else y_all
        drift_ppm = np.diff(error_ppm, prepend=np.nan)

        rows = []
        for i in range(n_total):
            rows.append({
                "date": _iso(dates[i]),
                "accumulated_days": int(accumulated_days[i]),
                "measured_value": float(y_all[i]),
                "error_ppm": float(error_ppm[i]),
                "drift_ppm": None if i == 0 or np.isnan(drift_ppm[i]) else float(drift_ppm[i]),
                "predicted": None, "lower": None, "upper": None,
                "in_fit": False, "out_of_trend": False,
                "manually_excluded": bool(excluded[i]),
                "is_adjusted": bool(adjustments[i]),
                "in_active_epoch": (latest_adj_idx == -1 or i >= latest_adj_idx),
            })
        return rows, None

    x_fit = x_all[fit_mask]
    y_fit = y_all[fit_mask]

    xbar = x_fit.mean()
    ybar = y_fit.mean()
    SSx = np.sum((x_fit - xbar) ** 2)
    Sxy = np.sum((x_fit - xbar) * (y_fit - ybar))

    slope = Sxy / SSx if SSx != 0 else 0.0
    intercept = ybar - slope * xbar

    fitted_fit = intercept + slope * x_fit
    residuals = y_fit - fitted_fit
    df = n - 2
    Syx = float(np.sqrt(np.sum(residuals ** 2) / df)) if df > 0 else 0.0
    t_crit = float(scipy_stats.t.ppf(0.975, df)) if df > 0 else 2.0

    fitted_all = intercept + slope * x_all
    margin_all = t_crit * Syx * np.sqrt(1 + 1 / n + ((x_all - xbar) ** 2 / SSx)) if SSx != 0 else np.zeros_like(x_all)
    lower_all = fitted_all - margin_all
    upper_all = fitted_all + margin_all

    error_ppm = ((y_all - nominal) / nominal * 1e6) if nominal != 0.0 else y_all
    drift_ppm = np.diff(error_ppm, prepend=np.nan)

    rows = []
    for i in range(n_total):
        in_active_epoch = (latest_adj_idx == -1 or i >= latest_adj_idx)
        out_of_trend = False
        if in_active_epoch and margin_all[i] > 0:
            out_of_trend = not (lower_all[i] <= y_all[i] <= upper_all[i])

        rows.append({
            "date": _iso(dates[i]),
            "accumulated_days": int(accumulated_days[i]),
            "measured_value": float(y_all[i]),
            "error_ppm": float(error_ppm[i]),
            "drift_ppm": None if i == 0 or np.isnan(drift_ppm[i]) else float(drift_ppm[i]),
            "predicted": float(fitted_all[i]) if in_active_epoch else None,
            "lower": float(lower_all[i]) if in_active_epoch else None,
            "upper": float(upper_all[i]) if in_active_epoch else None,
            "in_fit": bool(fit_mask[i]),
            "out_of_trend": out_of_trend,
            "manually_excluded": bool(excluded[i]),
            "is_adjusted": bool(adjustments[i]),
            "in_active_epoch": in_active_epoch,
        })

    stats = {
        "n": int(n), "df": int(df), "slope": float(slope), "intercept": float(intercept),
        "xbar": float(xbar), "Syx": float(Syx), "SSx": float(SSx), "t_crit": float(t_crit),
        "epoch_start_date": _iso(d0), "nominal": float(nominal), "latest_adj_idx": int(latest_adj_idx)
    }
    return rows, stats


def predict_at(accumulated_days: float, stats: dict) -> tuple:
    slope, intercept = stats["slope"], stats["intercept"]
    n, df, xbar, Syx, SSx, t_crit = (stats[k] for k in ("n", "df", "xbar", "Syx", "SSx", "t_crit"))
    fitted = intercept + slope * accumulated_days
    margin = t_crit * Syx * ((1 + 1 / n + (accumulated_days - xbar) ** 2 / SSx) ** 0.5)
    return fitted, fitted - margin, fitted + margin


def compute_trend_for_asset(conn, asset_id: int) -> tuple:
    nominal = conn.execute("SELECT nominal_ohms FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if nominal is None:
        raise ValueError(f"No asset with id={asset_id}")
    nominal = nominal[0]

    rows = conn.execute(
        "SELECT cal_date, measured_value, excluded_from_regression, is_adjusted FROM calibrations "
        "WHERE asset_id = ? ORDER BY cal_date",
        (asset_id,),
    ).fetchall()
    dates = [date.fromisoformat(r[0][:10]) for r in rows]
    measured = [r[1] for r in rows]
    excluded = [bool(r[2]) for r in rows]
    adjustments = [bool(r[3]) for r in rows]
    return compute_trend(dates, measured, nominal, excluded=excluded, adjustments=adjustments)