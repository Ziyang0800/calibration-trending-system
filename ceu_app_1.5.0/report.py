"""One-page 'Calibration Equipment Used' PDF, laid out like the MARS print-out (reportlab only)."""
from datetime import datetime
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

RED, GRAY, INK, RULE = HexColor("#E90029"), HexColor("#9A9A9A"), HexColor("#222222"), HexColor("#4A4A4A")
HEADERS = ("Model Number", "Serial Number", "Equipment ID", "Cal Due Date")
COLS = (42, 117, 192, 264)            # x of each column, in points (measured from the sample)
ROW_H = 16.4


def build_pdf(path, rows, job, station, procedure, unit_model="3458A", note=""):
    """rows: list of (model, serial, equipment_id, cal_due_text)."""
    W, H = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Calibration Equipment Used")
    from version import __version__
    c.setAuthor("CEU Validation Tool")
    c.setCreator("CEU Validation Tool v%s" % __version__)

    c.setStrokeColor(RED); c.setLineWidth(1.4)
    c.line(28, H - 32, W - 29, H - 32)                       # top red rule
    c.setFillColor(RED); c.setFont("Helvetica", 14)
    c.drawString(40, H - 56, "Calibration Equipment Used")

    y = H - 68                                              # table top rule
    c.setStrokeColor(RULE); c.setLineWidth(0.4)
    c.line(40, y, 328, y)
    c.setFillColor(GRAY); c.setFont("Helvetica-Bold", 7.5)
    for x, h in zip(COLS, HEADERS):
        c.drawString(x, y - 11, h)
    y -= 15
    c.line(40, y, 328, y)
    c.setFillColor(INK); c.setFont("Helvetica", 7.5)
    for r in rows:
        for x, v in zip(COLS, r):
            c.drawString(x, y - 11, str(v or ""))
        y -= ROW_H
        c.line(40, y, 328, y)

    y -= 20                                                 # details block
    unit = "%s (%s)" % (unit_model, job["serial"])
    for label, value in (("Service:", job["so"]), ("Unit:", unit),
                         ("Results Type:", job["result"]), ("Procedure:", procedure)):
        c.setFillColor(INK)
        c.setFont("Helvetica-BoldOblique", 7.5); c.drawString(45, y, label)
        c.setFont("Helvetica", 7.5);             c.drawString(102, y, value)
        y -= 11.3

    c.setStrokeColor(RED); c.setLineWidth(1.4)
    c.line(28, 51, W - 29, 51)                              # bottom red rule
    c.showPage(); c.save()
    return str(path)
