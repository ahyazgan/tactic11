"""Sahada boşluk haritası — "nerede üstünlük var, nereye oyna" (pozisyon karelerinden).

`engine.tracking` takımın ŞEKLİNİ ölçer (genişlik/kompaktlık/hat), `engine.tracking_signals`
iki pencere arasındaki DEĞİŞİMİ yakalar. İkisi de takım geneli ortalamadır: koça
"rakip daraldı" der ama **nerede** boşluk açıldığını söylemez. Bu motor o boşluğu
sahanın üstünde yerleştirir:

- **Bölgesel sayısal üstünlük** — saha 3 koridor × 3 üçte bire bölünür, her hücrede
  bizim ve rakibin ortalama oyuncu sayısı sayılır ("sol kanat hücum üçte birinde 3v1")
- **Hatlar arası boşluk** — rakibin geri hattı ile orta hattı arasındaki mesafe ve
  o boşlukta kaç oyuncumuz var ("cebe gir")
- **Zayıf taraf** — rakibin terk ettiği koridor ("kanat değiştir")

## Hücum yönü — bu motorun ön koşulu

"Hücum üçte biri" yön bilinmeden anlamsızdır ve takımlar ikinci yarıda taraf değiştirir.
Veride yön bilgisi YOK, o yüzden kalecinin konumundan çıkarılır: bir takımın en derin
oyuncusu (kaleci) hangi kaledeyse o kaleyi savunur, ters yöne hücum eder.

Yön belirlenince tüm koordinatlar **bizim hücum yönümüze** çevrilir: x=100 hep bizim
hücum ettiğimiz kale. Yön ters ise saha 180° döndürülür — yani `x → 100-x` İLE BİRLİKTE
`y → 100-y`. Sadece x'i aynalamak koridorları ters çevirir ("sol" derken sağı gösterir);
180° döndürme fiziksel olarak doğru olandır (sahayı öbür uçtan seyretmek).

Sınır: kamera görüş alanı dışındaki oyuncular sayılmaz; kısmi kadroda hücre sayıları
düşük çıkar. Bu yüzden mutlak sayı değil **fark** (bizim − rakip) raporlanır ve
`MIN_PLAYERS` altında sinyal üretilmez.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult
from app.domain import TrackingFrame

ENGINE_NAME = "engine.space_map"
ENGINE_VERSION = "1"

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

LANES = ("sol", "merkez", "sağ")
THIRDS = ("savunma", "orta", "hücum")

MIN_PLAYERS = 8.0          # pencerede ortalama görünür oyuncu alt sınırı
# Oyuncuların yayıldığı x aralığı (0-100) bunun altındaysa kamera sahanın dar bir
# bandını görüyordur: "hücum üçte biri" gibi bölge sayımı tüm sahayı temsil etmez.
MIN_X_SPAN = 45.0
OVERLOAD_DELTA = 1.5       # hücrede "üstünlük" saymak için gereken fark
WEAK_SIDE_MAX = 1.0        # rakibin koridoru "terk ettiği" sayılan ortalama
LINE_GAP_M = 12.0          # hatlar arası "sömürülebilir" boşluk eşiği
LINE_CLUSTER_GAP_M = 8.0   # x ekseninde bu boşluk hattı böler
MIN_LINE_PLAYERS = 3       # bir hat sayılması için gereken oyuncu
DIRECTION_MARGIN = 6.0     # yön çıkarımında iki takım arası anlamlı fark (normalize x)


@dataclass(frozen=True)
class ZoneCell:
    """Bir koridor × üçte bir hücresi (bizim hücum yönümüze göre)."""

    lane: str
    third: str
    ours: float
    theirs: float
    delta: float


@dataclass(frozen=True)
class LineGapReport:
    """Rakibin geri hattı ile önündeki hat arasındaki boşluk (metre)."""

    def_line_m: float | None
    mid_line_m: float | None
    gap_m: float | None
    our_players_between: float


@dataclass(frozen=True)
class SpaceFinding:
    key: str
    headline: str
    urgency: float
    magnitude: float
    detail: dict[str, Any]


@dataclass(frozen=True)
class SpaceMap:
    minute: float
    frames_used: int
    players_seen: float
    attack_direction: int      # +1: x artan yöne hücum · -1: azalan · 0: bilinmiyor
    direction_method: str      # keeper | deepest | unknown
    zones: tuple[ZoneCell, ...]
    line_gap: LineGapReport
    best_overload: ZoneCell | None
    findings: tuple[SpaceFinding, ...]
    pitch_coverage: float = 0.0   # oyuncuların yayıldığı x aralığı (0-1)
    note: str | None = None


def _players(frame: TrackingFrame, team_external_id: int):
    return [p for p in frame.players if p.team_external_id == team_external_id]


def infer_attack_direction(
    frames: Iterable[TrackingFrame], team_external_id: int, opponent_external_id: int,
) -> tuple[int, str]:
    """Takımın hücum yönü: +1 (x artan) / -1 (x azalan) / 0 (bilinmiyor).

    Önce kaleci bayrağına bakılır (event kaynaklarında güvenilir); yoksa her
    takımın en derin oyuncusunun ortalama konumu kullanılır — kaleci pratikte
    hep en derindedir, rakibin en derini ise yükselmiş savunmacısıdır.
    """
    frames = list(frames)
    if not frames:
        return 0, "unknown"

    def keeper_mean(team: int) -> float | None:
        xs = [p.x for f in frames for p in _players(f, team) if p.is_keeper]
        return sum(xs) / len(xs) if xs else None

    ours_gk, theirs_gk = keeper_mean(team_external_id), keeper_mean(opponent_external_id)
    if ours_gk is not None and theirs_gk is not None and abs(ours_gk - theirs_gk) >= DIRECTION_MARGIN:
        # Kendi kalemiz nerede ise ters yöne hücum ederiz
        return (1, "keeper") if ours_gk < theirs_gk else (-1, "keeper")

    def deepest_mean(team: int) -> float | None:
        per_frame = [min((p.x for p in _players(f, team)), default=None) for f in frames]
        vals = [v for v in per_frame if v is not None]
        return sum(vals) / len(vals) if vals else None

    ours_deep, theirs_deep = deepest_mean(team_external_id), deepest_mean(opponent_external_id)
    if ours_deep is None or theirs_deep is None:
        return 0, "unknown"
    if abs(ours_deep - theirs_deep) < DIRECTION_MARGIN:
        # İki takımın en derini birbirine çok yakın — güvenli bir yön yok
        return 0, "unknown"
    return (1, "deepest") if ours_deep < theirs_deep else (-1, "deepest")


def _oriented(x: float, y: float, direction: int) -> tuple[float, float]:
    """Koordinatı bizim hücum yönümüze çevir (gerekirse sahayı 180° döndür)."""
    if direction >= 0:
        return x, y
    return 100.0 - x, 100.0 - y


def _lane(y: float) -> str:
    if y < 100.0 / 3:
        return "sol"
    return "merkez" if y < 200.0 / 3 else "sağ"


def _third(x: float) -> str:
    if x < 100.0 / 3:
        return "savunma"
    return "orta" if x < 200.0 / 3 else "hücum"


def _lines_by_gap(xs_m: list[float]) -> list[list[float]]:
    """x'e göre sıralı oyuncuları boşluğa bakarak hatlara böl."""
    if not xs_m:
        return []
    ordered = sorted(xs_m)
    lines: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - lines[-1][-1] > LINE_CLUSTER_GAP_M:
            lines.append([v])
        else:
            lines[-1].append(v)
    return lines


def _line_gap(
    frames: list[TrackingFrame], our_team: int, their_team: int, direction: int,
) -> LineGapReport:
    """Rakibin geri hattı ve önündeki hat arasındaki boşluk + oradaki oyuncularımız.

    Bizim hücum yönümüzde rakibin geri hattı EN YÜKSEK x'tedir (kendi kalesine
    en yakın); onun bir önündeki hat orta saha hattıdır. Kaleci hattı tek kişilik
    izole küme olarak düşülür.
    """
    gaps: list[float] = []
    defs: list[float] = []
    mids: list[float] = []
    between: list[int] = []
    for f in frames:
        theirs = [_oriented(p.x, p.y, direction)[0] / 100.0 * PITCH_LENGTH_M
                  for p in _players(f, their_team)]
        if len(theirs) < MIN_LINE_PLAYERS * 2:
            continue
        lines = _lines_by_gap(theirs)
        # Kaleci: en derin (bizim yönümüzde en yüksek x) tek kişilik küme
        if len(lines) >= 2 and len(lines[-1]) == 1:
            lines = lines[:-1]
        lines = [ln for ln in lines if len(ln) >= 2]
        if len(lines) < 2:
            continue
        def_line = sum(lines[-1]) / len(lines[-1])      # rakip geri hattı
        mid_line = sum(lines[-2]) / len(lines[-2])      # önündeki hat
        gap = def_line - mid_line
        if gap <= 0:
            continue
        defs.append(def_line)
        mids.append(mid_line)
        gaps.append(gap)
        ours_in = sum(
            1 for p in _players(f, our_team)
            if mid_line < _oriented(p.x, p.y, direction)[0] / 100.0 * PITCH_LENGTH_M < def_line
        )
        between.append(ours_in)
    if not gaps:
        return LineGapReport(None, None, None, 0.0)
    return LineGapReport(
        def_line_m=round(sum(defs) / len(defs), 1),
        mid_line_m=round(sum(mids) / len(mids), 1),
        gap_m=round(sum(gaps) / len(gaps), 1),
        our_players_between=round(sum(between) / len(between), 2),
    )


def _findings(
    zones: tuple[ZoneCell, ...], gap: LineGapReport, best: ZoneCell | None,
) -> tuple[SpaceFinding, ...]:
    out: list[SpaceFinding] = []
    if best is not None and best.delta >= OVERLOAD_DELTA:
        where = f"{best.lane} {best.third} üçte biri"
        # Hücum üçte birindeki üstünlük doğrudan gol şansıdır; orta sahadaki
        # aynı fark daha az aciliyet taşır — koçun sırası buna göre kurulur.
        urgency = 0.35 + best.delta * 0.06 + (0.12 if best.third == "hücum" else 0.0)
        out.append(SpaceFinding(
            key=f"overload_{best.lane}_{best.third}",
            headline=(f"{where.capitalize()}nde {best.ours:.1f}v{best.theirs:.1f} sayısal "
                      f"üstünlük — oyunu oraya çevir"),
            urgency=round(min(1.0, urgency), 2),
            magnitude=min(1.0, best.delta / 3.0),
            detail={"lane": best.lane, "third": best.third, "ours": best.ours,
                    "theirs": best.theirs, "delta": best.delta},
        ))
    if gap.gap_m is not None and gap.gap_m >= LINE_GAP_M:
        out.append(SpaceFinding(
            key="line_gap_open",
            headline=(f"Rakip hatları arası {gap.gap_m:.0f} m açık"
                      + (f" ({gap.our_players_between:.1f} oyuncumuz cepte) — dikey pas"
                         if gap.our_players_between >= 0.5
                         else " ama cepte oyuncumuz yok — ara boşluğa adam sok")),
            urgency=0.6 if gap.our_players_between >= 0.5 else 0.5,
            magnitude=min(1.0, gap.gap_m / 25.0),
            detail={"gap_m": gap.gap_m, "def_line_m": gap.def_line_m,
                    "mid_line_m": gap.mid_line_m,
                    "our_players_between": gap.our_players_between},
        ))
    # Zayıf taraf: rakibin terk ettiği kanat (hücum + orta üçte bir).
    # ÖNEMLİ: "boş" ile "görünmüyor" ayrılmalı. Bir koridorda hiç kimse yoksa
    # (ne biz ne rakip) orası büyük ihtimalle kameranın görmediği yerdir; oraya
    # "rakip terk etti, kanat değiştir" demek uydurma sinyaldir. Bu yüzden
    # koridorun sahada gözlendiğine dair kanıt aranır.
    lane_totals = {
        lane: sum(z.ours + z.theirs for z in zones if z.lane == lane)
        for lane in LANES
    }
    flanks = [z for z in zones if z.lane in ("sol", "sağ") and z.third in ("orta", "hücum")
              and lane_totals[z.lane] >= 1.0]
    weak = min(flanks, key=lambda z: z.theirs, default=None)
    if weak is not None and weak.theirs <= WEAK_SIDE_MAX:
        out.append(SpaceFinding(
            key=f"weak_side_{weak.lane}",
            headline=(f"Rakip {weak.lane} kanadı boşalttı ({weak.theirs:.1f} oyuncu) "
                      f"— kanat değiştir"),
            urgency=0.55,
            magnitude=min(1.0, (WEAK_SIDE_MAX - weak.theirs + 0.5) / 1.5),
            detail={"lane": weak.lane, "third": weak.third, "theirs": weak.theirs,
                    "ours": weak.ours},
        ))
    out.sort(key=lambda f: (f.urgency, f.magnitude), reverse=True)
    return tuple(out)


def compute_space_map(
    frames: Iterable[TrackingFrame],
    *,
    our_team_external_id: int,
    their_team_external_id: int,
    minute: float,
    continuous: bool = True,
) -> EngineResult[SpaceMap]:
    """Pencere içindeki karelerden bölgesel üstünlük + hatlar arası boşluk.

    `continuous=False` (StatsBomb 360 gibi event-çapalı kareler) → yalnız not
    döner: freeze-frame'ler topun çevresini gösterir, bölge sayımı sahanın
    tamamını temsil etmez ("sol kanat boş" derken kamera oraya bakmamıştır.)
    """
    frames = list(frames)
    empty_gap = LineGapReport(None, None, None, 0.0)
    if not frames:
        return _result(SpaceMap(
            minute=minute, frames_used=0, players_seen=0.0, attack_direction=0,
            direction_method="unknown", zones=(), line_gap=empty_gap,
            best_overload=None, findings=(), note="kare yok",
        ), minute=minute)

    seen = [len(_players(f, our_team_external_id)) + len(_players(f, their_team_external_id))
            for f in frames]
    players_seen = round(sum(seen) / len(seen), 1) if seen else 0.0

    if not continuous:
        return _result(SpaceMap(
            minute=minute, frames_used=len(frames), players_seen=players_seen,
            attack_direction=0, direction_method="unknown", zones=(), line_gap=empty_gap,
            best_overload=None, findings=(),
            note="event-çapalı kareler topun çevresini gösterir — bölge sayımı yapılmaz",
        ), minute=minute)

    if players_seen < MIN_PLAYERS:
        return _result(SpaceMap(
            minute=minute, frames_used=len(frames), players_seen=players_seen,
            attack_direction=0, direction_method="unknown", zones=(), line_gap=empty_gap,
            best_overload=None, findings=(),
            note=f"görünür oyuncu az ({players_seen:.1f}) — bölge sayımı güvenilmez",
        ), minute=minute)

    # Kamera sahanın ne kadarını görüyor? Dar bir bant görüyorsa üçte-bir sayımı
    # yanıltır ("hücum üçte biri boş" derken kamera oraya hiç bakmamıştır) ve
    # kaleciler kadraja girmediği için yön de çıkarılamaz. Asıl sebep budur,
    # o yüzden yön hatasından ÖNCE söylenir.
    xs = [p.x for f in frames for p in f.players
          if p.team_external_id in (our_team_external_id, their_team_external_id)]
    coverage = round((max(xs) - min(xs)) / 100.0, 2) if xs else 0.0
    if coverage * 100.0 < MIN_X_SPAN:
        return _result(SpaceMap(
            minute=minute, frames_used=len(frames), players_seen=players_seen,
            attack_direction=0, direction_method="unknown", zones=(), line_gap=empty_gap,
            best_overload=None, findings=(), pitch_coverage=coverage,
            note=(f"kamera sahanın yalnız ~%{coverage * 100:.0f}'ini görüyor — "
                  f"bölge analizi tüm sahayı temsil etmez"),
        ), minute=minute)

    direction, method = infer_attack_direction(
        frames, our_team_external_id, their_team_external_id,
    )
    if direction == 0:
        return _result(SpaceMap(
            minute=minute, frames_used=len(frames), players_seen=players_seen,
            attack_direction=0, direction_method=method, zones=(), line_gap=empty_gap,
            best_overload=None, findings=(), pitch_coverage=coverage,
            note=("hücum yönü çıkarılamadı (kaleci görünmüyor, iki takımın derinliği "
                  "birbirine yakın) — bölge analizi yön olmadan yanıltıcı olur"),
        ), minute=minute)

    ours_count: dict[tuple[str, str], int] = {}
    theirs_count: dict[tuple[str, str], int] = {}
    for f in frames:
        for p in _players(f, our_team_external_id):
            x, y = _oriented(p.x, p.y, direction)
            key = (_lane(y), _third(x))
            ours_count[key] = ours_count.get(key, 0) + 1
        for p in _players(f, their_team_external_id):
            x, y = _oriented(p.x, p.y, direction)
            key = (_lane(y), _third(x))
            theirs_count[key] = theirs_count.get(key, 0) + 1

    n = len(frames)
    zones = tuple(
        ZoneCell(
            lane=lane, third=third,
            ours=round(ours_count.get((lane, third), 0) / n, 2),
            theirs=round(theirs_count.get((lane, third), 0) / n, 2),
            delta=round((ours_count.get((lane, third), 0)
                         - theirs_count.get((lane, third), 0)) / n, 2),
        )
        for third in THIRDS for lane in LANES
    )
    # Üstünlük yalnız rakip sahasında iş görür: savunma üçte birindeki fazlalık
    # "üstünlük" değil, topu oradan çıkaramamaktır.
    attacking = [z for z in zones if z.third in ("orta", "hücum")]
    best = max(attacking, key=lambda z: z.delta, default=None)
    gap = _line_gap(frames, our_team_external_id, their_team_external_id, direction)
    findings = _findings(zones, gap, best)
    return _result(SpaceMap(
        minute=minute, frames_used=n, players_seen=players_seen,
        attack_direction=direction, direction_method=method,
        zones=zones, line_gap=gap, best_overload=best, findings=findings,
        pitch_coverage=coverage,
        note=None if findings else "belirgin bölgesel üstünlük ya da hat boşluğu yok",
    ), minute=minute)


def _result(value: SpaceMap, *, minute: float) -> EngineResult[SpaceMap]:
    return EngineResult(
        value=value,
        audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="match", subject_id=0,
            metric="space_map",
            value=asdict(value),
            inputs={
                "minute": minute,
                "frames_used": value.frames_used,
                "players_seen": value.players_seen,
                "attack_direction": value.attack_direction,
                "direction_method": value.direction_method,
                "pitch_coverage": value.pitch_coverage,
                "zones": [asdict(z) for z in value.zones],
                "line_gap": asdict(value.line_gap),
            },
            formula=(
                f"saha {len(LANES)} koridor × {len(THIRDS)} üçte bir; hücre farkı = "
                f"(bizim − rakip) oyuncu / kare; üstünlük eşiği {OVERLOAD_DELTA}, "
                f"hat boşluğu eşiği {LINE_GAP_M} m; koordinatlar hücum yönüne "
                f"göre 180° döndürülür"
            ),
        ),
    )
