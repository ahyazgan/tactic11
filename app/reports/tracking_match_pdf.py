"""Maç sonu raporu PDF'i — takip verisinden otomatik, insan yorumu içermez.

Girdi `GET /tracking/matches/{id}/report` yanıtının kendisidir; builder yeni sayı üretmez,
yalnız dizer. Takımlar "Biz / Rakip" diye `our_side`a göre adlandırılır. Rakip analizinde
(`perspective="scout"`) video rakibin başka bir maçıdır: `our_side` izlenen takımdır, adlar
"İzlenen / Karşısındaki" olur ve raporun `notes` cümleleri "Nasıl oynuyor" bölümüne dizilir. Güvenilmez dilimler
tabloda işaretlenir; motorun ve fiziksel yükün sınırları raporun sonunda aynen yazılır.

Yazı tipi: reportlab'ın içindeki Vera (Türkçe harfleri taşır; sistem fontuna bağımlılık yok).
Saf: DB/HTTP bilmez.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from app.reports.pdf import REPORTLAB_AVAILABLE, ReportlabNotInstalled

Side = Literal["home", "away"]
Perspective = Literal["ours", "scout"]
FONT, FONT_BOLD = "MatchVera", "MatchVeraBold"
MAX_FINDINGS = 12
US_COLOR, THEM_COLOR = "#1f6b4f", "#b5651d"
_font_lock = threading.Lock()


def _register_fonts() -> None:
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    with _font_lock:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            folder = Path(reportlab.__file__).parent / "fonts"
            pdfmetrics.registerFont(TTFont(FONT, str(folder / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(folder / "VeraBd.ttf")))
            pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)


def _num(value: Any, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _pct(value: Any) -> str:
    return "—" if value is None else f"%{value * 100:.1f}"


def _line(summary: dict[str, Any]) -> str:
    """"38.2 m · Orta blok"; yön bilinmiyorsa "—"."""
    if summary.get("def_line_m") is None:
        return "—"
    return f"{_num(summary['def_line_m'])} m · {summary.get('block') or ''}".rstrip(" ·")


def _minutes(row: dict[str, Any]) -> str:
    return f"{row['from_minute']:g}–{row['to_minute']:g}'"


def build_tracking_match_pdf(report: dict[str, Any], *, our_side: Side = "home", title: str | None = None,
                             generated_at: str | None = None, perspective: Perspective = "ours") -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise ReportlabNotInstalled("reportlab kurulu değil — `pip install reportlab>=4.0`")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _register_fonts()
    their_side: Side = "away" if our_side == "home" else "home"
    scout = perspective == "scout"
    name = {our_side: "İzlenen", their_side: "Karşısındaki"} if scout else {our_side: "Biz", their_side: "Rakip"}
    color = {our_side: US_COLOR, their_side: THEM_COLOR}
    title = title or f"{'Rakip analizi' if scout else 'Maç sonu raporu'} · maç {report.get('match_id', '')}".strip()
    generated = generated_at or datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M")

    body = ParagraphStyle("MrBody", fontName=FONT, fontSize=9, leading=12.5)
    small = ParagraphStyle("MrSmall", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#5b6670"))
    head = ParagraphStyle("MrHead", parent=body, fontName=FONT_BOLD, fontSize=11.5, leading=15, spaceBefore=7,
                          spaceAfter=3, keepWithNext=True, textColor=colors.HexColor("#174f46"))
    title_style = ParagraphStyle("MrTitle", parent=head, fontSize=17, leading=21, spaceBefore=0)
    cell = ParagraphStyle("MrCell", parent=body, fontSize=8, leading=10)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(text), style)

    def side_label(side: Side, suffix: str = "") -> Paragraph:
        return Paragraph(f'<font color="{color[side]}"><b>{escape(name[side] + suffix)}</b></font>', cell)

    def grid(rows: list[list[Any]], widths: list[float], header_rows: int = 1) -> Table:
        table = Table(rows, colWidths=widths, repeatRows=header_rows)
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), FONT, 8),
            ("FONT", (0, 0), (-1, header_rows - 1), FONT_BOLD, 7.5),
            ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.HexColor("#5b6670")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.5, colors.HexColor("#9aa5ad")),
            ("LINEBELOW", (0, header_rows), (-1, -1), 0.25, colors.HexColor("#e1e5e8")),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return table

    teams = report.get("teams") or {}
    slices = report.get("slices") or []
    physical = report.get("physical") or {}
    story: list[Any] = [
        p("TACTIC11 · " + ("RAKİP ANALİZİ · " if scout else "") + "TAKİP VERİSİNDEN OTOMATİK RAPOR", small),
        p(title, title_style),
        p(f"Üretim: {generated} · dilim {report.get('slice_minutes', '—')} dk · {len(slices)} dilim. "
          "Bu sayfa makine çıktısıdır; yorum ve karar teknik ekibindir.", small),
        p("Maç ortalaması (güvenilir dilimler)", head),
    ]
    summary_rows: list[list[Any]] = [["", "Savunma hattı", "Genişlik", "Derinlik", "Kompaktlık", "Pres",
                                      "Güvenilir dilim"]]
    for side in (our_side, their_side):
        s = (teams.get(side) or {}).get("summary")
        if s is None:
            summary_rows.append([side_label(side), "—", "—", "—", "—", "—", "0"])
        else:
            summary_rows.append([side_label(side), _line(s), f"{_num(s['width_m'])} m", f"{_num(s['depth_m'])} m",
                                 f"{_num(s['compactness_m'])} m", _num(s.get("press_index"), 2),
                                 str(s.get("reliable_slices", "—"))])
    story.append(grid(summary_rows, [24 * mm, 40 * mm, 22 * mm, 22 * mm, 24 * mm, 20 * mm, 30 * mm]))
    if not (report.get("direction") or {}).get("known"):
        story.append(p("Saha yönü verilmediği için savunma hattı yazılmadı.", small))

    if scout:
        story.append(p("Nasıl oynuyor (bu maçın sayılarından)", head))
        notes = (report.get("notes") or {}).get(our_side) or []
        story.extend(p(f"• {note}", body) for note in notes)
        if not notes:
            story.append(p("Güvenilir dilim olmadığı için not çıkarılmadı.", body))
        story.append(p("Tek maçtır; rakibin alışkanlığı için birkaç maçın raporu birlikte okunmalı.", small))

    story.append(p("Öne çıkanlar (maç ortalamasından eşik kadar sapan dilimler)", head))
    findings = report.get("findings") or []
    if not findings:
        story.append(p("Hiçbir dilim maç ortalamasından eşik kadar sapmadı.", body))
    for f in findings[:MAX_FINDINGS]:
        unit = "" if f.get("metric") == "press_index" else " m"
        delta = f.get("delta", 0)
        side = f.get("side", our_side)
        story.append(Paragraph(
            f"{escape(_minutes(f))} <font color=\"{color.get(side, '#000000')}\"><b>{escape(name.get(side, side))}</b></font> "
            f"{escape(str(f.get('text', '')))} ({'+' if delta > 0 else ''}{delta}{unit})", body))
    if len(findings) > MAX_FINDINGS:
        story.append(p(f"… ve {len(findings) - MAX_FINDINGS} bulgu daha (arayüzde tam liste).", small))

    story.append(p("Dilim dilim takım şekli", head))
    columns = ["Oyuncu", "Hat", "Gen.", "Der.", "Komp.", "Pres"]
    shape_rows: list[list[Any]] = [["Dakika", *columns, "", *columns]]

    def team_cells(t: dict[str, Any]) -> list[str]:
        return [_num(t.get("players_mean")), _num(t.get("def_line_m")), _num(t.get("width_m")), _num(t.get("depth_m")),
                _num(t.get("compactness_m")), _num(t.get("press_index"), 2)]

    for row in slices:
        ours, theirs = row.get(our_side) or {}, row.get(their_side) or {}
        mark = "" if ours.get("reliable") and theirs.get("reliable") else " *"
        shape_rows.append([_minutes(row) + mark, *team_cells(ours), "", *team_cells(theirs)])
    widths = [20 * mm] + [12.5 * mm] * 6 + [4 * mm] + [12.5 * mm] * 6
    shape_head = [["", side_label(our_side), *[""] * 6, side_label(their_side), *[""] * 5]]
    story.append(_with_band(grid(shape_head + shape_rows, widths, header_rows=2), TableStyle, (1, 6), (8, 13)))
    story.append(p("* güvenilmez dilim: az kare ya da az görünür oyuncu; maç ortalamasına girmez.", small))

    if physical:
        story.append(p("Fiziksel yük (takım düzeyi, oyuncu bazında değil)", head))
        load_rows: list[list[Any]] = [["", "Tempo (m/dk)", "Yüksek hız", "Sprint", "Oyuncu-dakika"]]
        for side in (our_side, their_side):
            load = (physical.get("teams") or {}).get(side)
            load_rows.append([side_label(side), *(["—"] * 4 if load is None else
                              [_num(load.get("m_per_player_min")), _pct(load.get("hsr_share")),
                               _pct(load.get("sprint_share")), _num(load.get("player_minutes"))])])
        story.append(grid(load_rows, [30 * mm, 36 * mm, 36 * mm, 36 * mm, 40 * mm]))

    limits = [*(report.get("limits") or []), *(physical.get("limits") or [])]
    if limits:
        block = [p("Bu raporu okurken", head)] + [p(f"• {limit}", small) for limit in limits]
        story.append(KeepTogether(block))
    story.append(Spacer(1, 3 * mm))
    story.append(p("tactic11 · veriden türetilmiş özet; kararlar teknik ekibindir.", small))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    doc.build(story)
    return buf.getvalue()


def _with_band(table: Any, style: Callable[..., Any], *spans: tuple[int, int]) -> Any:
    """İki başlık satırlı tabloda takım adını sütun grubunun üstüne yayar."""
    table.setStyle(style([("SPAN", (a, 0), (b, 0)) for a, b in spans] + [("ALIGN", (0, 0), (-1, 0), "CENTER")]))
    return table
