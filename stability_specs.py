"""
stability_specs.py

Manufacturer stability specifications, used as a SEPARATE cross-check
against the observed drift between two consecutive calibrations. This is
deliberately independent of - and never combined with - the regression /
95% prediction interval analysis in trending.py. Nothing here feeds into
compute_trend(), and nothing from compute_trend() feeds into this.

INTERPRETATION NOTE - please double check this matches what you intended:
each spec is modeled as an allowance that's a function of the INTERVAL
LENGTH between two consecutive calibrations (e.g. "742A-1: 6 months
+-5ppm, 12 months +-8ppm" means "an ~6-month gap gets a +-5ppm allowance,
an ~12-month gap gets +-8ppm", interpolated/extrapolated for whatever the
ACTUAL elapsed interval between the two real calibrations turns out to
be). This is NOT keyed to the asset's total age in service - two
resistors of the same model, one brand new and one 8 years old, get the
same allowance for the same-length interval. That matches requirement #2
("elapsed time between the latest and immediately preceding
calibration"). If you actually meant age-based tiering instead (a
mature asset should use a different rate than a brand-new one even for
the same interval length), that needs each asset's install/first-use
date, which isn't currently tracked - let me know if that's the real
intent.

Beyond the last explicitly specified checkpoint, the final segment's
rate is carried forward indefinitely, UNLESS an explicit
"ongoing_rate_ppm_per_year" is given (used for specs like ESI SR104
where the published "thereafter" rate is different from the rate
implied by the last two checkpoints). This is a reasonable default,
not a guarantee - manufacturers rarely publish beyond what's given here.
"""

from datetime import date

DAYS_PER_MONTH = 30.4368  # average month length (365.25/12)

# checkpoints: list of (months_elapsed, cumulative_ppm_allowance) - point (0,0) is implicit.
# ongoing_rate_ppm_per_year: explicit override for extrapolation beyond the last
# checkpoint, only set when the source spec gives a "thereafter" rate that
# differs from what the last segment's own slope would imply.
STABILITY_SPECS = {
    "9334A-0.1": {
        "checkpoints": [(12, 2.5), (24, 4.5)],  # initial 12mo +-2.5ppm, second year +-2ppm more
        "description": "Initial 12 months: \u00b12.5 ppm  |  Second year: \u00b12 ppm",
    },
    "9334-0.1": {  # same physical model as 9334A-0.1 - source data spells it without the "A" for one asset
        "checkpoints": [(12, 2.5), (24, 4.5)],
        "description": "Initial 12 months: \u00b12.5 ppm  |  Second year: \u00b12 ppm",
    },
    "L&N 4221B": {
        "checkpoints": [(12, 10.0)],  # +-10ppm/year, flat rate (single checkpoint -> constant slope through origin)
        "description": "\u00b110 ppm/year",
    },
    "742A-1": {
        "checkpoints": [(6, 5.0), (12, 8.0)],
        "description": "6 months: \u00b15 ppm  |  12 months: \u00b18 ppm",
    },
    "742A-10": {
        "checkpoints": [(6, 5.0), (12, 8.0)],
        "description": "6 months: \u00b15 ppm  |  12 months: \u00b18 ppm",
    },
    "742A-100": {
        "checkpoints": [(6, 4.0), (12, 6.0)],
        "description": "6 months: \u00b14 ppm  |  12 months: \u00b16 ppm",
    },
    "742A-1K": {
        "checkpoints": [(6, 4.0), (12, 6.0)],
        "description": "6 months: \u00b14 ppm  |  12 months: \u00b16 ppm",
    },
    "ESI SR104": {
        "checkpoints": [(24, 2.0)],  # +-1ppm/year for first 2 years = 2ppm cumulative at 24mo
        "ongoing_rate_ppm_per_year": 0.5,  # explicit "thereafter" rate - NOT the same as the 0-24mo segment's slope
        "description": "First 2 years: \u00b11 ppm/year  |  Thereafter: \u00b10.5 ppm/year",
    },
    "742A-100K": {
        "checkpoints": [(6, 4.0), (12, 6.0)],
        "description": "6 months: \u00b14 ppm  |  12 months: \u00b16 ppm",
    },
    "742A-1M": {
        "checkpoints": [(6, 6.0), (12, 8.0)],
        "description": "6 months: \u00b16 ppm  |  12 months: \u00b18 ppm",
    },
    "742A-10M": {
        "checkpoints": [(6, 6.0), (12, 9.0)],
        "description": "6 months: \u00b16 ppm  |  12 months: \u00b19 ppm",
    },
    "9334A-1G": {
        "checkpoints": [(12, 35.0), (24, 65.0)],  # initial 12mo +-35ppm, second year +-30ppm more
        "description": "Initial 12 months: \u00b135 ppm  |  Second year: \u00b130 ppm",
    },
    "9334A-100M": {
        "checkpoints": [(12, 20.0), (24, 30.0)],  # initial 12mo +-20ppm, second year +-10ppm more
        "description": "Initial 12 months: \u00b120 ppm  |  Second year: \u00b110 ppm",
    },
    "GUI 9334": {  # same physical model as 9334A-100M - one asset's model is stored as "GUI 9334" in the database
        "checkpoints": [(12, 20.0), (24, 30.0)],
        "description": "Initial 12 months: \u00b120 ppm  |  Second year: \u00b110 ppm",
    },
}


def get_spec_description(model: str):
    """Human-readable spec text for display (e.g. '6 months: \u00b15 ppm |
    12 months: \u00b18 ppm') - or None if no spec is on file for this model."""
    if model is None:
        return None
    spec = STABILITY_SPECS.get(model)
    return spec["description"] if spec else None


def get_stability_allowance(model: str, elapsed_days: float):
    """
    Returns the allowed |drift| in ppm for an interval of the given length,
    per that model's manufacturer stability spec - or None if no spec is
    on file for this model (caller should treat that as "not assessable",
    not as "zero allowance").
    """
    if model is None:
        return None
    spec = STABILITY_SPECS.get(model)
    if spec is None:
        return None

    checkpoints = [(0.0, 0.0)] + list(spec["checkpoints"])
    elapsed_months = elapsed_days / DAYS_PER_MONTH

    for i in range(len(checkpoints) - 1):
        m0, a0 = checkpoints[i]
        m1, a1 = checkpoints[i + 1]
        if elapsed_months <= m1:
            if m1 == m0:
                return a1
            frac = (elapsed_months - m0) / (m1 - m0)
            return a0 + frac * (a1 - a0)

    # beyond the last checkpoint: extrapolate
    m_last, a_last = checkpoints[-1]
    if "ongoing_rate_ppm_per_year" in spec:
        rate_per_month = spec["ongoing_rate_ppm_per_year"] / 12.0
    else:
        m_prev, a_prev = checkpoints[-2]
        rate_per_month = (a_last - a_prev) / (m_last - m_prev) if m_last != m_prev else 0.0
    return a_last + rate_per_month * (elapsed_months - m_last)


def assess_drift(model: str, observed_drift_ppm: float, elapsed_days: float) -> dict:
    """
    Convenience wrapper: returns a dict with the allowance and whether the
    observed drift exceeds it, or {'allowance_ppm': None, ...} if the
    model has no spec on file.
    """
    allowance = get_stability_allowance(model, elapsed_days)
    if allowance is None:
        return {"allowance_ppm": None, "exceeds": None, "elapsed_days": elapsed_days}
    return {
        "allowance_ppm": allowance,
        "exceeds": abs(observed_drift_ppm) > allowance,
        "elapsed_days": elapsed_days,
    }
