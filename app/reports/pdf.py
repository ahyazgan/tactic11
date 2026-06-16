"""PDF rapor üretici (Faz 5 #16).

Saf builder — AgentOutput row alır, reportlab Platypus ile A4 PDF
döndürür. reportlab opsiyonel paket: kurulmamışsa `REPORTLAB_AVAILABLE`
False olur, endpoint katmanı 503 verir, sistem çalışmaya devam eder.

Yapı:
1) Header: agent_name + version + subject + updated_at
2) Summary paragrafı (NL, 1-2 cümle)
3) output_json key-value tablosu (özyinelemeli düz format, max derinlik 3)

Tasarım kuralı: bu modül DB veya HTTP bilmez — caller AgentOutput tipinde
veri verir, bytes alır. Test edilebilir.
"""
from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover — opsiyonel paket
    REPORTLAB_AVAILABLE = False
    A4 = None


# JSON key-value tablosunda gösterilecek max satır (gürültü engelleme)
MAX_TABLE_ROWS = 40
# Nested dict/list değerini düz string'e çevirirken max derinlik
MAX_NEST_DEPTH = 3


class ReportlabNotInstalled(RuntimeError):
    """reportlab paketi yok — pip install reportlab ile kurun."""


def _format_value(value: Any, depth: int = 0) -> str:
    """Nested JSON değerini okunabilir tek satıra düzleştir."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "evet" if value else "hayır"
    if isinstance(value, (int, float, str)):
        return str(value)
    if depth >= MAX_NEST_DEPTH:
        return "{…}" if isinstance(value, dict) else "[…]"
    if isinstance(value, dict):
        parts = [
            f"{k}: {_format_value(v, depth + 1)}"
            for k, v in list(value.items())[:5]
        ]
        suffix = f" (+{len(value) - 5} alan)" if len(value) > 5 else ""
        return "{" + ", ".join(parts) + suffix + "}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        first = _format_value(value[0], depth + 1)
        suffix = f" (+{len(value) - 1})" if len(value) > 1 else ""
        return f"[{first}{suffix}]"
    return str(value)


def _flatten_json(data: dict[str, Any]) -> list[tuple[str, str]]:
    """output_json'u (anahtar, değer) çiftlerine düzleştir; max satırla sınırla."""
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        rows.append((str(key), _format_value(value)))
        if len(rows) >= MAX_TABLE_ROWS:
            rows.append(("…", f"({len(data) - len(rows) + 1} alan daha)"))
            break
    return rows


def build_agent_output_pdf(
    *,
    agent_name: str,
    agent_version: str,
    subject_type: str,
    subject_id: int,
    summary: str,
    output_json: dict[str, Any] | str,
    updated_at: datetime | None = None,
    title: str | None = None,
) -> bytes:
    """AgentOutput row'undan A4 PDF üret.

    reportlab kurulu değilse ReportlabNotInstalled fırlatır — caller HTTP
    503 vermeli.
    """
    if not REPORTLAB_AVAILABLE:
        raise ReportlabNotInstalled(
            "reportlab kurulu değil — `pip install reportlab>=4.0`",
        )

    if isinstance(output_json, str):
        try:
            data = json.loads(output_json)
        except json.JSONDecodeError:
            data = {"raw": output_json}
    else:
        data = dict(output_json)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=title or f"{agent_name} {subject_type} {subject_id}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleSmall", parent=styles["Title"],
        fontSize=16, leading=20, spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=colors.HexColor("#666666"),
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=11, leading=15, spaceAfter=8,
    )

    story: list[Any] = []

    # Header
    story.append(Paragraph(
        title or f"{agent_name} — {subject_type} #{subject_id}",
        title_style,
    ))
    updated_str = (
        updated_at.strftime("%Y-%m-%d %H:%M UTC")
        if updated_at else "—"
    )
    story.append(Paragraph(
        f"Agent: <b>{agent_name}</b> v{agent_version} · "
        f"Subject: {subject_type} #{subject_id} · "
        f"Güncellendi: {updated_str}",
        meta_style,
    ))
    story.append(Spacer(1, 8 * mm))

    # Summary (NL)
    if summary:
        story.append(Paragraph("<b>Özet</b>", body_style))
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 4 * mm))

    # output_json key-value tablo
    rows = _flatten_json(data)
    if rows:
        story.append(Paragraph("<b>Detay</b>", body_style))
        table_data = [["Alan", "Değer"]]
        for key, value in rows:
            # Çok uzun değer pdf'de satır taşar; reportlab Paragraph wrap yapar
            table_data.append([
                Paragraph(key, styles["BodyText"]),
                Paragraph(value, styles["BodyText"]),
            ])
        table = Table(
            table_data,
            colWidths=[55 * mm, 115 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f5f5f5")]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(table)

    doc.build(story)
    return buf.getvalue()


# Rating → renk (görsel hızlı tarama; elit yeşil → zayıf kırmızı).
_RATING_COLORS = {
    "elit": "#1b7837",
    "iyi": "#5aae61",
    "ortalama": "#b8860b",
    "zayıf": "#c1272d",
}


def build_performance_report_pdf(
    *,
    player_name: str,
    player_external_id: int,
    test_date: str | datetime | None = None,
    scores: list[dict[str, Any]],
    strong_areas: list[str] | tuple[str, ...] = (),
    weak_areas: list[str] | tuple[str, ...] = (),
    progression: list[dict[str, Any]] | None = None,
    summary: str = "",
    club_name: str | None = None,
) -> bytes:
    """Bir oyuncunun performans test bataryasından A4 PDF rapor üret.

    `scores`: evaluate_battery çıktısındaki TestScore'lar (asdict). Her biri
    `protocol_name, raw_value, unit, rating, squad_percentile` içerir.
    `progression`: interpret_progression çıktıları (asdict, ops) — trend +
    regresyon uyarısı. Saf builder: DB/HTTP bilmez, caller veri verir.
    """
    if not REPORTLAB_AVAILABLE:
        raise ReportlabNotInstalled(
            "reportlab kurulu değil — `pip install reportlab>=4.0`",
        )

    if isinstance(test_date, datetime):
        date_str = test_date.strftime("%Y-%m-%d")
    else:
        date_str = test_date or datetime.utcnow().strftime("%Y-%m-%d")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Performans Raporu — {player_name}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PerfTitle", parent=styles["Title"],
        fontSize=17, leading=21, spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "PerfMeta", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=colors.HexColor("#666666"),
    )
    body_style = ParagraphStyle(
        "PerfBody", parent=styles["Normal"],
        fontSize=11, leading=15, spaceAfter=6,
    )
    cell_style = styles["BodyText"]

    story: list[Any] = []

    # Header
    story.append(Paragraph(f"Performans Test Raporu — {player_name}", title_style))
    meta = (
        f"Oyuncu #{player_external_id} · Test tarihi: {date_str}"
    )
    if club_name:
        meta = f"{club_name} · " + meta
    story.append(Paragraph(meta, meta_style))
    story.append(Spacer(1, 6 * mm))

    if summary:
        story.append(Paragraph("<b>Özet</b>", body_style))
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 3 * mm))

    # Test skor tablosu (renk-kodlu rating)
    story.append(Paragraph("<b>Test Sonuçları</b>", body_style))
    table_data: list[list[Any]] = [["Test", "Değer", "Norm", "Kadro %"]]
    rating_rows: list[tuple[int, str]] = []  # (row_index, rating) renk için
    for i, s in enumerate(scores, start=1):
        rating = str(s.get("rating", "—"))
        pct = s.get("squad_percentile")
        table_data.append([
            Paragraph(str(s.get("protocol_name", s.get("protocol_key", "?"))),
                      cell_style),
            Paragraph(f"{s.get('raw_value', '—')} {s.get('unit', '')}".strip(),
                      cell_style),
            Paragraph(rating, cell_style),
            Paragraph("—" if pct is None else f"%{pct}", cell_style),
        ])
        rating_rows.append((i, rating))

    table = Table(
        table_data,
        colWidths=[78 * mm, 32 * mm, 34 * mm, 30 * mm],
        repeatRows=1,
    )
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]
    # Norm hücresini rating rengine boya.
    for row_idx, rating in rating_rows:
        hexc = _RATING_COLORS.get(rating)
        if hexc:
            table_style.append(
                ("TEXTCOLOR", (2, row_idx), (2, row_idx), colors.HexColor(hexc)),
            )
            table_style.append(
                ("FONTNAME", (2, row_idx), (2, row_idx), "Helvetica-Bold"),
            )
    table.setStyle(TableStyle(table_style))
    story.append(table)
    story.append(Spacer(1, 5 * mm))

    # Güçlü / zayıf alanlar
    if strong_areas:
        story.append(Paragraph(
            "<b>Güçlü yönler:</b> " + ", ".join(strong_areas), body_style))
    if weak_areas:
        story.append(Paragraph(
            "<b>Gelişim alanları:</b> " + ", ".join(weak_areas), body_style))
    if strong_areas or weak_areas:
        story.append(Spacer(1, 4 * mm))

    # Gelişim / regresyon uyarıları
    if progression:
        story.append(Paragraph("<b>Gelişim Eğilimi</b>", body_style))
        prog_data: list[list[Any]] = [["Test", "Eğilim", "Uyarı"]]
        for p in progression:
            alert = "⚠ ani düşüş" if p.get("regression_alert") else "—"
            prog_data.append([
                Paragraph(str(p.get("protocol_name", p.get("protocol_key", "?"))),
                          cell_style),
                Paragraph(str(p.get("trend", "—")), cell_style),
                Paragraph(alert, cell_style),
            ])
        ptable = Table(prog_data, colWidths=[78 * mm, 46 * mm, 50 * mm],
                       repeatRows=1)
        ptable.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(ptable)
        story.append(Spacer(1, 4 * mm))

    # KVKK dipnotu — bu rapor özel nitelikli kişisel veri içerir.
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Bu rapor KVKK kapsamında <b>özel nitelikli kişisel veri</b> "
        "(sağlık/performans) içerir. Yalnızca yetkili teknik/tıbbi ekip "
        "erişebilir; paylaşımı denetim kaydına tabidir.",
        meta_style,
    ))

    doc.build(story)
    return buf.getvalue()
