"""
htbasic_format.py

Core primitive for the HTBasic legacy file generator: given a number AS
IT APPEARS IN THE EXISTING TEMPLATE FILE (e.g. "1.0000134E+7", "0.999916E+9",
".100000761", "100000.759"), format a NEW value using the exact same
notation convention - same scientific/plain choice, same exponent, same
number of decimal places, same leading-zero style. This is how "keep the
exact structure, only replace the numeric value" gets implemented: the
template IS the format spec, we never invent formatting rules of our own.
"""

import re

_SCI_RE = re.compile(r"^(-?)(\d*)\.(\d+)[Ee]([+-]\d+)$")
_PLAIN_RE = re.compile(r"^(-?)(\d*)\.(\d+)$")
_INT_RE = re.compile(r"^(-?)(\d+)$")


def format_like(template: str, new_value: float) -> str:
    """template: the exact numeric substring as it appears in the sample
    file (whitespace already stripped by the caller). Returns the new
    value formatted to match that template's notation exactly."""
    neg = new_value < 0
    abs_value = abs(new_value)

    m = _SCI_RE.match(template)
    if m:
        sign, int_part, frac_part, exp_str = m.groups()
        exponent = int(exp_str)
        decimals = len(frac_part)
        coefficient = abs_value / (10 ** exponent)
        exp_sign = exp_str[0] if exp_str[0] in "+-" else "+"
        return f"{'-' if neg else ''}{coefficient:.{decimals}f}E{exp_sign}{abs(exponent)}"

    m = _PLAIN_RE.match(template)
    if m:
        sign, int_part, frac_part = m.groups()
        decimals = len(frac_part)
        formatted = f"{abs_value:.{decimals}f}"
        if int_part == "" and formatted.startswith("0."):
            formatted = formatted[1:]  # match a template that omits the leading zero (e.g. ".100000761")
        return ("-" if neg else "") + formatted

    m = _INT_RE.match(template)
    if m:
        return ("-" if neg else "") + str(int(round(abs_value)))

    raise ValueError(f"Don't recognize the number format of template value {template!r}")
