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
