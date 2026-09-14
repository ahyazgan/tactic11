"""Takipten pas çıkarımı — video karelerinden pas olayları üret.

## Neden

Takip hattı oyuncuları, topu ve kare başına **aktörü** (topa en yakın oyuncu)
zaten üretiyor. Eksik olan tek şey bunları olaya çevirmekti: kulüp kendi
kamerasıyla kayıt yapıyor ama pas verisi olmadığı için karar etkisi ölçümü
"YALNIZ xG ile (pas verisi yok, xT doğrulaması yapılamadı)" diyordu. xT, ileri
pas, alan kazanımı gibi motorların hepsi pas bekliyor.

## Tanım — neden temiz

`build_frame` aktörü yalnız oyuncu topa `ACTOR_RADIUS_M` içindeyse işaretler.
Pas uçarken top iki oyuncunun arasındadır, yani **aktör YOKTUR**. Dolayısıyla:

    A tutuyor → (aktör yok: uçuş) → B tutuyor

Bu geçiş pas ADAYIDIR. Aynı takım → tamamlanan pas adayı; farklı takım →
top kaybı ve mesafe yeterliyse tamamlanmayan pas adayı; aynı oyuncu → top sürme.
Sekme, oyuncu kimliği veya top tespit hatası aynı geçişi taklit edebilir.

## Dürüstlük

Video türevi pas **asla kesin değildir**: top kaybolabilir, kimlik takası
olabilir, sekme pas sanılabilir. Bu yüzden:

- her pas `estimated=True` gelir,
- kabul için fiziksel kapılar vardır (uçuş süresi, mesafe, tutuş kararlılığı),
- **reddedilenler sayılır ve raporlanır** — kaç pasın neden atıldığını görmeden
  çıktıya güvenilmemeli,
- top enterpole edilmişken (görülmemiş, komşu karelerden uydurulmuş) yapılan
  geçişler ayrı sayılır; bunlar en kırılgan olanlardır.

## Ölçüm sınırı

SkillCorner 2017461: 40.404 kare, 824 referans sahiplik geçişi. İki ucun
kimliğini ve zamanını denetleyen birebir eşleme 380 adayın 215'ini eşliyor
(%56,6 kesinlik, %26,1 duyarlılık; önceki motorla aynı). Tekrar üretim:
`scripts/audit_skillcorner_passes.py`. Aktör ve referans aynı sağlayıcıdan
geldiği için bu, bağımsız video doğruluğu değil algoritma regresyonudur.
Eski %72 ölçüsü ara sahiplik atlamalarını da sayıyordu; doğru pas kesinliği
olarak kullanılmamalı. SoccerTrack olay bazlı kontrol: docs/VIDEO-OLAY-SONUCLARI.md.

Saf mantık: cv2/DB gerektirmez, `TrackingFrame` dizisi alır.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.tracking import TrackingFrame

ENGINE_NAME = "tracking.passes"
ENGINE_VERSION = "2"

# Saha boyutları (normalize 0-100 → metre)
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

# Uçuş bu kadar uzun sürdüyse topu kaybetmişizdir; pas iddia edilmez.
MAX_FLIGHT_SECONDS = 6.0
# Bu mesafenin altı pas sayılmaz: kimlik titremesi ya da ayak altı mücadelesi.
MIN_PASS_DISTANCE_M = 3.0
# Bir oyuncunun "tutuyor" sayılması için kaç ardışık karede aktör olması gerek.
# 1 kare yetseydi tek karelik kimlik takası sahte pas üretirdi.
MIN_HOLD_FRAMES = 2
MIN_HOLD_SECONDS = 0.10
MAX_SAMPLE_GAP_SECONDS = 0.5
MAX_PASS_SPEED_MPS = 45.0


@dataclass(frozen=True)
class DerivedPass:
    """Video takibinden çıkarılmış pas. `estimated` HER ZAMAN True."""

    minute: float
    team_external_id: int
    from_player_external_id: int
    to_player_external_id: int
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    distance_m: float
    flight_seconds: float
    ball_estimated: bool          # uçuş sırasında top enterpole edildi mi
    # Alıcı KENDİ takımından mı? False ise pas kesilmiştir (rakip aldı).
    #
    # Bu ayrım şart: yalnız tamamlananları saysaydık isabet oranı HER ZAMAN
    # %100 çıkardı ve veri yalan söylerdi. Kesilen pas ile kaptırma farkı
    # mesafedir — top ciddi yol aldıysa pas denemesidir, ayak altında
    # kaybedildiyse kaptırmadır (o zaten `turnovers`ta).
    complete: bool = True
    estimated: bool = True
    period: int = 1
    observed_flight: bool = False


@dataclass(frozen=True)
class PassExtraction:
    passes: tuple[DerivedPass, ...] = field(default_factory=tuple)
    turnovers: int = 0
    frames_seen: int = 0
    frames_with_actor: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def actor_ratio(self) -> float:
        """Karelerin ne kadarında topu tutan biri belirlenebildi."""
        return (round(self.frames_with_actor / self.frames_seen, 3)
                if self.frames_seen else 0.0)


def _dist_m(ax: float, ay: float, bx: float, by: float) -> float:
    dx = (bx - ax) / 100.0 * PITCH_LENGTH_M
    dy = (by - ay) / 100.0 * PITCH_WIDTH_M
    return float((dx * dx + dy * dy) ** 0.5)


def _actor(frame: TrackingFrame):
    for p in frame.players:
        if p.is_actor:
            return p
    return None


@dataclass
class _Holder:
    player: int
    team: int
    x: float
    y: float
    minute: float
    frames: int
    last_minute: float = 0.0


def extract_passes(frames: list[TrackingFrame]) -> PassExtraction:
    """Kare dizisinden pasları çıkar.

    Kareler dakikaya göre SIRALI gelmeli; sıralı değilse uçuş süreleri anlamsız
    olur. Çağıran sıralamayı garanti eder (hat zaten sıralı üretir).
    """
    if not frames:
        return PassExtraction(note="kare yok")

    passes: list[DerivedPass] = []
    rejected: dict[str, int] = {}
    turnovers = 0
    with_actor = 0

    def _reddet(sebep: str) -> None:
        rejected[sebep] = rejected.get(sebep, 0) + 1

    onaylı: _Holder | None = None      # kararlılık kapısını geçmiş tutucu
    aday: _Holder | None = None        # henüz yeterince kare tutmamış
    ucusta_enterpole = False
    previous: TrackingFrame | None = None

    for fr in frames:
        if previous is not None:
            dt = (fr.minute - previous.minute) * 60
            if (fr.match_external_id != previous.match_external_id
                    or fr.period != previous.period
                    or fr.continuity_id != previous.continuity_id or dt <= 0):
                onaylı = aday = None
                ucusta_enterpole = False
                _reddet("maç/yarı/zaman sürekliliği koptu")
            elif dt > MAX_SAMPLE_GAP_SECONDS:
                aday = None
                ucusta_enterpole = True
        previous = fr
        is_video = fr.source in {"video_tracking", "broadcast_tracking"}
        uncertain_ball = fr.ball_estimated or (is_video and fr.ball is None)
        if onaylı is not None and uncertain_ball:
            ucusta_enterpole = True
        act = _actor(fr)
        if act is None or act.team_external_id is None:
            # Aktör yok → top uçuyor (ya da görülmüyor). Tutuş adaylığı düşer.
            aday = None
            if fr.ball_estimated:
                ucusta_enterpole = True
            continue

        with_actor += 1
        pid, team = act.player_external_id, act.team_external_id

        if aday is not None and aday.player == pid and aday.team == team:
            aday.frames += 1
            aday.last_minute = fr.minute
        else:
            aday = _Holder(pid, team, act.x, act.y, fr.minute, 1, fr.minute)

        if (aday.frames < MIN_HOLD_FRAMES
                or (aday.last_minute - aday.minute) * 60 + 0.001 < MIN_HOLD_SECONDS):
            continue                    # henüz kararlı değil

        if onaylı is None:
            onaylı = _Holder(pid, team, act.x, act.y, fr.minute, aday.frames, fr.minute)
            ucusta_enterpole = uncertain_ball
            continue
        if onaylı.player == pid and onaylı.team == team:
            onaylı.x, onaylı.y, onaylı.minute = act.x, act.y, fr.minute
            # A previous uncertain spell while dribbling must not taint a later pass.
            ucusta_enterpole = uncertain_ball
            continue                    # aynı oyuncu sürüyor

        # Tutucu DEĞİŞTİ.
        ucus = (aday.minute - onaylı.minute) * 60.0
        mesafe = _dist_m(onaylı.x, onaylı.y, aday.x, aday.y)

        ayni_takim = onaylı.team == team
        if not ayni_takim and onaylı.player != pid and 0 < ucus <= MAX_FLIGHT_SECONDS:
            turnovers += 1

        if ucus <= 0:
            _reddet("pozitif uçuş süresi yok")
        elif onaylı.player == pid:
            _reddet("aynı kimlikte takım değişti")
        elif ucus > MAX_FLIGHT_SECONDS:
            # Aradaki boşluk çok uzun: top izlenemedi, ne olduğunu bilmiyoruz.
            _reddet("uçuş çok uzun (top izlenemedi)")
        elif mesafe < MIN_PASS_DISTANCE_M:
            # Kısa mesafe: aynı takımda kimlik takası, rakipte ayak altı kaptırma.
            _reddet("mesafe çok kısa (kimlik takası olabilir)" if ayni_takim
                    else "kısa mesafe kaptırma (pas denemesi değil)")
        elif is_video and mesafe > MAX_PASS_SPEED_MPS * ucus + 2.5:
            _reddet("fiziksel hız sınırı aşıldı")
        else:
            passes.append(DerivedPass(
                # Takım DAİMA pası ATANIN takımıdır; kesilen pasta alıcı rakiptir.
                minute=round(onaylı.minute, 4), team_external_id=onaylı.team,
                from_player_external_id=onaylı.player, to_player_external_id=pid,
                start_x=round(onaylı.x, 2), start_y=round(onaylı.y, 2),
                end_x=round(aday.x, 2), end_y=round(aday.y, 2),
                distance_m=round(mesafe, 2), flight_seconds=round(ucus, 2),
                ball_estimated=ucusta_enterpole, complete=ayni_takim,
                period=fr.period,
                observed_flight=is_video and not ucusta_enterpole,
            ))
        onaylı = _Holder(pid, team, act.x, act.y, fr.minute, aday.frames, fr.minute)
        ucusta_enterpole = uncertain_ball

    n = len(frames)
    oran = with_actor / n if n else 0.0
    if not passes and with_actor == 0:
        not_ = ("hiçbir karede topu tutan belirlenemedi — top takibi ya da takım "
                "ataması çalışmamış; pas çıkarımı yapılamaz")
    elif oran < 0.25:
        not_ = (f"karelerin yalnız %{oran * 100:.0f}'inde topu tutan belirlendi — "
                f"pas listesi EKSİK; top takibi zayıf")
    else:
        belirsiz = sum(1 for p in passes if p.ball_estimated)
        tam = sum(1 for p in passes if p.complete)
        isabet = f" (%{tam / len(passes) * 100:.0f} isabet)" if passes else ""
        not_ = (f"{len(passes)} pas denemesi{isabet} · {turnovers} top kaybı · "
                f"karelerin %{oran * 100:.0f}'inde tutucu belirlendi")
        if belirsiz:
            not_ += f" · {belirsiz} pasta top enterpole edilmişti (kırılgan)"

    return PassExtraction(
        passes=tuple(passes), turnovers=turnovers, frames_seen=n,
        frames_with_actor=with_actor, rejected=rejected, note=not_,
    )
