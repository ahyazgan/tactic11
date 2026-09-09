"""Pozisyon verisinden maç-içi karar sinyalleri (video / StatsBomb 360 → context_engine).

`engine.tracking` takım şeklini ve pres yoğunluğunu ölçer; bu motor ARDIŞIK İKİ
PENCEREYİ karşılaştırıp koçun hemen kullanabileceği sinyaller çıkarır:

- rakip bloğu açıldı → dikey pas / hatlar arası koşu zamanı
- rakip geri hattı yükseldi → arkaya derinlik koşusu
- rakip geri hattı düştü → ayak altı + uzaktan şut / kanat değişimi
- rakip daraldı → oyunu genişlet, kanat değiştir
- bizim presimiz düştü → pres tetikleyicisini hatırlat
- rakip presi arttı → basit çıkış / uzun top

Sinyaller `CandidateSignal`e çevrilip context_engine'in "şimdi şunu yap"
sıralamasına girer (bkz. app/api/context_pipeline.py).

Neden iki pencere: mutlak değerler takıma/kameraya göre değişir; DEĞİŞİM koçun
tepki verebileceği şeydir ("blok açıldı" — "blok 18 m" değil).

Sınır: kamera görüş alanı dışındaki oyuncular sayılmaz. Az oyuncu görünen
pencerelerde sinyal üretilmez (`MIN_PLAYERS`), kısmi görünürlükte yanıltmasın.

ÖNEMLİ — şekil sinyalleri yalnız SÜREKLİ takipte (sabit kamera video) üretilir.
StatsBomb 360 gibi event-çapalı freeze frame'lerde her kare topun çevresini
gösterir; top sahanın öbür ucuna gidince "geri hat" gerçekte kaymadan zıplar.
Bu kaynaklarda yalnız topa göreli pres sinyalleri değerlendirilir (`continuous=False`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.tracking_signals"
ENGINE_VERSION = "1"

PITCH_LENGTH_M = 105.0
MIN_PLAYERS = 8.0          # pencere başına ortalama görünür oyuncu alt sınırı
# İki pencere arasında görünen oyuncu sayısı bu kadar oynarsa şekil farkı
# kıyaslanamaz (farklı altküme ölçülüyor) — şekil sinyalleri bastırılır.
MAX_VISIBILITY_DRIFT = 2.0
COMPACTNESS_DELTA_M = 2.5  # blok açılma/kapanma eşiği
LINE_DELTA_M = 4.0         # geri hat kayması eşiği
WIDTH_DELTA_M = 4.0        # genişlik değişimi eşiği
PRESS_DELTA = 0.15         # pres endeksi değişimi eşiği


@dataclass(frozen=True)
class TrackingFinding:
    """Tek bir pozisyon-temelli bulgu."""

    key: str
    headline: str          # koça gösterilecek Türkçe öneri
    urgency: float         # 0..1
    magnitude: float       # 0..1 — değişimin gücü
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingSignalReport:
    minute: float
    frames_used: int
    players_seen: float
    findings: tuple[TrackingFinding, ...]
    note: str | None = None


def _m(x_pct: float) -> float:
    """0-100 saha yüzdesi → metre (boyuna)."""
    return x_pct / 100.0 * PITCH_LENGTH_M


def _mag(delta: float, threshold: float) -> float:
    return round(min(1.0, abs(delta) / (threshold * 3)), 2)


def compute_tracking_signals(
    *,
    minute: float,
    our_shape: dict[str, Any] | None,
    their_shape: dict[str, Any] | None,
    prev_our_shape: dict[str, Any] | None = None,
    prev_their_shape: dict[str, Any] | None = None,
    our_pressure: dict[str, Any] | None = None,
    their_pressure: dict[str, Any] | None = None,
    prev_our_pressure: dict[str, Any] | None = None,
    frames_used: int = 0,
    continuous: bool = True,
) -> EngineResult[TrackingSignalReport]:
    """İki pencere arasındaki şekil/pres değişiminden karar sinyalleri.

    `continuous=False` (event-çapalı kaynak, örn. StatsBomb 360) → şekil
    karşılaştırması yapılmaz, yalnız topa göreli pres sinyalleri üretilir.
    """
    findings: list[TrackingFinding] = []
    note: str | None = None
    seen = 0.0
    for s in (our_shape, their_shape):
        if s:
            seen = max(seen, float(s.get("players_mean") or 0.0))

    if not our_shape or not their_shape or seen < MIN_PLAYERS:
        note = (
            f"pozisyon verisi yetersiz (görünen oyuncu {seen:.1f} < {MIN_PLAYERS})"
            if (our_shape or their_shape) else "pozisyon verisi yok"
        )
        report = TrackingSignalReport(minute=minute, frames_used=frames_used,
                                      players_seen=round(seen, 1), findings=(), note=note)
    else:
        # Şekil farkı ancak iki pencerede benzer sayıda oyuncu görünüyorsa
        # anlamlı: 8 oyuncuyla 12 oyuncunun "hattı" kıyaslanamaz.
        their_now = float(their_shape.get("players_mean") or 0.0)
        their_prev = float((prev_their_shape or {}).get("players_mean") or 0.0)
        if prev_their_shape and not continuous:
            note = (
                "şekil kıyaslanmadı: event-çapalı kareler topun çevresini gösterir "
                "(sürekli takip değil); yalnız pres sinyalleri değerlendirildi"
            )
            prev_their_shape = None
        elif prev_their_shape and abs(their_now - their_prev) > MAX_VISIBILITY_DRIFT:
            note = (
                f"şekil kıyaslanmadı: görünen oyuncu {their_prev:.1f} → {their_now:.1f} "
                "(farklı altküme); yalnız pres sinyalleri değerlendirildi"
            )
            prev_their_shape = None

        # 1) Rakip bloğu açıldı / kapandı (kompaktlık)
        if prev_their_shape:
            d = float(their_shape.get("compactness_m", 0)) - float(prev_their_shape.get("compactness_m", 0))
            if d >= COMPACTNESS_DELTA_M:
                findings.append(TrackingFinding(
                    key="opponent_block_opened",
                    headline=f"Rakip bloğu açıldı ({d:+.1f} m) — hatlar arası dikey pas zamanı",
                    urgency=0.7, magnitude=_mag(d, COMPACTNESS_DELTA_M),
                    detail={"compactness_delta_m": round(d, 1)},
                ))
            elif d <= -COMPACTNESS_DELTA_M:
                findings.append(TrackingFinding(
                    key="opponent_block_tightened",
                    headline=f"Rakip bloğu sıkıştı ({d:+.1f} m) — genişlik ve kanat değişimi ile aç",
                    urgency=0.5, magnitude=_mag(d, COMPACTNESS_DELTA_M),
                    detail={"compactness_delta_m": round(d, 1)},
                ))

        # 2) Rakip savunma hattı yükseldi / düştü
        if prev_their_shape:
            now_line = _m(float(their_shape.get("rear_line_x", 0)))
            prev_line = _m(float(prev_their_shape.get("rear_line_x", 0)))
            d = now_line - prev_line
            if abs(d) >= LINE_DELTA_M:
                pushed = d > 0
                findings.append(TrackingFinding(
                    key="opponent_line_pushed" if pushed else "opponent_line_dropped",
                    headline=(
                        f"Rakip savunma hattı {abs(d):.0f} m yükseldi — arkaya derinlik koşusu"
                        if pushed else
                        f"Rakip savunma hattı {abs(d):.0f} m düştü — ayak altı + uzaktan şut, kanat değiştir"
                    ),
                    urgency=0.65 if pushed else 0.5, magnitude=_mag(d, LINE_DELTA_M),
                    detail={"line_delta_m": round(d, 1), "rear_line_x": their_shape.get("rear_line_x")},
                ))

        # 3) Rakip genişliği daraldı (kanat boşluğu)
        if prev_their_shape:
            d = float(their_shape.get("width_m", 0)) - float(prev_their_shape.get("width_m", 0))
            if d <= -WIDTH_DELTA_M:
                findings.append(TrackingFinding(
                    key="opponent_narrowed",
                    headline=f"Rakip {abs(d):.0f} m daraldı — kanatlar boş, oyunu genişlet",
                    urgency=0.6, magnitude=_mag(d, WIDTH_DELTA_M),
                    detail={"width_delta_m": round(d, 1)},
                ))

        # 4) Bizim presimiz düştü
        if our_pressure and prev_our_pressure and our_pressure.get("frames_used"):
            d = float(our_pressure.get("press_index", 0)) - float(prev_our_pressure.get("press_index", 0))
            if d <= -PRESS_DELTA:
                findings.append(TrackingFinding(
                    key="our_press_dropped",
                    headline=(
                        f"Presimiz düştü ({d:+.2f}) — topa en yakın "
                        f"{our_pressure.get('nearest_mean_m', '?')} m; tetikleyiciyi hatırlat"
                    ),
                    urgency=0.75, magnitude=_mag(d, PRESS_DELTA),
                    detail={"press_delta": round(d, 2), **{k: our_pressure.get(k) for k in ("press_index", "nearest_mean_m")}},
                ))

        # 5) Rakip presi arttı → basit çıkış
        if their_pressure and their_pressure.get("frames_used"):
            idx = float(their_pressure.get("press_index", 0))
            if idx >= 0.65:
                findings.append(TrackingFinding(
                    key="opponent_press_high",
                    headline=(
                        f"Rakip yüksek pres yapıyor (endeks {idx:.2f}) — basit çıkış / uzun top,"
                        " kaleciyi oyuna kat"
                    ),
                    urgency=0.7, magnitude=round(min(1.0, idx), 2),
                    detail={"press_index": round(idx, 2), "nearest_mean_m": their_pressure.get("nearest_mean_m")},
                ))

        findings.sort(key=lambda f: (-f.urgency, -f.magnitude))
        report = TrackingSignalReport(
            minute=minute, frames_used=frames_used, players_seen=round(seen, 1),
            findings=tuple(findings),
            note=note or (None if findings else "şekil/pres değişimi eşiklerin altında"),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0, metric="tracking_signals",
        value=asdict(report),
        inputs={
            "minute": minute, "frames_used": frames_used, "players_seen": round(seen, 1),
            "thresholds": {
                "compactness_m": COMPACTNESS_DELTA_M, "line_m": LINE_DELTA_M,
                "width_m": WIDTH_DELTA_M, "press": PRESS_DELTA, "min_players": MIN_PLAYERS,
            },
        },
        formula=(
            "ardışık iki pencere farkı: kompaktlık/genişlik metre, geri hat x%→metre, "
            "pres endeksi 0-1; eşiği aşan değişim sinyal olur, magnitude = |Δ|/(3·eşik). "
            "Kamera dışı oyuncular sayılmaz — görünen oyuncu < 8 ise sinyal üretilmez."
        ),
    )
    return EngineResult(value=report, audit=audit)
