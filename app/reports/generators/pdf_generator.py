"""
app/reports/generators/pdf_generator.py
──────────────────────────────────────────
PDF report generator using ReportLab.

generate_pdf(title, sections) → bytes

A section is a dict:
  {"heading": str, "paragraphs": [str], "table": {"headers": [...], "rows": [[...]]}}
"""

from __future__ import annotations
import io
from datetime import datetime, timezone
from typing import Any, Optional

from reportlab.lib          import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles   import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units    import cm
from reportlab.platypus     import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums    import TA_CENTER, TA_LEFT


# ── Brand colours ─────────────────────────────────────────────
BRAND_BLUE  = colors.HexColor("#2563EB")
BRAND_LIGHT = colors.HexColor("#EFF6FF")
DARK_GREY   = colors.HexColor("#374151")
MID_GREY    = colors.HexColor("#9CA3AF")
ROW_ALT     = colors.HexColor("#F9FAFB")


def generate_pdf(
    title:    str,
    sections: list[dict[str, Any]],
    subtitle: Optional[str] = None,
    period:   Optional[str] = None,
) -> bytes:
    """
    Generate a branded PDF report.

    Args:
        title    : report title shown in the header
        sections : list of section dicts
        subtitle : optional subtitle line
        period   : e.g. "last_30_days"

    Returns:
        PDF as bytes
    """
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
    )

    styles  = getSampleStyleSheet()
    story   = []

    # ── Title block ───────────────────────────────────────────
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=BRAND_BLUE,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    sub_style = ParagraphStyle(
        "ReportSub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=MID_GREY,
        spaceAfter=2,
    )
    ts  = datetime.now(tz=timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    per = period.replace("_", " ").title() if period else ""

    story.append(Paragraph(title, title_style))
    if subtitle:
        story.append(Paragraph(subtitle, sub_style))
    story.append(Paragraph(f"Generated: {ts}" + (f" | Period: {per}" if per else ""), sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_BLUE, spaceAfter=12))

    # ── Sections ──────────────────────────────────────────────
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=DARK_GREY,
        spaceBefore=14,
        spaceAfter=6,
        borderPad=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        textColor=DARK_GREY,
        leading=14,
        spaceAfter=4,
    )

    for section in sections:
        # Heading
        if heading := section.get("heading"):
            story.append(Paragraph(heading, heading_style))

        # Paragraphs
        for para in section.get("paragraphs", []):
            story.append(Paragraph(str(para), body_style))

        # Table
        if tbl := section.get("table"):
            headers = tbl.get("headers", [])
            rows    = tbl.get("rows", [])
            if headers and rows:
                story.append(_make_table(headers, rows))
                story.append(Spacer(1, 6))

        # KPI cards (simple two-column grid)
        if kpis := section.get("kpis"):
            story.append(_make_kpi_block(kpis, body_style))

        story.append(Spacer(1, 8))

    # ── Footer note ───────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY, spaceBefore=12))
    story.append(Paragraph(
        "AI Customer Support — Confidential Report",
        ParagraphStyle("Footer", parent=styles["Normal"],
                       fontSize=8, textColor=MID_GREY, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buffer.getvalue()


# ── Helpers ───────────────────────────────────────────────────

def _make_table(headers: list[str], rows: list[list]) -> Table:
    """Build a styled ReportLab Table."""
    col_count = len(headers)
    page_w    = A4[0] - 4 * cm
    col_w     = page_w / col_count

    data = [headers] + [
        [str(c)[:80] if c is not None else "" for c in row]
        for row in rows
    ]

    tbl = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",  (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING",  (0, 0), (-1, 0), 6),
        # Data rows
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING",  (0, 1), (-1, -1), 4),
        # Grid
        ("GRID",        (0, 0), (-1, -1), 0.25, MID_GREY),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _make_kpi_block(kpis: list[dict], style) -> Table:
    """
    Render KPI cards as a 2-column table.
    kpis: [{"label": str, "value": str/int/float, "unit": str}, ...]
    """
    rows = []
    for i in range(0, len(kpis), 2):
        left  = kpis[i]
        right = kpis[i + 1] if i + 1 < len(kpis) else {}
        rows.append([
            _kpi_cell(left),
            _kpi_cell(right) if right else "",
        ])

    page_w = A4[0] - 4 * cm
    tbl    = Table(rows, colWidths=[page_w / 2, page_w / 2])
    tbl.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _kpi_cell(kpi: dict) -> str:
    if not kpi:
        return ""
    label = kpi.get("label", "")
    value = kpi.get("value", "")
    unit  = kpi.get("unit", "")
    trend = kpi.get("trend", "")
    arrow = "▲" if trend == "up" else ("▼" if trend == "down" else "")
    return f"<b>{label}</b><br/>{value}{unit} {arrow}"
