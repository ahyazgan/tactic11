"""Render validated analyst marks onto a real source frame, locally."""
from __future__ import annotations

import hashlib
import math
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from app.reports.review_document import Drawing, ReviewDocument
from app.reports.review_media import MediaError, ffmpeg

COLORS = {"yellow": "#ffdf32", "red": "#ff4b4b", "blue": "#37bfff"}


def source_frame(source: Path, time: float) -> bytes:
    command = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1",
               "-protocol_whitelist", "file,pipe", "-f", "mov", "-ss", str(time), "-i", str(source),
               "-map", "0:v:0", "-frames:v", "1", "-vf",
               "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
               "-threads", "1", "-f", "image2pipe", "-c:v", "png", "-"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        if result.returncode or not result.stdout:
            raise MediaError("Çizim karesi okunamadı. Video içinden başka bir zaman seçin.")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("Çizim karesi hazırlanamadı.") from exc


def draw_frame(frame: bytes, drawing: Drawing) -> bytes:
    image = Image.open(BytesIO(frame)).convert("RGB")
    pen = ImageDraw.Draw(image)
    width = max(2, round(image.width * .004))
    for mark in drawing.marks:
        x1, y1, x2, y2 = mark.x1 * image.width, mark.y1 * image.height, mark.x2 * image.width, mark.y2 * image.height
        color = COLORS[mark.color]
        if mark.kind == "box":
            points = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            pen.rectangle(points, outline="#182922", width=width + 3)
            pen.rectangle(points, outline=color, width=width)
        else:
            pen.line((x1, y1, x2, y2), fill="#182922", width=width + 3)
            pen.line((x1, y1, x2, y2), fill=color, width=width)
            angle = math.atan2(y2 - y1, x2 - x1)
            size = min(image.width * .022, math.hypot(x2 - x1, y2 - y1) * .45)
            pen.polygon([(x2, y2), (x2 - size * math.cos(angle - .5), y2 - size * math.sin(angle - .5)),
                         (x2 - size * math.cos(angle + .5), y2 - size * math.sin(angle + .5))], fill=color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def report_frames(source: Path, document: ReviewDocument, source_hash: str) -> dict[str, bytes]:
    if not any(f.drawing and f.drawing.marks for f in document.findings):
        return {}
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source_hash:
            raise MediaError("Kaynak video değişti. Çizimleri yeniden inceleyin.")
    return {str(f.id): draw_frame(source_frame(source, f.drawing.time), f.drawing)
            for f in document.findings if f.drawing and f.drawing.marks}
