"""Printable review with source times, provenance and human approval."""
from __future__ import annotations

import threading
from html import escape
from io import BytesIO
from pathlib import Path

from app.reports.review_document import CATEGORIES, ReviewDocument, review_time_label, time_label

_font_lock = threading.Lock()


def build_review_pdf(*, title: str, document: ReviewDocument, source: str,
                     source_hash: str, reviewer: str, reviewed_at: str, version: int,
                     frames: dict[str, bytes] | None = None) -> bytes:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    # ReportLab bundles Vera, including Turkish glyphs; no OS font dependency.
    with _font_lock:
        if "ReviewVera" not in pdfmetrics.getRegisteredFontNames():
            folder = Path(reportlab.__file__).parent / "fonts"
            pdfmetrics.registerFont(TTFont("ReviewVera", str(folder / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont("ReviewVeraBold", str(folder / "VeraBd.ttf")))
            pdfmetrics.registerFontFamily("ReviewVera", normal="ReviewVera", bold="ReviewVeraBold")
    body = ParagraphStyle("ReviewBody", fontName="ReviewVera", fontSize=10, leading=15, spaceAfter=7)
    heading = ParagraphStyle("ReviewHeading", parent=body, fontName="ReviewVeraBold", fontSize=13,
                             leading=18, spaceBefore=10, spaceAfter=7, keepWithNext=True,
                             textColor=colors.HexColor("#174f46"))
    small = ParagraphStyle("ReviewMeta", parent=body, fontSize=8, leading=12,
                           textColor=colors.HexColor("#53636a"))
    title_style = ParagraphStyle("ReviewTitle", parent=heading, fontSize=23, leading=29, spaceAfter=12)

    def paragraph(text: str, style=body):
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    scope = "Maçın tamamı incelendi" if document.scope == "full_match" else "Seçilmiş bölümler incelendi"
    story = [paragraph("MANAGER / MAÇ İNCELEMESİ", small), paragraph(title, title_style),
             paragraph(f"{document.club} - {document.opponent} | {document.match_date or 'Tarih belirtilmedi'}", small),
             paragraph(f"{scope}. İstatistik kapsamı: yalnız kaydedilen gözlemler.", small),
             paragraph(f"Kontrol eden: {reviewer} | {review_time_label(reviewed_at)} | Sürüm {version}", small),
             paragraph("Maç değerlendirmesi", heading), paragraph(document.summary)]
    if document.strengths:
        story.extend([paragraph("İyi yapılanlar", heading), paragraph(document.strengths)])
    story.append(paragraph("Sonraki antrenmanın odağı", heading))
    for i, action in enumerate(document.training_focus, 1):
        story.append(paragraph(f"{i}. {action}"))
    story.append(paragraph("Video ile desteklenen gözlemler", heading))
    story.append(paragraph("Zamanlar kaynak videonun başlangıcına göredir. Klipler teslim paketinin clips klasöründedir.", small))
    for i, finding in enumerate(document.findings, 1):
        head = f"{i:02d}. {finding.title}"
        meta = (f"{CATEGORIES[finding.category]} | {time_label(finding.start)} - {time_label(finding.end)}"
                + (f" | Oyuncu: {finding.player}" if finding.player else ""))
        block = [paragraph(head, heading), paragraph(meta, small),
                 paragraph(f"Gözlem: {finding.observation}"),
                 paragraph(f"Çalışma önerisi: {finding.action}")]
        if finding.next_check:
            block.append(paragraph(f"Sonraki kontrolde: {finding.next_check}"))
        block.append(paragraph(f"Klip: clips/{i:02d}.mp4", small))
        story.append(KeepTogether(block))
        if finding.drawing and frames and str(finding.id) in frames:
            picture = Image(BytesIO(frames[str(finding.id)]))
            scale = min(174 * mm / picture.imageWidth, 90 * mm / picture.imageHeight)
            picture.drawWidth, picture.drawHeight = picture.imageWidth * scale, picture.imageHeight * scale
            story.append(KeepTogether([picture, paragraph(
                f"Kaynak karesi {time_label(finding.drawing.time)} · Analistin çizimi", small)]))
    story.append(KeepTogether([Spacer(1, 5 * mm), paragraph("Kaynak ve kapsam", heading),
                  paragraph(f"Video: {source}\nSHA-256: {source_hash}", small),
                  paragraph("Bu rapor kaydedilmiş insan gözlemlerini içerir. Kamera dışında kalan hareketler ve ölçülmemiş fiziksel değerler hakkında sonuç üretmez. Oyuncu gelişimi için aynı ölçütlerle tekrarlanan incelemeler gerekir.", small)]))
    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("ReviewVera", 8)
        canvas.setFillColor(colors.HexColor("#53636a"))
        canvas.drawString(18 * mm, 12 * mm, "Manager | Kulüp içi kullanım")
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(buffer, pagesize=A4, title=title, author="Manager",
                      leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=22 * mm).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
