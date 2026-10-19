"""
report_pdf.py - generates PDF audit reports across all calibration standards:
Standard Resistors, DC Voltage References, AC Dividers, and Waveform Generators.
Aligned to exact 5-decimal precision for Waveform Generators.
"""

import io
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable

from queries import get_asset_detail

STEEL = colors.HexColor("#0a192f")
WARN = colors.HexColor("#d97706")
REVIEWED = colors.HexColor("#1d4ed8")
GREY = colors.HexColor("#64748b")
INK_DIM = colors.HexColor("#475569")


def _status_of(cal: dict) -> tuple:
    if cal.get("display_status") == "excluded" or cal.get("excluded_from_regression"):
        return "Excluded", GREY
    if cal.get("display_status") == "reviewed_out_of_trend":
        return "Reviewed", REVIEWED
    if cal.get("out_of_trend"):
        return "Out of Trend", WARN
    if cal.get("predicted") is not None:
        return "In Trend", colors.HexColor("#059669")
    return "Baseline", GREY


def _render_chart_png(calibrations: list, asset: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(6.4, 2.8), dpi=150)

    xs = [c["accumulated_days"] for c in calibrations]
    measured = [c["measured_value"] for c in calibrations]
    predicted = [c.get("predicted") for c in calibrations]
    lower = [c.get("lower") for c in calibrations]
    upper = [c.get("upper") for c in calibrations]

    has_limits = any(v is not None for v in lower) and any(v is not None for v in upper)
    if has_limits:
        valid_indices = [i for i, v in enumerate(lower) if v is not None and upper[i] is not None]
        valid_xs = [xs[i] for i in valid_indices]
        valid_low = [lower[i] for i in valid_indices]
        valid_up = [upper[i] for i in valid_indices]
        valid_pred = [predicted[i] for i in valid_indices]

        ax.fill_between(valid_xs, valid_low, valid_up, color="#3b82f6", alpha=0.12, linewidth=0)
        ax.plot(valid_xs, valid_up, color="#93c5fd", linestyle="-", linewidth=1.0, label="95% Upper")
        ax.plot(valid_xs, valid_low, color="#93c5fd", linestyle="-", linewidth=1.0, label="95% Lower")
        ax.plot(valid_xs, valid_pred, color="#64748b", linestyle=":", linewidth=1.2, label="Prediction")

    point_colors = []
    for c in calibrations:
        if c.get("excluded_from_regression"):
            point_colors.append("#94a3b8")
        elif c.get("display_status") == "reviewed_out_of_trend":
            point_colors.append("#1d4ed8")
        elif c.get("out_of_trend"):
            point_colors.append("#d97706")
        else:
            point_colors.append("#0a192f")

    ax.scatter(xs, measured, c=point_colors, s=20, zorder=3, label="Measured")

    unit = asset.get("unit", "")
    y_title = f"Measured Value ({unit})" if unit else "Measured Value"
    ax.set_xlabel("Accumulated days", fontsize=7.5, color="#475569")
    ax.set_ylabel(y_title, fontsize=7.5, color="#475569")
    ax.tick_params(labelsize=7, colors="#475569")
    ax.ticklabel_format(style="plain", useOffset=False, axis="y")
    ax.grid(True, linestyle="--", alpha=0.3, color="#cbd5e1")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=6.5, frameon=False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _format_val(val, asset: dict):
    if val is None:
        return "—"
    cat = asset.get("category", "")
    if cat == "dcv_reference":
        return f"{val:.8f} V"
    if cat == "ac_divider":
        return f"{val:.5f}"
    if cat == "waveform_generator":
        return f"{val:+.5f} dB"  # Exact 5 decimals with sign
    nom = asset.get("nominal_ohms", 1.0)
    integer_digits = len(str(abs(int(nom)))) if abs(nom) >= 1 else 1
    decimals = max(0, 9 - integer_digits)
    return f"{val:,.{decimals}f} Ω"


def _asset_flowables(detail: dict, styles) -> list:
    asset = detail["asset"]
    calibrations = detail["calibrations"]
    test_points = detail.get("test_points", [])
    flow = []

    title = asset["model"] or asset["serial"]
    flow.append(Paragraph(f"<b>{escape(str(title))}</b>", styles["AssetTitle"]))

    cat_name = {
        "dcv_reference": "DC Voltage Reference",
        "ac_divider": "AC Voltage Divider",
        "waveform_generator": "Waveform Generator",
    }.get(asset["category"], "Standard Resistor")

    flow.append(Paragraph(
        f"Serial: <b>{escape(str(asset['serial']))}</b> &nbsp;·&nbsp; "
        f"Equipment ID: <b>{escape(str(asset['asset_number'] or '—'))}</b> &nbsp;·&nbsp; "
        f"Category: <b>{cat_name}</b> &nbsp;·&nbsp; "
        f"Set: <b>{escape(str(asset['set_id'] or '—'))}</b>",
        styles["AssetSub"],
    ))
    flow.append(Spacer(1, 6))

    if not calibrations:
        flow.append(Paragraph("No calibration history on file.", styles["Body"]))
        flow.append(Spacer(1, 14))
        flow.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), thickness=0.5))
        flow.append(Spacer(1, 14))
        return flow

    # Multi-point glance table on PDF (AC Dividers & 33622A)
    if test_points and len(test_points) > 1:
        matrix_data = [["Test Point", "Classification", "Latest Reading", "Drift", "Status"]]
        for tp in test_points[:8]:
            drift_str = "—"
            if tp.get("drift") is not None:
                drift_str = f"{tp['drift']:+.4f} dB" if asset["unit"] == "dB" else f"{tp['drift']:.5f}"
            matrix_data.append([
                tp["point_name"],
                tp.get("group_name", "—"),
                f"{tp['latest_value']:.5f} {asset['unit']}" if tp.get("latest_value") is not None else "—",
                drift_str,
                "In Trend" if tp.get("status") == "ok" else ("Reviewed" if tp.get("status") == "reviewed_out_of_trend" else ("Out of Trend" if tp.get("status") == "out_of_trend" else "Baseline"))
            ])
        mt = Table(matrix_data, hAlign="LEFT", colWidths=[1.6*inch, 1.4*inch, 1.3*inch, 1.0*inch, 1.0*inch])
        mt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK_DIM),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        flow.append(mt)
        flow.append(Spacer(1, 6))

    # Trend Chart
    has_trend = calibrations and calibrations[0].get("predicted") is not None
    if has_trend or len(calibrations) >= 4:
        png_bytes = _render_chart_png(calibrations, asset)
        flow.append(Image(io.BytesIO(png_bytes), width=4.8 * inch, height=2.1 * inch))
        flow.append(Spacer(1, 6))

    # Latest Cal Details
    latest = calibrations[-1]
    status_label, status_color = _status_of(latest)

    table_data = [
        ["Latest Cal", f"Measured ({asset.get('unit', '')})", "Predicted", "95% Lower", "95% Upper", "Status"],
        [
            latest["date"],
            _format_val(latest["measured_value"], asset),
            _format_val(latest.get("predicted"), asset),
            _format_val(latest.get("lower"), asset),
            _format_val(latest.get("upper"), asset),
            status_label,
        ],
    ]
    t = Table(table_data, hAlign="LEFT", colWidths=[0.9*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.0*inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK_DIM),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#e2e8f0")),
        ("TEXTCOLOR", (5, 1), (5, 1), status_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(t)

    if latest.get("pressure_hpa"):
        flow.append(Spacer(1, 3))
        loc_str = f" · {latest['location']}" if latest.get("location") else ""
        flow.append(Paragraph(f"<font size=7 color='#64748b'>Ambient Pressure: {int(latest['pressure_hpa'])} hPa{loc_str}</font>", styles["Comment"]))

    if latest.get("reviewer_comment"):
        flow.append(Spacer(1, 3))
        flow.append(Paragraph(f"<i>Reviewer Note: {escape(str(latest['reviewer_comment']))}</i>", styles["Comment"]))

    flow.append(Spacer(1, 14))
    flow.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), thickness=0.5))
    flow.append(Spacer(1, 14))
    return flow


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("AssetTitle", parent=styles["Heading2"], fontSize=12, spaceAfter=2, textColor=STEEL))
    styles.add(ParagraphStyle("AssetSub", parent=styles["Normal"], fontSize=8, textColor=INK_DIM))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=8))
    styles.add(ParagraphStyle("Comment", parent=styles["Normal"], fontSize=7.5, textColor=INK_DIM))
    return styles


def generate_report(conn, asset_ids: list, out_path: str) -> str:
    styles = _build_styles()
    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        leftMargin=0.5*inch, rightMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch,
    )

    story = [
        Paragraph("<b>Calibration Standards Trending Report</b>", styles["Title"]),
        Paragraph(f"Generated: {datetime.now():%Y-%m-%d %H:%M} · Standards Laboratory Quality Record", styles["AssetSub"]),
        Spacer(1, 14),
    ]

    for asset_id in asset_ids:
        detail = get_asset_detail(conn, asset_id)
        if detail is None:
            continue
        story.extend(_asset_flowables(detail, styles))

    doc.build(story)
    return out_path