"""Haftalık rapor PDF'i — direktöre tek sayfa (rapor backlog #5).

Builder içerik ÜRETMEZ, dizer: arayüz (`/weekly-report`) ya da zamanlanmış iş
hazır metni verir. Saf: DB/HTTP bilmez. reportlab yoksa `ReportlabNotInstalled`.

Girdi sözlüğü:
  club, week_no, week_range, opponent?, score? [a, b], xg_for?, xg_against?
  kpis: [{label, value, delta?}]        — en çok 6 başlık rakamı
  sections: [{title, lines: [str]}]     — maç / sağlık / antrenman / performans
  note?                                  — teknik direktör notu
  generated_at?                          — ISO metin; yoksa şimdi
Bozuk/eksik alanlar atlanır — arayüzden gelen her yapı için bir PDF çıkar.
"""
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from app.reports.pdf import REPORTLAB_AVAILABLE, ReportlabNotInstalled

MAX_KPIS = 6
MAX_LINES_PER_SECTION = 12


def build_weekly_report_pdf(report: dict[str, Any]) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise ReportlabNotInstalled("reportlab kurulu değil — `pip install reportlab>=4.0`")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    club = str(report.get("club") or "tactic11")
    week_no = report.get("week_no")
    title = f"Haftalık Rapor — {club}" + (f" · {week_no}. Hafta" if week_no else "")
    generated = str(report.get("generated_at")
                    or datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm, title=title,
    )
    styles = getSampleStyleSheet()
    grey = colors.HexColor("#666666")
    title_style = ParagraphStyle("WkTitle", parent=styles["Title"], fontSize=16, leading=20, spaceAfter=2)
    meta_style = ParagraphStyle("WkMeta", parent=styles["Normal"], fontSize=9, leading=12, textColor=grey)
    h_style = ParagraphStyle("WkH", parent=styles["Heading3"], fontSize=11.5, leading=14,
                             spaceBefore=5, spaceAfter=2)
    body = ParagraphStyle("WkBody", parent=styles["Normal"], fontSize=9.5, leading=13)
    kpi_label = ParagraphStyle("WkKpiL", parent=styles["Normal"], fontSize=7.5, leading=9, textColor=grey)
    kpi_value = ParagraphStyle("WkKpiV", parent=styles["Normal"], fontSize=14, leading=17,
                               fontName="Helvetica-Bold")

    story: list[Any] = [Paragraph(title, title_style)]
    meta_bits = [b for b in (str(report.get("week_range") or ""), f"Üretim: {generated}") if b]
    opponent, score = report.get("opponent"), report.get("score")
    if opponent and isinstance(score, list | tuple) and len(score) == 2:
        line = f"{club} {score[0]}–{score[1]} {opponent}"
        xg_f, xg_a = report.get("xg_for"), report.get("xg_against")
        if isinstance(xg_f, int | float) and isinstance(xg_a, int | float):
            line += f" · xG {xg_f:.2f}–{xg_a:.2f}"
        meta_bits.insert(0, line)
    story.append(Paragraph(" · ".join(meta_bits), meta_style))
    story.append(Spacer(1, 4 * mm))

    kpis = [k for k in (report.get("kpis") or []) if isinstance(k, dict)][:MAX_KPIS]
    if kpis:
        labels, values = [], []
        for k in kpis:
            val = str(k.get("value", "—"))
            delta = k.get("delta")
            if delta not in (None, ""):
                val += f'  <font size="8" color="#666666">{delta}</font>'
            labels.append(Paragraph(str(k.get("label", "")), kpi_label))
            values.append(Paragraph(val, kpi_value))
        table = Table([labels, values], colWidths=[(178 * mm) / len(kpis)] * len(kpis))
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e5e5")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f7f5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 4 * mm))

    for sec in report.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        lines = [str(ln) for ln in (sec.get("lines") or []) if ln is not None and str(ln).strip()]
        if not lines:
            continue
        story.append(Paragraph(str(sec.get("title", "")), h_style))
        for ln in lines[:MAX_LINES_PER_SECTION]:
            story.append(Paragraph("• " + ln, body))

    note = str(report.get("note") or "").strip()
    if note:
        story.append(Paragraph("Teknik Direktör Notu", h_style))
        story.append(Paragraph(note.replace("\n", "<br/>"), body))

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("tactic11 · veriden türetilmiş özet; kararlar teknik ekibindir.", meta_style))
    doc.build(story)
    return buf.getvalue()
