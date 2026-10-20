"""
tests/test_trending.py - Comprehensive mathematical verification of hold-out
linear regression, Student's t 95% prediction intervals, and numerical guards.
"""

from datetime import date, timedelta
import pytest
from trending import compute_trend, predict_at


def test_hold_out_regression_basic():
    """Verifies newest point is strictly held out and evaluated against 95% interval."""
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=365 * i) for i in range(5)]
    # Linear aging with realistic measurement scatter (Syx > 0)
    measured = [10.000001, 10.000009, 10.000022, 10.000029, 10.000040]

    rows, stats = compute_trend(dates, measured, nominal=10.0)

    assert stats is not None
    assert stats["n"] == 4, "Fit must use only first 4 points (newest point held out)"
    assert stats["df"] == 2, "df must be n - 2 = 2"
    assert stats["t_crit"] == pytest.approx(4.30265, abs=0.001)
    assert stats["Syx"] > 0, "Real calibration scatter must yield Syx > 0"

    # Check fit roles
    assert rows[0]["fit_role"] == "included"
    assert rows[1]["fit_role"] == "included"
    assert rows[2]["fit_role"] == "included"
    assert rows[3]["fit_role"] == "included"
    assert rows[4]["fit_role"] == "held_out"

    # Held out point has valid prediction interval and passes in-trend
    assert rows[4]["lower"] is not None
    assert rows[4]["upper"] is not None
    assert rows[4]["lower"] < rows[4]["measured_value"] < rows[4]["upper"]
    assert rows[4]["out_of_trend"] is False


def test_held_out_point_out_of_trend_detection():
    """Verifies that an anomalous held-out point is flagged as out-of-trend."""
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=365 * i) for i in range(5)]
    # Point 4 has a major jump (+0.00100)
    measured = [10.000001, 10.000009, 10.000022, 10.000029, 10.001000]

    rows, stats = compute_trend(dates, measured, nominal=10.0)

    assert rows[4]["fit_role"] == "held_out"
    assert rows[4]["out_of_trend"] is True, "Held-out jump must be flagged as out-of-trend"


def test_predict_at_zero_ssx_guard():
    """Ensures predict_at does not crash with ZeroDivisionError when SSx == 0."""
    stats = {
        "slope": 0.0,
        "intercept": 10.0,
        "n": 3,
        "df": 1,
        "xbar": 0.0,
        "Syx": 0.001,
        "SSx": 0.0,  # Zero variance in X
        "t_crit": 12.706
    }
    fitted, lower, upper = predict_at(0.0, stats)
    assert fitted == 10.0
    assert lower == 10.0
    assert upper == 10.0, "Zero SSx must safely return margin = 0 without ZeroDivisionError"


def test_epoch_reset_quarantines_prior_points():
    """Ensures that adjustment events isolate prior calibrations into prior_epoch."""
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=180 * i) for i in range(6)]
    measured = [0.01, 0.02, 0.03, 0.50, 0.51, 0.52]
    # Point 3 marks an electronic adjustment
    adjustments = [False, False, False, True, False, False]

    rows, stats = compute_trend(dates, measured, nominal=0.0, adjustments=adjustments)

    assert rows[0]["fit_role"] == "prior_epoch"
    assert rows[1]["fit_role"] == "prior_epoch"
    assert rows[2]["fit_role"] == "prior_epoch"
    assert rows[0]["in_active_epoch"] is False

    # Active epoch has points 3, 4, 5. Point 5 held out, points 3 and 4 in fit (n = 2 < 3, insufficient)
    assert stats is None  # Needs at least 3 points in active epoch baseline