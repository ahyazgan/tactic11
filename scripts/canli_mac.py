"""Canlı maç modu: kaynak ver (dosya / RTSP / HTTP akışı), gerisi otomatik (venv-cv).

## Neden bu script var

Parçalar vardı ama tek komut yoktu: kamera segment yazar (ffmpeg, README'de
örnek), `track_live` klasörü izler, panel kareleri okur. Kullanıcı üç şey
istiyor: kendi kamerası, stadyum kamerası (RTSP), canlı yayın. Üçü de aynı
hatta iner; fark yalnız girişte. Bu script girişi tek komuta indirir ve
GECİKMEYİ ÖLÇÜP GÖSTERİR — gizlemez.

    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source mac.mp4 \\
        --match-id 990201 --home-team 611 --away-team 612 [--calibration saha.json]
    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source rtsp://kamera/stream ...
    venv-cv\\Scripts\\python.exe -m scripts.canli_mac --source https://.../index.m3u8 ...

## Dosya kaynağı = canlı prova

Dosya verildiğinde ffmpeg `-re` ile GERÇEK HIZDA okur: 90 dakikalık maç 90
dakikada akar, segmentler maç saatinde düşer. Böylece "sistem canlı maça
yetişiyor mu, kaç dakika geriden geliyor" dürüstçe ölçülür; kamera almadan
önce cevap bu ölçümden gelir. `--no-realtime` ile dosya olabildiğince hızlı
işlenir (maç sonrası analiz).

## Gecikme nasıl ölçülür

Her turda iki saat karşılaştırılır: akışın maç saati (dosyada: geçen duvar
saati; akışta: yazılan segment sayısı) ve panelin gördüğü son kare (işlenen
segment sayısı). Fark = koçun gördüğü resmin kaç saniye eski olduğu. Ekrana
`[canlı] işlenen dk 63.0 · akış dk 66.5 · gecikme 210 sn` yazılır.

## Sınırlar (dürüst)

- Gecikme ilk kurulumda dakikalar mertebesindedir (geniş açıda dilimli tespit
  gerçek zamanın ~4 katı yavaş — README "Canlı takip performansı"). Devre arası
  ve 60-80. dk kararları için yeterli, 89. dk için değil.
- Sabit kamera için kalibrasyon JSON'u gerekir (`scripts.propose_calibration`);
  verilmezse çapa görüntüden aranır (TV kuralı) — sabit kamerada yanlış olabilir.
- Skor ve dakika videodan okunmaz; dakika segment sırasından türetilir
  (`--start-minute`), skor panelde şut olaylarından gelir.

## Canlı kalma (`--keep-up`)

Takip segmenti gerçek zamandan yavaş işliyorsa (ölçüldü: 1080p panorama, 4 dilim,
RTX 5060'ta 30 sn'lik segment ~96 sn) gecikme her segmentte ~66 sn büyür; 6 dk
sonra koç 14 dk eski resmi görür. `--keep-up` ile ffmpeg segmentleri
`<watch>/incoming/` klasörüne yazar; takip boştayken yalnız EN YENİ kapanmış
segment izlenen klasöre alınır, aradakiler atlanır. Gecikme sınırlı kalır
(≈ bir segmentin işlenme süresi + segment süresi) ama maçın bir kısmı görülmez;
atlanan segmentler `incoming/` içinde kalır ve maç sonu tam işlenebilir. Alınan
segment adı dakikasını taşır (`seg_0007_m13.500.mp4`) ve takip dakikayı addan
okur (`--minute-from-name`), çünkü sıra numarası artık işlenen segment sayısına
eşit değildir.

## Panelde gecikme (`<watch>/status.json`)

Her turda ölçülen gecikme `status.json` olarak da yazılır (akış ve işlenen dakika,
gecikme, atlanan segment, kaynak bitti mi, yazılma zamanı). API bunu canlı
telestrasyon yanıtına ekler; panel kartı koçun gördüğü resmin kaç saniye eski
olduğunu gösterir.

## Kalibrasyon ön kontrolü (`--telestration`)

Telestrasyonun çizgi/etiket kapısı bağımsız doğrulanmamış ya da 2,0 m'den hatalı
kalibrasyonla hiç çizmez; operatör bunu ancak maç başladıktan sonra "neden çizgi
yok" diye fark ederdi. Başlamadan önce aynı kapı çalıştırılır; geçmiyorsa akış
başlamaz ve ne yapılacağı yazılır (`--allow-unverified-calibration` yalnız halka
isteyen operatör için).

## Veritabanı ön kontrolü

Kareler ana ortamın ingest süreciyle veritabanına yazılır; yazılamayan segment
"işlendi" sayılmaz ve gecikme göstergesi ilerlemez. Başlamadan önce aynı
yorumlayıcı ve aynı `DATABASE_URL` ile bağlantı denenir; ulaşılamazsa akış hiç
başlamaz ve ne yapılacağı yazılır (ölçüldü: `.env`'deki şablon adresle 12
segmentin hepsi sessizce reddedilmişti). Yerel kurulum için
`--database-url sqlite:///<proje>/demo.db`.

## Küçültülmüş segment ve kalibrasyon (`--height`)

Piksel kalibrasyonu çekildiği çözünürlüğe bağlıdır; takip hattı boyut farkında
kareyi reddeder. `--height` ile `--calibration` birlikte verilirse ilk segment
bitince gerçek boyutu okunur, kalibrasyon o boyuta ölçeklenip
`<watch>/calibration_<g>x<y>.json` olarak yazılır ve takip ile telestrasyona bu
dosya verilir. Saha konumları ve çizgi doğrulaması değişmez (yalnız piksel ölçeği).

## Telestrasyon (`--telestration`)

`scripts.telestrate_live` işçisi takiple birlikte başlar: işlenen her segment
için `<watch>/tele/seg_XXXX.mp4` (halka, blok çizgileri, faz etiketi) ve
`latest.json` yazar. Sabit kamera kalibrasyonu (`--calibration`, saha çizgisi
noktalı) ve hücum yönü (`--home-attack`) gerekir; kaynak bitince işçinin kalan
segmentleri bitirmesi beklenir.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEGMENT_SECONDS = 30.0
# Sabit kamerada (panorama) üretim dedektörü; kanıt docs/DEDEKTOR-INCE-AYAR-SONUCLARI.md
STATIC_DEFAULT_WEIGHTS = PROJECT_ROOT / "data" / "tracking" / "models" / "rfdetr_soccertrack_ft_v2"
POLL_SECONDS = 5.0
STREAM_SCHEMES = ("rtsp://", "rtsps://", "rtmp://", "http://", "https://", "udp://", "srt://")


@dataclass(frozen=True)
class SourceKind:
    is_stream: bool
    realtime: bool          # dosyayı gerçek hızda oku (-re)
    label: str


def classify_source(source: str, *, realtime_file: bool) -> SourceKind:
    low = source.lower()
    if low.startswith(STREAM_SCHEMES):
        return SourceKind(is_stream=True, realtime=False, label="akış")
    return SourceKind(is_stream=False, realtime=realtime_file,
                      label="dosya (canlı prova)" if realtime_file else "dosya (hızlı)")


def find_ffmpeg(explicit: str | None = None) -> str:
    """ffmpeg yolu: verilen → PATH → imageio-ffmpeg statik ikilisi. Yoksa hata."""
    if explicit:
        return explicit
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg  # noqa: PLC0415 — isteğe bağlı bağımlılık
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise SystemExit(
            "ffmpeg bulunamadı. Kur: `winget install Gyan.FFmpeg` ya da "
            "`venv-cv\\Scripts\\pip install imageio-ffmpeg`"
        ) from e


def ffmpeg_segment_command(
    ffmpeg: str, source: str, kind: SourceKind, watch: Path, *,
    segment_seconds: float, start_seconds: float = 0.0, transcode: bool = False,
    height: int | None = None,
) -> list[str]:
    """Kaynağı `watch/seg_%04d.mp4` segmentlerine böl.

    `-c copy` (H.264 kaynak) kayıpsız ve ucuzdur; VP9/webm ya da çözünürlük
    düşürme istenirse yeniden kodlanır (`transcode`, `height`). Segmentler
    anahtar kareye hizalanır; `-reset_timestamps 1` her segmenti 0'dan başlatır
    ki takip kare zamanlarını segment içi saysın.
    """
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin"]
    if kind.is_stream and source.lower().startswith(("rtsp://", "rtsps://")):
        cmd += ["-rtsp_transport", "tcp"]
    if kind.realtime:
        cmd += ["-re"]
    if start_seconds > 0:
        cmd += ["-ss", f"{start_seconds:.3f}"]
    cmd += ["-i", source, "-an"]
    if transcode or height:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-g", str(int(segment_seconds * 2)), "-pix_fmt", "yuv420p"]
        if height:
            cmd += ["-vf", f"scale=-2:{int(height)}"]
        cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{segment_seconds:g})"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-f", "segment", "-segment_time", f"{segment_seconds:g}",
            "-reset_timestamps", "1", "-segment_format", "mp4",
            str(watch / "seg_%04d.mp4")]
    return cmd


def source_needs_transcode(source: str) -> bool:
    """H.264 değilse (VP9/AV1/HEVC…) mp4 segment için yeniden kodla."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return False
    cap = cv2.VideoCapture(source)
    try:
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
    finally:
        cap.release()
    fourcc = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00").lower()
    return fourcc not in {"avc1", "h264", "x264"}


@dataclass(frozen=True)
class Latency:
    processed_minute: float
    stream_minute: float
    lag_seconds: float


def latency(processed_segments: int, written_segments: int, *, segment_seconds: float,
            start_minute: float, elapsed_seconds: float | None,
            source_ended: bool = False) -> Latency:
    """Gecikme = akışın maç saati − panelin gördüğü son kare.

    Akış saati: dosya provasında geçen duvar saati (gerçek hız); akışta yazılan
    segment sayısı (duvar saati bilinmez, kamera ne yazdıysa o). Kaynak bittiyse
    akış saati yazılan son segmentte durur — duvar saati akmaya devam etse de
    maç akmıyor (ölçüldü: prova sonunda "akış dk 23.8" gibi sahte büyüme).
    """
    processed = start_minute + processed_segments * segment_seconds / 60.0
    written = start_minute + written_segments * segment_seconds / 60.0
    if elapsed_seconds is not None and not source_ended:
        stream = start_minute + elapsed_seconds / 60.0
    else:
        stream = written
    return Latency(
        processed_minute=round(processed, 2), stream_minute=round(stream, 2),
        lag_seconds=round(max(0.0, (stream - processed) * 60.0), 1),
    )


def _processed_count(watch: Path) -> int:
    state = watch / ".track_live_state.json"
    if not state.is_file():
        return 0
    try:
        return len(json.loads(state.read_text(encoding="utf-8")).get("processed", []))
    except (ValueError, OSError):
        return 0


def _written_count(watch: Path) -> int:
    return len(list(watch.glob("seg_*.mp4")))


# --keep-up: alınan segment adı dakikayı taşır; track_live `--minute-from-name` ile okur
KEEP_UP_MINUTE_PATTERN = r"_m(\d+\.\d+)"


def keep_up_name(index: int, *, start_minute: float, segment_seconds: float) -> str:
    """`incoming/seg_0007.mp4` → `seg_0007_m13.500.mp4` (segmentin başladığı maç dakikası)."""
    return f"seg_{index:04d}_m{start_minute + index * segment_seconds / 60.0:.3f}.mp4"


def segment_index(name: str) -> int:
    """`seg_0007.mp4` / `seg_0007_m13.500.mp4` → 7."""
    return int(name[4:8])


def keep_up_choice(closed: list[str], promoted: list[str], processed: set[str]) -> str | None:
    """Takip boştaysa alınacak segment: kapanmış olanların en yenisi, son alınandan yeniyse.

    `closed` ffmpeg'in bitirdiği `incoming` adları; `promoted` izlenen klasöre alınmış
    adlar; `processed` takibin bitirdikleri. Takip hâlâ bir segmentle meşgulse None.
    """
    if any(name not in processed for name in promoted):
        return None
    last = max((segment_index(n) for n in promoted), default=-1)
    newer = [n for n in closed if segment_index(n) > last]
    return max(newer, key=segment_index) if newer else None


def closed_segments(incoming: Path, source_ended: bool) -> list[str]:
    """ffmpeg'in kapattığı segmentler: yazılan son dosya, kaynak bitmedikçe hâlâ açıktır."""
    names = sorted(p.name for p in incoming.glob("seg_*.mp4"))
    return names if source_ended else names[:-1]


def _processed_names(watch: Path) -> set[str]:
    state = watch / ".track_live_state.json"
    if not state.is_file():
        return set()
    try:
        return set(json.loads(state.read_text(encoding="utf-8")).get("processed", []))
    except (ValueError, OSError):
        return set()


# hata sınıfı + ilk satır: SQLAlchemy'nin "Background on this error" kuyruğu bilgi taşımaz
DB_CHECK = (
    "import sys\n"
    "from sqlalchemy import text\n"
    "from app.db.session import engine\n"
    "try:\n"
    "    with engine.connect() as c:\n"
    "        c.execute(text('select 1'))\n"
    "except Exception as exc:\n"
    "    print(type(exc).__name__ + ': ' + (str(exc).splitlines() or [''])[0], file=sys.stderr)\n"
    "    sys.exit(1)\n"
)


def check_calibration(calibration: Path) -> str | None:
    """Telestrasyon kapısının başlangıçta uygulanması: sorun varsa operatöre tek cümle, yoksa None."""
    from app.tracking.calibration import PitchCalibration  # noqa: PLC0415 — numpy yalnız bu yolda
    from app.tracking.telestration import (  # noqa: PLC0415
        MAX_REPROJECTION_M,
        calibration_validation,
    )

    try:
        calib = PitchCalibration.load(calibration)
    except (OSError, ValueError, KeyError) as exc:
        return f"kalibrasyon okunamadı: {exc}"
    source, error = calibration_validation(calib)
    if source == "unverified":
        return ("kalibrasyon bağımsız doğrulanmamış (noktalar saha işareti değil ya da çizgi doğrulaması yok); "
                "telestrasyon çizgi/etiket çizmez. Saha işaretleriyle (≥5 nokta) yeniden kalibre edin.")
    if error is None or error > MAX_REPROJECTION_M:
        return (f"kalibrasyon doğrulama hatası {error if error is None else round(error, 2)} m > {MAX_REPROJECTION_M} m; "
                "telestrasyon çizgi/etiket çizmez. Noktaları kontrol edip yeniden kalibre edin.")
    return None


def check_database(ingest_python: str, database_url: str | None, timeout_s: float = 30.0) -> str | None:
    """Ingest ortamında veritabanı bağlantısını dene → None (tamam) ya da hata metninin son satırı."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if database_url:
        env["DATABASE_URL"] = database_url
    try:
        proc = subprocess.run([ingest_python, "-c", DB_CHECK], cwd=str(PROJECT_ROOT), env=env,  # noqa: S603
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return f"{timeout_s:g} sn içinde yanıt yok"
    except OSError as exc:
        return f"yorumlayıcı başlatılamadı: {exc}"
    if proc.returncode == 0:
        return None
    lines = [ln for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip()]
    return lines[-1] if lines else f"çıkış kodu {proc.returncode}"


def write_status(watch: Path, lat: Latency, *, skipped: int, keep_up: bool, source_ended: bool) -> None:
    """Paneldeki gecikme göstergesi için durum; okuyucu yarım dosya görmesin diye geçici dosya + yer değiştirme."""
    payload = {"updated": datetime.now(UTC).isoformat(timespec="seconds"),
               "stream_minute": lat.stream_minute, "processed_minute": lat.processed_minute,
               "lag_seconds": lat.lag_seconds, "skipped_segments": skipped, "keep_up": keep_up,
               "source_ended": source_ended}
    tmp = watch / "status.json.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, watch / "status.json")


def scale_calibration(calibration: Path, size: tuple[int, int], out_dir: Path) -> Path:
    """Kalibrasyonu yeni görüntü boyutuna ölçekle (saha noktaları aynı); boyut aynıysa olduğu gibi."""
    data = json.loads(calibration.read_text(encoding="utf-8"))
    w0, h0 = (int(v) for v in data["image_size"])
    if (w0, h0) == size:
        return calibration
    sx, sy = size[0] / w0, size[1] / h0
    scaled = {**data, "image_size": [size[0], size[1]],
              "points": [{**pt, "image": [pt["image"][0] * sx, pt["image"][1] * sy]} for pt in data["points"]],
              "meta": {**(data.get("meta") or {}), "scaled_from": [w0, h0], "scaled_source": str(calibration)}}
    out = out_dir / f"calibration_{size[0]}x{size[1]}.json"
    out.write_text(json.dumps(scaled, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def resolve_weights(weights: str | None, camera: str, default: Path = STATIC_DEFAULT_WEIGHTS) -> str | None:
    """`--weights` verilmediyse sabit kamerada v2 (klasör varsa); diğer kameralarda COCO.

    v2 yalnız sabit panoramada ölçüldü; yayın/operatörlü kamerada eski davranış kalır.
    """
    if weights:
        return weights
    if camera == "static" and (default / "meta.json").exists():
        return str(default)
    return None


def wait_first_segment_size(seg_dir: Path, seg_proc: subprocess.Popen, timeout_s: float = 180.0) -> tuple[int, int]:
    """İlk segment tamamlanınca (ikincisi başlayınca ya da kaynak bitince) boyutunu oku."""
    import cv2  # noqa: PLC0415 — yalnız --height ile gerekir (venv-cv)

    first, second = seg_dir / "seg_0000.mp4", seg_dir / "seg_0001.mp4"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if first.exists() and (second.exists() or seg_proc.poll() is not None):
            cap = cv2.VideoCapture(str(first))
            size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            cap.release()
            if size[0] > 0 and size[1] > 0:
                return size
        time.sleep(1.0)
    raise SystemExit("ilk segment zamanında oluşmadı; kalibrasyon ölçeklenemedi")


def _telestration_backlog(watch: Path) -> int:
    """Takibi bitmiş ama telestrasyonu (çıktı ya da hata kaydı) henüz yazılmamış segment sayısı."""
    tele = watch / "tele"
    return sum(1 for f in (watch / "frames").glob("seg_*.json")
               if not (tele / f"{f.stem}.mp4").exists() and not (tele / f"{f.stem}.error.json").exists())


def main() -> int:
    p = argparse.ArgumentParser(description="Canlı maç modu: kaynak → segment → takip → panel")
    p.add_argument("--source", required=True, help="video dosyası | rtsp://... | http(s)://... (HLS)")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--home-team", type=int, required=True)
    p.add_argument("--away-team", type=int, required=True)
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--watch", default=None, help="segment klasörü (varsayılan data/tracking/live/<match-id>)")
    p.add_argument("--calibration", default=None, help="sabit kamera için saha kalibrasyon JSON'u")
    p.add_argument("--segment-seconds", type=float, default=DEFAULT_SEGMENT_SECONDS)
    p.add_argument("--start-minute", type=float, default=0.0, help="akışın başladığı maç dakikası")
    p.add_argument("--start-seconds", type=float, default=0.0, help="dosyada bu saniyeden başla")
    p.add_argument("--no-realtime", action="store_true", help="dosyayı gerçek hızda değil, olabildiğince hızlı oku")
    p.add_argument("--height", type=int, default=None, help="segmentleri bu yüksekliğe indir (ör. 1080)")
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--camera", default="auto", choices=["auto", "static", "broadcast", "operated"],
                   help="static=sabit, broadcast=TV, operated=operatörlü tek kamera (pan/zoom, kesme yok)")
    p.add_argument("--tiles", type=int, default=4)
    p.add_argument("--track-fps", type=float, default=15.0)
    p.add_argument("--weights", default=None)
    p.add_argument("--backend", default="auto", choices=["auto", "torch", "onnx"])
    p.add_argument("--onnx-model", default=None)
    p.add_argument("--database-url", default=None)
    p.add_argument("--fresh", action="store_true", help="klasördeki eski segment ve durumu sil")
    p.add_argument("--keep-up", action="store_true",
                   help="takip yetişemezse aradaki segmentleri atla, hep en yenisini işle (gecikme sınırlı)")
    p.add_argument("--telestration", action="store_true",
                   help="işlenen her segment için telestrasyonlu video üret (scripts.telestrate_live)")
    p.add_argument("--swap-at-minute", type=float, default=None,
                   help="telestrasyon: bu dakikadan sonra hücum yönünü ters çevir (ikinci yarı, ör. 45)")
    p.add_argument("--home-attack", default="auto", choices=["auto", "x+", "x-"],
                   help="telestrasyon: ev sahibi kalibrasyonun saha x'i artan/azalan yöne hücum eder")
    p.add_argument("--allow-unverified-calibration", action="store_true",
                   help="telestrasyon kapısını geçmeyen kalibrasyonla yine başla (yalnız halkalar çizilir)")
    args = p.parse_args()
    if args.telestration and not args.calibration:
        p.error("--telestration sabit kamera kalibrasyonu ister (--calibration)")
    if args.telestration:
        calib_error = check_calibration(Path(args.calibration))
        if calib_error is not None and not args.allow_unverified_calibration:
            print(f"[canlı] {calib_error}")
            print("[canlı] yine de başlamak için --allow-unverified-calibration.")
            return 2
        if calib_error is not None:
            print(f"[canlı] uyarı: {calib_error}")

    kind = classify_source(args.source, realtime_file=not args.no_realtime)
    if not kind.is_stream and not Path(args.source).is_file():
        print(f"kaynak yok: {args.source}")
        return 2
    watch = Path(args.watch) if args.watch else PROJECT_ROOT / "data" / "tracking" / "live" / str(args.match_id)
    if args.fresh and watch.exists():
        shutil.rmtree(watch)
    watch.mkdir(parents=True, exist_ok=True)
    seg_dir = watch / "incoming" if args.keep_up else watch
    seg_dir.mkdir(exist_ok=True)

    # track_live ile aynı ingest yorumlayıcısı
    from scripts.track_live import default_ingest_python  # noqa: PLC0415

    db_error = check_database(default_ingest_python(), args.database_url)
    if db_error is not None:
        print(f"[canlı] veritabanına ulaşılamıyor: {db_error}")
        print("[canlı] kareler yazılamaz; --database-url verin (yerel: sqlite:///<proje>/demo.db) "
              "ya da DATABASE_URL'i düzeltin.")
        return 2

    ffmpeg = find_ffmpeg(args.ffmpeg)
    transcode = (not kind.is_stream) and source_needs_transcode(args.source)
    seg_cmd = ffmpeg_segment_command(
        ffmpeg, args.source, kind, seg_dir, segment_seconds=args.segment_seconds,
        start_seconds=args.start_seconds, transcode=transcode, height=args.height,
    )
    track_cmd = [
        sys.executable, "-m", "scripts.track_live_candidates" if args.telestration else "scripts.track_live",
        "--watch", str(watch), "--match-id", str(args.match_id),
        "--home-team", str(args.home_team), "--away-team", str(args.away_team),
        "--tenant", args.tenant, "--segment-seconds", f"{args.segment_seconds:g}",
        "--start-minute", f"{args.start_minute:g}", "--camera", args.camera,
        "--tiles", str(args.tiles), "--track-fps", f"{args.track_fps:g}",
        "--backend", args.backend, "--poll-seconds", f"{POLL_SECONDS:g}",
    ]
    if args.keep_up:
        track_cmd += ["--minute-from-name", KEEP_UP_MINUTE_PATTERN]
    weights = resolve_weights(args.weights, args.camera)
    for flag, val in (("--calibration", args.calibration), ("--weights", weights),
                      ("--onnx-model", args.onnx_model), ("--database-url", args.database_url)):
        if val:
            track_cmd += [flag, val]

    print(f"[canlı] kaynak: {kind.label} · {args.source}")
    print(f"[canlı] dedektör: {weights or 'COCO ön-eğitimli'}")
    print(f"[canlı] segment: {args.segment_seconds:g} sn → {watch}"
          f"{' · yeniden kodlama' if transcode or args.height else ' · kopya'}")
    print(f"[canlı] panel: /admin/matches/{args.match_id}/live-decision?my_team_id={args.home_team}"
          f"&current_minute=<işlenen dk>")
    t0 = time.time()
    seg_proc = subprocess.Popen(seg_cmd, cwd=str(PROJECT_ROOT))  # noqa: S603
    calibration = args.calibration
    if args.height and calibration:
        size = wait_first_segment_size(seg_dir, seg_proc)
        calibration = str(scale_calibration(Path(calibration), size, watch))
        track_cmd[track_cmd.index("--calibration") + 1] = calibration
        print(f"[canlı] kalibrasyon {size[0]}x{size[1]} segmentlere ölçeklendi: {calibration}")
    track_proc = subprocess.Popen(track_cmd, cwd=str(PROJECT_ROOT),  # noqa: S603
                                  env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    tele_proc = None
    if args.telestration:
        tele_cmd = [sys.executable, "-m", "scripts.telestrate_live", "--watch", str(watch),
                    "--calibration", calibration, "--home-attack", args.home_attack]
        if args.swap_at_minute is not None:
            tele_cmd += ["--swap-at-minute", f"{args.swap_at_minute:g}"]
        # düzeltilmiş top veritabanındaki aynı karelere de yazılır
        tele_cmd += ["--match-id", str(args.match_id), "--tenant", args.tenant]
        if args.database_url:
            tele_cmd += ["--database-url", args.database_url]
        tele_proc = subprocess.Popen(tele_cmd, cwd=str(PROJECT_ROOT),  # noqa: S603
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        print(f"[canlı] telestrasyon: {watch / 'tele'} (latest.json)")
    promoted: list[str] = []   # --keep-up: incoming adları, alınış sırasıyla
    skipped_total = 0
    try:
        while True:
            time.sleep(POLL_SECONDS)
            source_ended = seg_proc.poll() is not None
            elapsed = (time.time() - t0) if kind.realtime else None
            if args.keep_up:
                processed = {n for n in promoted
                             if keep_up_name(segment_index(n), start_minute=args.start_minute,
                                             segment_seconds=args.segment_seconds) in _processed_names(watch)}
                closed = closed_segments(seg_dir, source_ended)
                choice = keep_up_choice(closed, promoted, processed)
                if choice is not None:
                    skipped = [n for n in closed
                               if max((segment_index(m) for m in promoted), default=-1)
                               < segment_index(n) < segment_index(choice)]
                    target = keep_up_name(segment_index(choice), start_minute=args.start_minute,
                                          segment_seconds=args.segment_seconds)
                    # kopya: incoming tam kayıt olarak kalır; .part uzantısı takibe yarım dosya göstermez
                    shutil.copy2(seg_dir / choice, watch / f"{target}.part")
                    os.replace(watch / f"{target}.part", watch / target)
                    promoted.append(choice)
                    skipped_total += len(skipped)
                    print(f"[canlı] işlenecek: {target}"
                          f"{f' · atlandı {len(skipped)} segment' if skipped else ''}", flush=True)
                done = max((segment_index(n) + 1 for n in processed), default=0)
                written = len(closed)
                caught_up = source_ended and len(processed) == len(promoted) and \
                    keep_up_choice(closed, promoted, processed) is None
            else:
                done, written = _processed_count(watch), _written_count(watch)
                caught_up = source_ended and done >= written
            lat = latency(done, written, segment_seconds=args.segment_seconds, start_minute=args.start_minute,
                          elapsed_seconds=elapsed, source_ended=source_ended)
            print(f"[canlı] işlenen dk {lat.processed_minute:.1f} · akış dk {lat.stream_minute:.1f} "
                  f"· gecikme {lat.lag_seconds:.0f} sn", flush=True)
            write_status(watch, lat, skipped=skipped_total, keep_up=args.keep_up, source_ended=source_ended)
            if caught_up:
                if tele_proc is not None and tele_proc.poll() is None and _telestration_backlog(watch):
                    print(f"[canlı] telestrasyon bekleniyor: {_telestration_backlog(watch)} segment", flush=True)
                    continue
                print("[canlı] kaynak bitti ve bütün segmentler işlendi.")
                break
            if track_proc.poll() is not None:
                print(f"[canlı] izleyici durdu (kod {track_proc.returncode}).")
                break
    except KeyboardInterrupt:
        print("\n[canlı] durduruluyor…")
    finally:
        for proc in (seg_proc, track_proc, tele_proc):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
