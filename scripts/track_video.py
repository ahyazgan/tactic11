"""Video → tracking frame JSON (venv-cv işçisi; torch + rfdetr + supervision + opencv).

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.track_video \\
        --video clip.mp4 --calibration calib.json --out frames.json \\
        --match-id 990001 --home-team 217 --away-team 213 \\
        --fps 5 --model medium --tiles 2 --preview preview.mp4

Sonra ana ortamda:
    venv\\Scripts\\python.exe -m scripts.ingest_tracking_json --json frames.json --tenant t-default

Kalibrasyon JSON şeması: app/tracking/calibration.py docstring.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.camera import (
    BROADCAST_SOURCE,
    STATIC_SOURCE,
    analyze_video,
    source_after_run,
)
from app.tracking.detect import DetectorConfig
from app.tracking.frames import frames_to_json
from app.tracking.passes import extract_passes
from app.tracking.pipeline import PipelineConfig, process_video, video_info


def main() -> int:
    p = argparse.ArgumentParser(description="Video → TrackingFrame JSON (RF-DETR + ByteTrack)")
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", default=None,
                   help="Saha kalibrasyon JSON'u. Verilmezse çapa GÖRÜNTÜDEN bulunur "
                        "(kare başına kalibrasyon açılır; TV kuralı: görüntünün altı "
                        "yakın taç çizgisi). Çapa bulunana kadar kare üretilmez.")
    p.add_argument("--out", required=True, help="Çıktı frames JSON")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--home-team", type=int, required=True)
    p.add_argument("--away-team", type=int, required=True)
    p.add_argument("--fps", type=float, default=5.0, help="Çıktı kare hızı (TrackingFrame/sn)")
    p.add_argument("--track-fps", type=float, default=15.0, help="Tespit+takip kare hızı (küçük/hızlı oyuncular için yüksek)")
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "base", "large"])
    p.add_argument("--threshold", type=float, default=0.35)
    p.add_argument("--ball-threshold", type=float, default=0.4, help="Top için ayrı güven eşiği")
    p.add_argument("--tiles", type=int, default=1, help="1=tam kare, 2=2×2 dilim (küçük oyuncular için)")
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--weights", default=None, help="İnce ayarlı ağırlık klasörü (meta.json + checkpoint_best_total.pth)")
    p.add_argument("--backend", default="auto", choices=["auto", "torch", "onnx"],
                   help="Dedektör arka ucu. auto=ONNX modeli varsa (ya da torch yüklenemiyorsa) ONNX, "
                        "yoksa torch. ONNX modeli: scripts/export_detector_onnx.py")
    p.add_argument("--onnx-model", default=None, help="ONNX model yolu (varsayılan: data/tracking/models/onnx/…)")
    p.add_argument("--clip-offset-minutes", type=float, default=0.0, help="Klibin maç dakikası başlangıcı")
    p.add_argument("--period", type=int, default=1)
    p.add_argument("--preview", default=None, help="Etiketli önizleme mp4 yolu")
    p.add_argument("--per-frame-calibration", default="auto",
                   choices=["auto", "on", "off"],
                   help="Hareketli kamerada homografiyi her karede yeniden bul. "
                        "auto=kamera sabit değilse aç. Oturmayan kareler ATLANIR.")
    p.add_argument("--reacquire", default="auto", choices=["auto", "on", "off"],
                   help="Kesmeden sonra ÇAPADAN yeniden yakala. auto=yayın "
                        "görüntüsünde aç. Kapalıyken ilk kesmede takip kopar ve "
                        "bir daha toparlanmaz (videonun kalanı atılır).")
    p.add_argument("--camera", default="auto", choices=["auto", "static", "broadcast"],
                   help="Kamera davranışı: auto=videodan tespit et (varsayılan), "
                        "static=sabit kamera (tam analiz), broadcast=hareketli/yayın "
                        "(top-merkezli, şekil ve bölge analizi kapalı)")
    args = p.parse_args()

    calib = PitchCalibration.load(args.calibration) if args.calibration else None
    info = video_info(args.video)
    print(f"video: {Path(args.video).name} {info['width']}x{info['height']} @{info['fps']:.2f}fps {info['frames']} kare")
    if calib is not None:
        print(f"kalibrasyon: {len(calib.points)} nokta · geri-izdüşüm hatası ~{calib.reprojection_error_m:.2f} m")
    else:
        print("kalibrasyon: ÇAPA YOK → görüntüden otomatik çapa (TV kuralı: görüntünün "
              "altı yakın taç y=68; karşı açıda konumlar aynalanır)")

    # Kamera sabit mi? Sabit homografi yalnız sabit kamerada geçerlidir; kamera
    # çeviriyorsa oyuncular sahada kaymış görünür ve sahte taktik sinyal çıkar
    # (100 px kayma ≈ 3.6 m, sinyal eşikleri 2.5-4 m). Bkz. app/tracking/camera.py
    if args.camera == "auto":
        verdict = analyze_video(args.video)
        print(f"kamera: {verdict.kind} · {verdict.note}")
        source_name = verdict.source_name
    else:
        source_name = STATIC_SOURCE if args.camera == "static" else BROADCAST_SOURCE
        print(f"kamera: {args.camera} (elle verildi) → kaynak {source_name}")

    # Kamera hareketliyse sabit homografi geçersiz; kare başına kalibrasyon
    # devreye girer ve oturmayan kareler atlanır. Kalibrasyon başarılıysa
    # konumlar tekrar güvenilir olduğu için kaynak etiketi de yükseltilir.
    moving = source_name == BROADCAST_SOURCE
    if args.per_frame_calibration == "on":
        per_frame = True
    elif args.per_frame_calibration == "off":
        per_frame = False
    else:
        per_frame = moving
    if calib is None and not per_frame:
        if args.per_frame_calibration == "off":
            print("HATA: kalibrasyon yok ve kare başına kalibrasyon kapalı — "
                  "--calibration ver ya da --per-frame-calibration on")
            return 2
        # Sabit kamerada da çapa görüntüden bulunur; bunun tek yolu kalibratör.
        per_frame = True
        print("kalibrasyon verilmedi → kare başına kalibrasyon otomatik açıldı")
    if per_frame:
        print("kare başına kalibrasyon: AÇIK — oturmayan kareler atlanacak")
        # Kalibrasyon kamerayı ancak ardışık örnekler yakınsa takip edebilir.
        # Ölçüldü: 30 fps kaynakta her 3. kareye kadar %100 kalibre, her 5.
        # karede takip kopuyor. track_fps düşükse hat kareyi seyrek örnekler
        # ve kalibrasyon hiç tutturamaz (5 fps'te 30 karenin 1'i kalibre oldu).
        if args.track_fps < 15.0:
            print(f"  UYARI: --track-fps {args.track_fps:g} kare başına kalibrasyon için "
                  f"düşük. Kamera kareler arasında çok yol alıyor; 15 önerilir.")
        if moving:
            # Her kare kendi homografisiyle geldiği için kareler artık
            # top-merkezli değil, gerçek saha konumu taşır.
            source_name = STATIC_SOURCE

    # Kesmeden sonra yeniden yakalama. Yayında ŞART: yayın sürekli kamera
    # değiştirir, kapalıyken kalibratör ilk kesmede KAYIP'a düşer ve bir daha
    # toparlanmaz — segmentin kalanındaki her kare atılır.
    if args.reacquire == "on":
        reacquire = True
    elif args.reacquire == "off":
        reacquire = False
    else:
        reacquire = moving
    if per_frame and reacquire:
        print("kesmeden sonra yeniden yakalama: AÇIK (çapadan, %85 inlier şartı)")

    cfg = PipelineConfig(
        per_frame_calibration=per_frame,
        allow_reacquire=per_frame and reacquire,
        detect_cuts=per_frame,
        detect_replays=per_frame and moving,
        source_name=source_name,
        fps_out=args.fps, track_fps=args.track_fps, max_seconds=args.max_seconds,
        detector=DetectorConfig(model=args.model, threshold=args.threshold, tiles=args.tiles, resolution=args.resolution, weights=args.weights,
                                backend=args.backend, onnx_model=args.onnx_model),
        clip_offset_minutes=args.clip_offset_minutes, period=args.period,
        preview_path=args.preview, ball_threshold=args.ball_threshold,
    )
    started = time.time()
    frames, summary = process_video(
        args.video, calib, match_id=args.match_id,
        home_team_id=args.home_team, away_team_id=args.away_team, cfg=cfg,
    )
    # Etiketi GERÇEKLEŞENE göre düzelt — canlı hatla (scripts/track_live.py)
    # aynı kural. İki yolun aynı görüntüde farklı etiket üretmesi, karelerin bir
    # sınıfta yazılıp başka bir sınıfta yorumlanmasına yol açar.
    mode = {"per_frame": per_frame, "source": source_name}
    stats = summary.get("calibration_stats") or {}
    source_name, downgrade = source_after_run(mode, stats.get("calibrated_ratio"))
    if downgrade:
        frames = [f.model_copy(update={"source": source_name}) for f in frames]
        summary["source_downgraded"] = downgrade
        print(f"  ! {downgrade}")

    payload = frames_to_json(frames, match_id=args.match_id, source_name=source_name, extra={
        # Takipten çıkarılan paslar JSON'a da girer: ingest bunları event
        # tablosuna yazabilsin ve xT/ileri pas motorları kulüp videosuyla
        # çalışabilsin. Özet yalnız sayıyı taşır, ayrıntı burada.
        "derived_passes": [asdict(p) for p in extract_passes(frames).passes],
        "video": Path(args.video).name, "video_info": info,
        "home_team_external_id": args.home_team, "away_team_external_id": args.away_team,
        "config": {"fps": args.fps, "track_fps": args.track_fps, "model": args.model, "tiles": args.tiles, "threshold": args.threshold, "weights": args.weights,
                   "backend": args.backend, "onnx_model": args.onnx_model},
        "summary": summary,
    })
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    print("\n=== Track Report ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  out: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
