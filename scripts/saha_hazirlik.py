"""Saha günü ön kontrolü: maça çıkmadan önce tek komutla "başlar mı?" cevabı (venv-cv).

Canlı hat (`scripts.canli_mac`) başlarken veritabanı ve kalibrasyon kapılarını
zaten uygular; ama kamera, disk ve GPU kontrolü yoktur ve sorun sahada, maç
başlarken görülür. Bu script aynı kapıları + kamera/disk/GPU'yu evden ya da
sahaya varınca çalıştırır ve her satır için GEÇTİ / UYARI / KALDI der.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.saha_hazirlik \\
        --camera "Insta360 X5" --hours 2 \\
        [--calibration data/tracking/calibrations/saha.json] \\
        [--database-url "sqlite:///<proje>/demo.db"]

Disk hesabı ölçümden: USB kamera akışı 2880x1440 @ 30 fps H.264 segmentte
~3,3 GB/saat (30 sn ≈ 23–29 MB, `docs/measurements/live-rehearsal-990771-usb-camera.json`);
takip çıktısı (kare JSON + top adayları + telestrasyon mp4) saatte ~1 GB. Üstüne
5 GB pay bırakılır. Çıkış kodu: 0 hepsi geçti, 1 uyarı var, 2 kalan var.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.canli_mac import (
    PROJECT_ROOT,
    check_calibration,
    check_database,
    find_ffmpeg,
    list_devices,
)

STREAM_GB_PER_HOUR = 3.3      # ölçülen: 2880x1440@30 H.264 segment
OUTPUT_GB_PER_HOUR = 1.0      # kare JSON + top adayları + telestrasyon mp4 (990741 koşusundan)
DISK_RESERVE_GB = 5.0
MIN_GPU_FREE_GB = 3.0         # v2 dedektör + izleyici 4K panoramada ~2,5 GB kullanıyor

OK, WARN, FAIL = "GEÇTİ", "UYARI", "KALDI"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def disk_verdict(free_gb: float, hours: float) -> Check:
    need = hours * (STREAM_GB_PER_HOUR + OUTPUT_GB_PER_HOUR) + DISK_RESERVE_GB
    detail = f"boş {free_gb:.1f} GB · gereken ≈ {need:.1f} GB ({hours:g} saat)"
    if free_gb >= need:
        return Check("disk", OK, detail)
    if free_gb >= need - DISK_RESERVE_GB:
        return Check("disk", WARN, detail + " · pay yok; eski segmentleri sil ya da --height 1080")
    return Check("disk", FAIL, detail + " · yetmez; data/tracking/live altındaki eski koşuları sil")


def parse_device_modes(ffmpeg_stderr: str) -> list[tuple[str, int, int, float]]:
    """ffmpeg `-list_options` çıktısından (codec, genişlik, yükseklik, fps) — tekrarsız."""
    modes: list[tuple[str, int, int, float]] = []
    for m in re.finditer(r"(?:vcodec|pixel_format)=(\w+)\s+min s=(\d+)x(\d+) fps=([\d.]+)", ffmpeg_stderr):
        item = (m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4)))
        if item not in modes:
            modes.append(item)
    return modes


def device_modes(ffmpeg: str, name: str) -> list[tuple[str, int, int, float]]:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-list_options", "true", "-f", "dshow", "-i", f"video={name}"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return parse_device_modes(proc.stderr)


def camera_verdict(name: str, listed: list[str], modes: list[tuple[str, int, int, float]]) -> Check:
    if name not in listed:
        return Check("kamera", FAIL, f"'{name}' bağlı değil · görülen: {', '.join(listed) or 'yok'}")
    if not modes:
        return Check("kamera", WARN, f"'{name}' bağlı, kip listesi alınamadı")
    best = max(modes, key=lambda m: m[1] * m[2])
    text = ", ".join(f"{w}x{h}@{fps:g}" for _c, w, h, fps in modes)
    status = OK if best[2] >= 1440 else WARN
    note = "" if status == OK else " · 1440p altı: uzak yarıda oyuncu < 30 px kalır"
    return Check("kamera", status, f"'{name}' · kipler: {text} · en yüksek {best[1]}x{best[2]}{note}")


def gpu_verdict() -> Check:
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return Check("gpu", FAIL, "torch yok (venv-cv ile çalıştırın)")
    if not torch.cuda.is_available():
        return Check("gpu", FAIL, "CUDA yok; dedektör CPU'da maça yetişmez")
    free, total = torch.cuda.mem_get_info()
    free_gb, total_gb = free / 1e9, total / 1e9
    detail = f"{torch.cuda.get_device_name(0)} · boş {free_gb:.1f} / {total_gb:.1f} GB"
    if free_gb < MIN_GPU_FREE_GB:
        return Check("gpu", FAIL, detail + " · başka bir takip/eğitim çalışıyor olabilir; kapatın")
    return Check("gpu", OK, detail)


def run_checks(args: argparse.Namespace) -> list[Check]:
    checks: list[Check] = []
    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
        checks.append(Check("ffmpeg", OK, ffmpeg))
    except SystemExit as exc:
        checks.append(Check("ffmpeg", FAIL, str(exc)))
        ffmpeg = None
    if ffmpeg and args.camera:
        listed = list_devices(ffmpeg)
        modes = device_modes(ffmpeg, args.camera) if args.camera in listed else []
        checks.append(camera_verdict(args.camera, listed, modes))
    free_gb = shutil.disk_usage(PROJECT_ROOT).free / 1e9
    checks.append(disk_verdict(free_gb, args.hours))
    checks.append(gpu_verdict())
    from scripts.track_live import default_ingest_python  # noqa: PLC0415

    db_error = check_database(default_ingest_python(), args.database_url)
    checks.append(Check("veritabanı", FAIL if db_error else OK, db_error or (args.database_url or "DATABASE_URL")))
    if args.calibration:
        path = Path(args.calibration)
        if not path.is_file():
            checks.append(Check("kalibrasyon", FAIL, f"dosya yok: {path}"))
        else:
            err = check_calibration(path)
            checks.append(Check("kalibrasyon", FAIL if err else OK, err or f"{path.name} doğrulanmış"))
    else:
        checks.append(Check("kalibrasyon", WARN, "verilmedi: telestrasyon ve saha konumları için şart; "
                                                  "yalnız kayıt alınacaksa sorun değil"))
    return checks


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--camera", default=None, help="dshow kamera adı (ör. \"Insta360 X5\"); boş: kamera kontrolü atlanır")
    p.add_argument("--hours", type=float, default=2.0, help="planlanan kayıt süresi (saat)")
    p.add_argument("--calibration", default=None)
    p.add_argument("--database-url", default=None)
    p.add_argument("--ffmpeg", default=None)
    args = p.parse_args()
    checks = run_checks(args)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"[{c.status:>5}] {c.name:<{width}}  {c.detail}")
    worst = max((c.status for c in checks), key=[OK, WARN, FAIL].index)
    print({OK: "hazır: canli_mac başlatılabilir", WARN: "başlar, uyarıları okuyun",
           FAIL: "başlamaz: KALDI satırlarını düzeltin"}[worst])
    return [OK, WARN, FAIL].index(worst)


if __name__ == "__main__":
    sys.exit(main())
