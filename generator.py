"""Renders a single certificate PDF from the one predefined template."""
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

NAVY = colors.HexColor("#1f3a5f")
GOLD = colors.HexColor("#b8932f")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "recipient"


def _fit_font_size(text: str, font: str, max_size: int, max_width: float, min_size: int = 14) -> int:
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def render_certificate(path: Path, *, recipient_name: str, title: str, event_name: str,
                       issued_by: str, issue_date: str, description: str | None = None) -> None:
    """Write a landscape A4 certificate PDF to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(w, h))
    c.setTitle(f"{title} - {recipient_name}")

    # Double border
    c.setStrokeColor(NAVY); c.setLineWidth(6); c.rect(25, 25, w - 50, h - 50)
    c.setStrokeColor(GOLD); c.setLineWidth(1.5); c.rect(38, 38, w - 76, h - 76)

    cx, max_w = w / 2, w - 160
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", _fit_font_size(title.upper(), "Helvetica-Bold", 34, max_w))
    c.drawCentredString(cx, h - 120, title.upper())

    c.setFillColor(colors.black); c.setFont("Helvetica", 15)
    c.drawCentredString(cx, h - 170, "This is to certify that")

    c.setFillColor(GOLD)
    c.setFont("Times-BoldItalic", _fit_font_size(recipient_name, "Times-BoldItalic", 44, max_w, 18))
    c.drawCentredString(cx, h - 235, recipient_name)
    c.setStrokeColor(GOLD); c.setLineWidth(1); c.line(cx - 220, h - 247, cx + 220, h - 247)

    c.setFillColor(colors.black); c.setFont("Helvetica", 15)
    c.drawCentredString(cx, h - 285, "has successfully participated in")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", _fit_font_size(event_name, "Helvetica-Bold", 24, max_w))
    c.drawCentredString(cx, h - 320, event_name)

    if description:
        c.setFillColor(colors.HexColor("#444444")); c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(cx, h - 350, description[:110])

    c.setFillColor(colors.black); c.setFont("Helvetica", 12)
    c.drawString(90, 90, f"Date: {issue_date}")
    c.line(w - 290, 98, w - 90, 98)
    c.drawCentredString(w - 190, 80, f"Issued by {issued_by}"[:45])
    c.showPage()
    c.save()
