"""Local, tenant-scoped footage and bounded FFmpeg operations."""
from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MediaError(RuntimeError):
    pass


def private_dir(tenant_id: str) -> Path:
    # Tenant IDs never become a user-controlled path component.
    root = Path(os.environ.get("REVIEW_DATA_DIR") or ROOT / "data" / "reviews")
    folder = root / hashlib.sha256(tenant_id.encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def asset_path(tenant_id: str, asset_id: str, suffix: str = ".mp4") -> Path:
    return private_dir(tenant_id) / (str(uuid.UUID(asset_id)) + suffix)


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError) as exc:
        raise MediaError("Video aracı hazır değil. imageio-ffmpeg kurulumu gerekli.") from exc


def probe_video(path: Path) -> float:
    """Accept only a decodable local MP4, with a finite, bounded duration."""
    command = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "info",
               "-protocol_whitelist", "file,pipe", "-f", "mov", "-threads", "1",
               "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        info = result.stderr.decode("utf-8", errors="replace")
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
        if result.returncode or not match or not re.search(r"frame=\s*[1-9]\d*", info):
            raise MediaError("Video okunamadı; geçerli bir MP4 dosyası yükleyin.")
        source_stream = next((line for line in info.splitlines() if "Video:" in line), "")
        if not re.search(r"Video:\s*h264\b", source_stream) or not re.search(r"\byuvj?420p\b", source_stream):
            raise MediaError("Tarayıcıda incelemek için H.264, 8 bit MP4 video yükleyin. Bu videonun kodlaması desteklenmiyor.")
        hours, minutes, seconds = (float(value) for value in match.groups())
        duration = hours * 3600 + minutes * 60 + seconds
        if not math.isfinite(duration) or not 0.5 <= duration <= 10800:
            raise MediaError("Video süresi 0,5 saniye ile 3 saat arasında olmalı.")
        return duration
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise MediaError("Video okunamadı; geçerli bir MP4 dosyası yükleyin.") from exc


def cut_clip(source: Path, destination: Path, start: float, end: float) -> None:
    """Re-encode for accurate boundaries and browser-compatible H.264 playback."""
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    command = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-protocol_whitelist", "file,pipe", "-f", "mov", "-ss", str(start),
               "-i", str(source), "-t", str(end - start), "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", "scale=w='trunc(min(1280,iw)/2)*2':h=-2", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac",
               "-movflags", "+faststart", "-shortest", str(temporary)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=180, check=False)
        if result.returncode or not temporary.exists() or temporary.stat().st_size == 0:
            raise MediaError("Klip üretilemedi. Kaynak videoyu ve seçilen aralığı kontrol edin.")
        actual_duration = probe_video(temporary)
        if abs(actual_duration - (end - start)) > 0.5:
            raise MediaError("Klip süresi seçilen aralıkla uyuşmuyor. Kaynak videonun bu bölümünü kontrol edin.")
        temporary.replace(destination)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("Klip üretimi tamamlanamadı; yeniden deneyin.") from exc
    finally:
        temporary.unlink(missing_ok=True)
