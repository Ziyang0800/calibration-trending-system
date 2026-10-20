"""
htbasic_export.py

Generates the complete suite of legacy HTBasic 3458A test station files:
  1. RESNOM.txt          (Nominal factor standards: 1Ω, 10M, 100M, 1G)
  2. RESVALUE.TXT        (Transfer standards: 10Ω – 10kΩ)
  3. HIGHRES.txt         (100kΩ standards)
  4. ONEMEG.txt          (1MΩ standards)
  5. Station File        (286300.txt for B-1 / 286325.txt for B-2)
  6. DIVMEANS.TXT        (AC Dividers: 10mV and 100mV across 6 frequencies)
  7. 90xxxx_Extended.txt (33622A 11 cf Data points with cal date and due date)

Safety Rules:
  - Zero silent fallbacks: missing live calibration data strictly raises ValueError.
  - Zero default zeroes: missing 33622A factors fail validation instead of writing 0.0 dB.
  - Byte-level ASCII and CRLF line ending validation on all generated files.
"""

import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from htbasic_format import format_like

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "htbasic_templates")

# Station-to-Resistor & Standard Mapping
SET_STATION_MAPPING = {
    "Set 1": {
        "station": "Station B-1",
        "station_file": "286300.txt",
        "1": "PN010022", "10": "PN010002", "100": "PN010004",
        "1000": "PN010006", "10000": "PN010008", "100000": "PN010010", "1000000": "PN010012",
        "10000000": "PN010014", "100000000": "PN010017", "1000000000": "PN010050",
        "divider_10mv": "PN030002", "divider_100mv": "PN030000",
        "wfg_pn": "PAA0311", "wfg_asset_id": "902470", "wfg_serial": "SG53800187",
    },
    "Set 2": {
        "station": "Station B-2",
        "station_file": "286325.txt",
        "1": "PN010001", "10": "PN010003", "100": "PN010005",
        "1000": "PN010007", "10000": "PN010009", "100000": "PN010011", "1000000": "PN010013",
        "10000000": "PN010015", "100000000": "PN010016", "1000000000": "PN010048",
        "divider_10mv": "PN030001", "divider_100mv": "PN030003",
        "wfg_pn": "PN010063", "wfg_asset_id": "906099", "wfg_serial": "MY53802790",
    },
}

ZERO_POINT_ONE_OHM_OPTIONS = {
    "PN010034": "PN010034 (Set 1's 0.1 Ohm)",
    "EQ358990": "EQ358990 (Set 2's 0.1 Ohm)",
    "PN010069": "PN010069 (Set 3's 0.1 Ohm)",
}

WFG_OPTIONS = {
    "SG53800187": {
        "file_id": "902470",
        "serial": "SG53800187",
        "pn": "PAA0311",
        "default_set": "Set 1",
        "label": "902470 (Set 1 - PAA0311 / SG53800187)"
    },
    "MY53802790": {
        "file_id": "906099",
        "serial": "MY53802790",
        "pn": "PN010063",
        "default_set": "Set 2",
        "label": "906099 (Set 2 - PN010063 / MY53802790)"
    },
    "MY59000394": {
        "file_id": "906773",
        "serial": "MY59000394",
        "pn": "PN010070",
        "default_set": "Set 3",
        "label": "906773 (Set 3 - PN010070 / MY59000394)"
    },
}

REQUIRED_DIVIDER_FREQS = ["1 kHz", "20 kHz", "100 kHz", "300 kHz", "500 kHz", "1 MHz"]

WFG_CF_POINTS = [
    ("cf 10mV @ 4MHz (dB)", "10mV, 4MHz dB error"),
    ("cf 100mV @ 4MHz (dB)", "100mV, 4MHz dB error"),
    ("cf 100mV @ 8MHz (dB)", "100mV, 8MHz dB error"),
    ("cf 100mV @ 10MHz (dB)", "100mV, 10MHz dB error"),
    ("cf 1V @ 4MHz (dB)", "1V, 4MHz dB error"),
    ("cf 1V @ 8MHz (dB)", "1V, 8MHz dB error"),
    ("cf 1V @ 10MHz (dB)", "1V, 10MHz dB error"),
    ("cf 3V @ 2MHz (dB)", "3V, 2MHz dB error"),
    ("cf 3V @ 4MHz (dB)", "3V, 4MHz dB error"),
    ("cf 3V @ 8MHz (dB)", "3V, 8MHz dB error"),
    ("cf 3V @ 10MHz (dB)", "3V, 10MHz dB error"),
]


def _read_template_lines(filename: str) -> list:
    path = os.path.join(TEMPLATE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required HTBasic template missing: {path}")
    with open(path, "rb") as f:
        text = f.read().decode("ascii")
    return text.split("\r\n")


def get_latest_value(conn, asset_number: str):
    row = conn.execute(
        "SELECT c.measured_value FROM calibrations c "
        "JOIN assets a ON a.id = c.asset_id "
        "WHERE a.asset_number = ? "
        "ORDER BY c.cal_date DESC LIMIT 1",
        (asset_number,),
    ).fetchone()
    return row[0] if row else None


def _patch_value_line(line: str, pn: str, conn) -> str:
    new_value = get_latest_value(conn, pn)
    if new_value is None:
        raise ValueError(f"No active calibration reading found in database for reference standard {pn}")

    leading_ws = line[: len(line) - len(line.lstrip())]
    rest = line.lstrip()

    if "!" in rest:
        num_field, _old_comment = rest.split("!", 1)
        comment_part = f"! {pn}"
        field_width = len(num_field)
        new_num = format_like(num_field.strip(), new_value)
        return f"{leading_ws}{new_num.ljust(field_width)}{comment_part}"
    else:
        new_num = format_like(rest.strip(), new_value)
        return f"{leading_ws}{new_num}"


# -----------------------------------------------------------------------------
# 1. Resistor Factor Generators
# -----------------------------------------------------------------------------
def generate_resnom(conn, set_name: str) -> str:
    lines = _read_template_lines("RESNOM.txt")
    lines[1] = _patch_value_line(lines[1], SET_STATION_MAPPING[set_name]["1"], conn)
    lines[3] = _patch_value_line(lines[3], SET_STATION_MAPPING["Set 1"]["10000000"], conn)
    lines[5] = _patch_value_line(lines[5], SET_STATION_MAPPING[set_name]["100000000"], conn)
    lines[7] = _patch_value_line(lines[7], SET_STATION_MAPPING[set_name]["1000000000"], conn)
    lines[9] = _patch_value_line(lines[9], SET_STATION_MAPPING["Set 2"]["10000000"], conn)
    return "\r\n".join(lines)


def generate_resvalue(conn, set_name: str) -> str:
    lines = _read_template_lines("RESVALUE.TXT")
    patch_map = {
        2: "PN010002", 5: "PN010003",
        8: "PN010005", 11: "PN010004",
        14: "PN010007", 17: "PN010006",
        41: "PN010009", 59: "PN010008",
    }
    for idx, pn in patch_map.items():
        lines[idx] = _patch_value_line(lines[idx], pn, conn)
    return "\r\n".join(lines)


def generate_highres(conn, set_name: str) -> str:
    lines = _read_template_lines("HIGHRES.txt")
    patch_map = {1: "PN010011", 5: "PN010010"}
    for idx, pn in patch_map.items():
        lines[idx] = _patch_value_line(lines[idx], pn, conn)
    return "\r\n".join(lines)


def generate_onemeg(conn, set_name: str) -> str:
    lines = _read_template_lines("ONEMEG.txt")
    lines[1] = _patch_value_line(lines[1], "PN010012", conn)
    lines[3] = _patch_value_line(lines[3], "PN010013", conn)
    return "\r\n".join(lines)


def generate_station_file(conn, set_name: str, zero_pt_one_pn: str) -> tuple:
    filename = SET_STATION_MAPPING[set_name]["station_file"]
    lines = _read_template_lines(filename)
    lines[0] = _patch_value_line(lines[0], zero_pt_one_pn, conn)
    return filename, "\r\n".join(lines)


# -----------------------------------------------------------------------------
# 2. AC Voltage Divider Generator (DIVMEANS.TXT - Strict, No Fallbacks)
# -----------------------------------------------------------------------------
def get_divider_ratios(conn, pn: str) -> dict:
    asset = conn.execute("SELECT id FROM assets WHERE asset_number = ?", (pn,)).fetchone()
    if not asset:
        return {}
    asset_id = asset[0]

    ratios = {}
    for f in REQUIRED_DIVIDER_FREQS:
        row = conn.execute(
            "SELECT cr.measured_value FROM calibrations c "
            "JOIN calibration_readings cr ON cr.calibration_id = c.id "
            "JOIN test_points tp ON tp.id = cr.test_point_id "
            "WHERE c.asset_id = ? AND tp.point_name = ? "
            "ORDER BY c.cal_date DESC LIMIT 1",
            (asset_id, f)
        ).fetchone()
        if row and row[0] is not None:
            ratios[f] = row[0]
    return ratios


def generate_divmeans(conn, set_name: str) -> str:
    cfg = SET_STATION_MAPPING[set_name]
    pn_10mv = cfg["divider_10mv"]
    pn_100mv = cfg["divider_100mv"]

    r_10mv = get_divider_ratios(conn, pn_10mv)
    r_100mv = get_divider_ratios(conn, pn_100mv)

    # Strictly verify all 6 frequencies exist (Zero fallback allowed)
    missing_10 = [f for f in REQUIRED_DIVIDER_FREQS if f not in r_10mv]
    missing_100 = [f for f in REQUIRED_DIVIDER_FREQS if f not in r_100mv]

    if missing_10:
        raise ValueError(f"Cannot generate DIVMEANS.TXT: 10mV divider {pn_10mv} is missing live calibration ratios for: {missing_10}")
    if missing_100:
        raise ValueError(f"Cannot generate DIVMEANS.TXT: 100mV divider {pn_100mv} is missing live calibration ratios for: {missing_100}")

    lines = [
        # 1mV (Fixed standards lab characterization standard)
        "1000.280 ! DC-1kHz (For 1mV) PENANG DATA MF",
        "1000.280 ! DC-1kHz (1mV)",
        "1000.280 ! DC-1kHz (1mV)",
        "1000.280 ! DC-1kHz (1mV)",
        "1000.484 ! 20kHz   (1mV)",
        "1000.227 ! 100kHz  (1mV)",
        "999.558  ! 300kHz  (1mV)",
        "999.042  ! 500kHz  (1mV)",
        "1004.203 ! 1MHz    (1mV)",

        # 3mV (Characterized using same ratios as 10mV)
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (For 3mV) SAME AS 10mV {pn_10mv}",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (3mV)",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (3mV)",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (3mV)",
        f"{r_10mv['20 kHz']:.4f} ! 20kHz   (3mV)",
        f"{r_10mv['100 kHz']:.4f} ! 100kHz  (3mV)",
        f"{r_10mv['300 kHz']:.4f} ! 300kHz  (3mV)",
        f"{r_10mv['500 kHz']:.4f} ! 500kHz  (3mV)",
        f"{r_10mv['1 MHz']:.4f} ! 1MHz    (3mV)",

        # 10mV
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (For 10mV) {pn_10mv}",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (10mV)",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (10mV)",
        f"{r_10mv['1 kHz']:.4f} ! DC-1kHz (10mV)",
        f"{r_10mv['20 kHz']:.4f} ! 20kHz   (10mV)",
        f"{r_10mv['100 kHz']:.4f} ! 100kHz  (10mV)",
        f"{r_10mv['300 kHz']:.4f} ! 300kHz  (10mV)",
        f"{r_10mv['500 kHz']:.4f} ! 500kHz  (10mV)",
        f"{r_10mv['1 MHz']:.4f} ! 1MHz    (10mV)",

        # 30mV (Characterized using same ratios as 100mV)
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (For 30mV) SAME AS 100mV {pn_100mv}",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (30mV)",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (30mV)",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (30mV)",
        f"{r_100mv['20 kHz']:.5f} ! 20kHz   (30mV)",
        f"{r_100mv['100 kHz']:.5f} ! 100kHz  (30mV)",
        f"{r_100mv['300 kHz']:.5f} ! 300kHz  (30mV)",
        f"{r_100mv['500 kHz']:.5f} ! 500kHz  (30mV)",
        f"{r_100mv['1 MHz']:.5f} ! 1MHZ    (30mV)",

        # 100mV
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (For 100mV) {pn_100mv}",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (100mV)",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (100mV)",
        f"{r_100mv['1 kHz']:.5f} ! DC-1kHz (100mV)",
        f"{r_100mv['20 kHz']:.5f} ! 20kHz   (100mV)",
        f"{r_100mv['100 kHz']:.5f} ! 100kHz  (100mV)",
        f"{r_100mv['300 kHz']:.5f} ! 300kHz  (100mV)",
        f"{r_100mv['500 kHz']:.5f} ! 500kHz  (100mV)",
        f"{r_100mv['1 MHz']:.5f} ! 1MHZ    (100mV)",
    ]
    return "\r\n".join(lines)


# -----------------------------------------------------------------------------
# 3. Waveform Generator Generator (90xxxx_Extended.txt - Strict, No Zero Injection)
# -----------------------------------------------------------------------------
def generate_33622a_extended(conn, wfg_serial: str) -> tuple:
    if wfg_serial not in WFG_OPTIONS:
        raise ValueError(f"Unrecognized 33622A serial number: '{wfg_serial}'")

    cfg = WFG_OPTIONS[wfg_serial]
    asset = conn.execute("SELECT id, serial FROM assets WHERE serial = ?", (cfg["serial"],)).fetchone()
    if not asset:
        raise ValueError(f"33622A waveform generator (Serial {cfg['serial']}) is not registered in the database.")
    asset_id, serial = asset

    cal_row = conn.execute(
        "SELECT id, cal_date FROM calibrations WHERE asset_id = ? ORDER BY cal_date DESC LIMIT 1",
        (asset_id,)
    ).fetchone()
    if not cal_row:
        raise ValueError(f"33622A waveform generator (Serial {serial}) has no recorded calibration history.")
    cal_id, cal_date_str = cal_row

    cal_d = date.fromisoformat(cal_date_str[:10])
    cal_date_fmt = cal_d.strftime("%d %b %Y")
    cal_due_fmt = (cal_d + relativedelta(months=6)).strftime("%d %b %Y")

    lines = [
        f"{cal_date_fmt} ! Cal Date for 33622A  {cfg['file_id']} {serial}",
        f"{cal_due_fmt} ! Cal Due",
    ]

    missing_pts = []
    for pt_name, comment in WFG_CF_POINTS:
        row = conn.execute(
            "SELECT cr.measured_value FROM calibration_readings cr "
            "JOIN test_points tp ON tp.id = cr.test_point_id "
            "WHERE cr.calibration_id = ? AND tp.point_name = ?",
            (cal_id, pt_name)
        ).fetchone()

        if row is None or row[0] is None:
            missing_pts.append(pt_name)
        else:
            val = float(row[0])
            lines.append(f"{val:+.5f} ! {comment}")

    if missing_pts:
        raise ValueError(f"Cannot generate {cfg['file_id']}_Extended.txt: Missing readings for calibration factor(s): {missing_pts}")

    filename = f"{cfg['file_id']}_Extended.txt"
    return filename, "\r\n".join(lines)


# -----------------------------------------------------------------------------
# 4. Comprehensive Pre-Flight Inspection Validator
# -----------------------------------------------------------------------------
def validate_required_resistors(conn, set_name: str, zero_pt_one_pn: str, wfg_serial: str = "SG53800187") -> list:
    problems = []
    if set_name not in SET_STATION_MAPPING:
        return [{"nominal": "Station Set", "asset_number": set_name, "issue": "Invalid station set selected"}]

    cfg = SET_STATION_MAPPING[set_name]

    # Required 11 Resistors
    req_resistors = [
        ("0.1 Ω", zero_pt_one_pn),
        ("1 Ω", cfg["1"]),
        ("10 Ω", cfg["10"]),
        ("100 Ω", cfg["100"]),
        ("1 kΩ", cfg["1000"]),
        ("10 kΩ", cfg["10000"]),
        ("100 kΩ", cfg["100000"]),
        ("1 MΩ", cfg["1000000"]),
        ("10 MΩ", cfg["10000000"]),
        ("100 MΩ", cfg["100000000"]),
        ("1 GΩ", cfg["1000000000"]),
    ]

    for nom, pn in req_resistors:
        val = get_latest_value(conn, pn)
        if val is None:
            problems.append({"nominal": nom, "asset_number": pn, "issue": "Missing calibration history in database"})

    # Check AC Dividers (Both 10mV and 100mV across all 6 frequencies)
    for div_nom, div_pn in [("10mV Divider", cfg["divider_10mv"]), ("100mV Divider", cfg["divider_100mv"])]:
        r_dict = get_divider_ratios(conn, div_pn)
        missing_freqs = [f for f in REQUIRED_DIVIDER_FREQS if f not in r_dict]
        if missing_freqs:
            problems.append({
                "nominal": div_nom,
                "asset_number": div_pn,
                "issue": f"Missing frequency ratio readings: {', '.join(missing_freqs)} ({len(r_dict)}/6 available)"
            })

    # Check 33622A Waveform Generator (All 11 factors)
    wfg_cfg = WFG_OPTIONS.get(wfg_serial)
    if not wfg_cfg:
        problems.append({"nominal": "Waveform Gen", "asset_number": wfg_serial, "issue": "Unrecognized serial number"})
    else:
        wfg_asset = conn.execute("SELECT id FROM assets WHERE serial = ?", (wfg_cfg["serial"],)).fetchone()
        if not wfg_asset:
            problems.append({"nominal": "Waveform Gen", "asset_number": wfg_cfg["serial"], "issue": "Asset not registered in database"})
        else:
            latest_cal = conn.execute(
                "SELECT id FROM calibrations WHERE asset_id = ? ORDER BY cal_date DESC LIMIT 1",
                (wfg_asset[0],)
            ).fetchone()
            if not latest_cal:
                problems.append({"nominal": "Waveform Gen", "asset_number": wfg_cfg["serial"], "issue": "No calibration history on file"})
            else:
                cal_id = latest_cal[0]
                missing_cf = []
                for pt_name, _ in WFG_CF_POINTS:
                    r = conn.execute(
                        "SELECT cr.measured_value FROM calibration_readings cr "
                        "JOIN test_points tp ON tp.id = cr.test_point_id "
                        "WHERE cr.calibration_id = ? AND tp.point_name = ?",
                        (cal_id, pt_name)
                    ).fetchone()
                    if r is None or r[0] is None:
                        missing_cf.append(pt_name)
                if missing_cf:
                    problems.append({
                        "nominal": "Waveform Gen",
                        "asset_number": wfg_cfg["serial"],
                        "issue": f"Missing {len(missing_cf)}/11 factors: {', '.join(missing_cf)}"
                    })

    return problems


# -----------------------------------------------------------------------------
# 5. Master Package Generator with Strict Integrity Checks
# -----------------------------------------------------------------------------
def generate_all_files(conn, set_name: str, zero_pt_one_pn: str, wfg_serial: str = "SG53800187") -> dict:
    """
    Compiles all 7 station files.
    Pre-validates against missing data and verifies pure ASCII encoding and CRLF endings.
    """
    problems = validate_required_resistors(conn, set_name, zero_pt_one_pn, wfg_serial)
    if problems:
        issues = "; ".join(f"{p['nominal']} ({p['asset_number']}): {p['issue']}" for p in problems)
        raise ValueError(f"Pre-flight verification failed. Package generation blocked: {issues}")

    station_filename, station_content = generate_station_file(conn, set_name, zero_pt_one_pn)
    wfg_filename, wfg_content = generate_33622a_extended(conn, wfg_serial)

    files = {
        "RESNOM.txt": generate_resnom(conn, set_name),
        "RESVALUE.TXT": generate_resvalue(conn, set_name),
        "HIGHRES.txt": generate_highres(conn, set_name),
        "ONEMEG.txt": generate_onemeg(conn, set_name),
        station_filename: station_content,
        "DIVMEANS.TXT": generate_divmeans(conn, set_name),
        wfg_filename: wfg_content,
    }

    # Strict structural and byte-level validation
    for fname, content in files.items():
        if not content:
            raise ValueError(f"Generated file '{fname}' is empty.")
        try:
            content.encode("ascii")
        except UnicodeEncodeError as e:
            raise ValueError(f"Generated file '{fname}' contains non-ASCII characters: {e}")
        if "\n" in content and "\r\n" not in content:
            raise ValueError(f"Generated file '{fname}' does not have strict CRLF line endings.")

    return files