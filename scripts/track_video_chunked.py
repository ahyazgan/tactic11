"""Uzun videoyu parçalara bölüp her parçayı ayrı ürün işçisi (`scripts.track_video_product`) süreciyle işler (venv-cv).

Neden: tek süreç 94 dakikalık maçta belleği bitirdi (ArrayMemoryError, ölçüm
docs/measurements/product-full-match-exam-result-attempt2.json). Parça başına ayrı süreç
belleği her parçada sıfırlar; çöken parça yalnız kendi dakikalarını kaybettirir.

Kısa klipte (tek parça) `track_video` aynen çalışır, çıktı değişmez. Bölme ffmpeg segment
muxer ile, yeniden kodlamadan; parça sınırları anahtar karededir ve gerçek başlangıçlar
segment listesinden okunur. Sınırlar: takip kimlikleri parça sınırında yeniden başlar
(çıktıda `cross_segment_person_identity: false`), kare başına kalibrasyon her parçada verilen
kalibrasyondan başlar, önizleme yalnız ilk parçadan üretilir, bölme sırasında video boyutu
kadar boş disk gerekir.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_CHUNK_SECONDS = 300.0
# Tek parça sayılacak üst sınır: bundan kısa video bölünmez (bölmenin kazancı yok).
SINGLE_CHUNK_FACTOR = 1.5
DISK_RESERVE_BYTES = 3 * 1024**3
# Kare başına en çok dilim (örtüşmeli ızgara). Ölçülen: 4096x1080'de 4 dilim (50) 8 GB GPU'da
# 3,4 GB ile çalışıyor (docs/CANLI-HIZ-VE-PROVA.md); 6 dilim (98) belleği taşırıp paylaşılan
# belleğe düşüyor ve 13 dakikada 8 saniyeden az video işliyor (2026-11-13, RTX 5060 8 GB).
# 1920x1080'de 6 dilim 49'dur, yani 16:9 kaynakta varsayılan değişmez.
MAX_TILE_WINDOWS = 50
SUMMED_CALIBRATION_STATS = ("frames_calibrated", "frames_rejected", "replays_dropped", "cuts",
                            "anchor_attempts", "anchors_found", "tracker_resets")

Runner = Callable[[list[str]], int]


def needs_chunking(duration_seconds: float, chunk_seconds: float) -> bool:
    return chunk_seconds > 0 and duration_seconds > chunk_seconds * SINGLE_CHUNK_FACTOR


def parse_segment_list(path: Path) -> list[tuple[str, float, float]]:
    """ffmpeg `-segment_list` CSV'si: (dosya, başlangıç sn, bitiş sn), kaynak zaman çizgisinde."""
    with open(path, encoding="utf-8", newline="") as f:
        return [(row[0], float(row[1]), float(row[2])) for row in csv.reader(f) if len(row) >= 3]


def segment_command(ffmpeg: str, video: str, out_dir: Path, chunk_seconds: float,
                    max_seconds: float | None = None) -> list[str]:
    limit = ["-t", f"{max_seconds:g}"] if max_seconds else []
    return [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-i", video, *limit, "-map", "0:v:0",
            "-c", "copy", "-f", "segment", "-segment_time", f"{chunk_seconds:g}", "-reset_timestamps", "1",
            "-segment_format", "mp4", "-segment_list", str(out_dir / "segments.csv"),
            "-segment_list_type", "csv", str(out_dir / "seg_%04d.mp4")]


def usable_team_anchor(summary: dict[str, Any] | None) -> list[list[float]] | None:
    """Önceki parçanın iki forma rengi; öğrenilemediyse (sıfır renk) çapa verilmez."""
    colors = (summary or {}).get("team_colors")
    if not isinstance(colors, list) or len(colors) != 2:
        return None
    if any(not isinstance(c, list) or len(c) != 3 or sum(c) <= 0 for c in colors):
        return None
    return colors


def snapped_offset_minutes(start_seconds: float) -> float:
    """Parça başlangıcı, tam milisaniyeye oturtulmuş dakika olarak.

    ffmpeg sınırları kare zamanıdır (59,94 fps'te 304.320667 sn gibi); kimlik ad alanı ise
    milisaniye altı başlangıcı reddeder (`identity_namespace.segment_namespace`). Yuvarlama
    kare zamanını en çok 0,5 ms kaydırır; ayrı parçalar yine ayrı ad alanı alır.
    """
    return round(start_seconds * 1000.0) / 60_000.0


def chunk_args(base: list[str], *, video: str, out: str, offset_minutes: float,
               anchor: list[list[float]] | None, preview: str | None, max_seconds: float | None) -> list[str]:
    cmd = [*base, "--video", video, "--out", out, "--clip-offset-minutes", repr(offset_minutes)]
    if anchor is not None:
        cmd += ["--team-anchor-json", json.dumps(anchor)]
    if preview:
        cmd += ["--preview", preview]
    if max_seconds is not None:
        cmd += ["--max-seconds", repr(max_seconds)]
    return cmd


def merge_payloads(payloads: list[dict[str, Any]], chunks: list[dict[str, Any]], video: str) -> dict[str, Any]:
    """Parça çıktıları tek çıktıya: kareler zaman sırasıyla, sayaçlar toplanır, parça karnesi eklenir."""
    if not payloads:
        raise ValueError("hiçbir parça çıktı üretmedi")
    merged = dict(payloads[0])
    merged["video"] = video
    merged["frames"] = [fr for p in payloads for fr in p.get("frames", [])]
    stats: dict[str, Any] = {}
    for key in SUMMED_CALIBRATION_STATS:
        values = [(p.get("summary") or {}).get("calibration_stats", {}).get(key) for p in payloads]
        if any(v is not None for v in values):
            stats[key] = sum(v or 0 for v in values)
    seen = stats.get("frames_calibrated", 0) + stats.get("frames_rejected", 0)
    if seen:
        stats["calibrated_ratio"] = round(stats.get("frames_calibrated", 0) / seen, 4)
    last = payloads[-1].get("summary") or {}
    merged["summary"] = {
        "frames_written": len(merged["frames"]),
        "tracks": sum((p.get("summary") or {}).get("tracks") or 0 for p in payloads),
        "team_colors": last.get("team_colors"),
        "calibration_stats": stats,
        "chunked": True,
        "chunks": chunks,
        "chunks_failed": sum(1 for c in chunks if c["state"] != "done"),
        "identity_scope": {"cross_segment_person_identity": False},
    }
    return merged


def nominal_tile_windows(tiles: int, width: int, height: int) -> int:
    """Dedektörün kare başına işleyeceği dilim sayısı (örtüşmeli ızgara, yaklaşık)."""
    from app.tracking.detect import DetectorConfig

    cols, rows = DetectorConfig(tiles=tiles).tile_grid(width, height)
    return (cols + 1) * (rows + 1)


def cap_tiles(passthrough: list[str], width: int, height: int) -> tuple[list[str], int | None, int | None]:
    """İstenen dilim sayısı bu görüntüde GPU belleğini taşırıyorsa ölçülmüş sınıra indirir.

    Dilim sayısı satır sayısıdır; sütun sayısı en-boy oranından gelir, yani panoramada aynı
    `--tiles` çok daha fazla dilim demektir (1920x1080'de 6 → 49, 4096x1080'de 6 → 98).
    Döner: (işçiye gidecek argümanlar, istenen, kullanılan); `--tiles` yoksa (…, None, None).
    """
    if "--tiles" not in passthrough:
        return passthrough, None, None
    at = passthrough.index("--tiles") + 1
    requested = used = int(passthrough[at])
    while used > 1 and nominal_tile_windows(used, width, height) > MAX_TILE_WINDOWS:
        used -= 1
    return [*passthrough[:at], str(used), *passthrough[at + 1:]], requested, used


def process_chunks(segments: list[tuple[str, float, float]], seg_dir: Path, base: list[str], *, out: str,
                   preview: str | None, max_seconds: float | None, video: str,
                   run: Runner, extra_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parçaları sırayla işler; işlenen parça dosyası hemen silinir. Çöken parça kaydedilir, atlanır."""
    payloads: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    anchor: list[list[float]] | None = None
    for index, (name, start, end) in enumerate(segments):
        seg_path = seg_dir / name
        if max_seconds is not None and start >= max_seconds:
            seg_path.unlink(missing_ok=True)
            continue
        part_out = seg_dir / f"part_{index:04d}.json"
        limit = max_seconds - start if max_seconds is not None and end > max_seconds else None
        rc = run(chunk_args(base, video=str(seg_path), out=str(part_out), offset_minutes=snapped_offset_minutes(start),
                            anchor=anchor, preview=preview if index == 0 else None, max_seconds=limit))
        record: dict[str, Any] = {"index": index, "start_seconds": round(start, 3), "end_seconds": round(end, 3)}
        if rc == 0 and part_out.exists():
            with open(part_out, encoding="utf-8") as f:
                payload = json.load(f)
            payloads.append(payload)
            anchor = usable_team_anchor(payload.get("summary")) or anchor
            record.update(state="done", frames=len(payload.get("frames", [])))
        else:
            record.update(state="failed", exit_code=rc)
        chunks.append(record)
        print(f"parça {index + 1}/{len(segments)}: {record['state']} "
              f"({record.get('frames', 0)} kare, {start / 60:.1f}-{end / 60:.1f}. dk)", flush=True)
        seg_path.unlink(missing_ok=True)
        part_out.unlink(missing_ok=True)
    merged = merge_payloads(payloads, chunks, video)
    merged["summary"].update(extra_summary or {})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)
    return merged["summary"]


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, check=False).returncode  # noqa: S603 — komut bu betiğin kurduğu sabit liste


def _split_known(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    p = argparse.ArgumentParser(description=__doc__, add_help=False)
    p.add_argument("--video", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--chunk-seconds", type=float, default=DEFAULT_CHUNK_SECONDS)
    p.add_argument("--clip-offset-minutes", type=float, default=0.0)
    p.add_argument("--preview", default=None)
    p.add_argument("--max-seconds", type=float, default=None)
    return p.parse_known_args(argv)


def main(argv: list[str] | None = None) -> int:
    own, passthrough = _split_known(list(sys.argv[1:] if argv is None else argv))
    worker = [sys.executable, "-m", "scripts.track_video_product"]
    from app.tracking.pipeline import video_info

    info = video_info(own.video)
    duration = info["frames"] / info["fps"] if info["fps"] else 0.0
    effective = min(duration, own.max_seconds) if own.max_seconds else duration
    passthrough, tiles_requested, tiles_used = cap_tiles(passthrough, info["width"], info["height"])
    tiles_note: dict[str, Any] = {}
    if tiles_used != tiles_requested:
        tiles_note = {"tiles_requested": tiles_requested, "tiles_used": tiles_used}
        print(f"dilim sayısı {tiles_requested} → {tiles_used}: {info['width']}x{info['height']} görüntüde "
              f"{tiles_requested} dilim GPU belleğini taşırır (sınır kare başına {MAX_TILE_WINDOWS} dilim)", flush=True)
    if own.clip_offset_minutes or not needs_chunking(effective, own.chunk_seconds):
        # Kısa klip ya da zaten bir parçanın kendisi: tek süreç, eski davranış.
        return _run(chunk_args([*worker, *passthrough], video=own.video, out=own.out,
                               offset_minutes=own.clip_offset_minutes, anchor=None,
                               preview=own.preview, max_seconds=own.max_seconds))

    from scripts.canli_mac import find_ffmpeg

    seg_dir = Path(own.out).with_suffix("").with_name(Path(own.out).stem + "_chunks")
    need = Path(own.video).stat().st_size + DISK_RESERVE_BYTES
    seg_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(seg_dir).free
    if free < need:
        print(f"boş disk yetersiz: bölme için {need / 1e9:.1f} GB gerekli, {free / 1e9:.1f} GB var", flush=True)
        return 3
    try:
        print(f"video {duration / 60:.1f} dk: {own.chunk_seconds:g} sn'lik parçalara bölünüyor", flush=True)
        if _run(segment_command(find_ffmpeg(), own.video, seg_dir, own.chunk_seconds, own.max_seconds)) != 0:
            print("ffmpeg videoyu bölemedi", flush=True)
            return 4
        segments = parse_segment_list(seg_dir / "segments.csv")
        summary = process_chunks(segments, seg_dir, [*worker, *passthrough], out=own.out, preview=own.preview,
                                 max_seconds=own.max_seconds, video=own.video, run=_run,
                                 extra_summary=tiles_note)
    except ValueError as e:
        print(f"parçalı işleme başarısız: {e}", flush=True)
        return 1
    finally:
        shutil.rmtree(seg_dir, ignore_errors=True)
    print(f"parçalı işleme bitti: {summary['frames_written']} kare, "
          f"{summary['chunks_failed']}/{len(summary['chunks'])} parça başarısız", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
