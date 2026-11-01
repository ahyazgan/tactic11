"""Maç saati — videonun duvar saatini servisin devre başlangıçlarına bağlar.

Canlı modda segment dakikası bugüne kadar `--start-minute + sıra × süre` idi:
operatör başlangıç dakikasını tahmin ediyor, devre arası boyunca saat akmaya
devam ediyor ve ikinci yarı "61. dakika" diye başlıyordu. Bu modül dakikayı
gerçek olaydan türetir:

    gerçek an = segmentin duvar saati − yayın gecikmesi
    dakika    = (gerçek an − o devrenin başlama anı) / 60 + devre tabanı (0/45/90/105)

Devre başlama anları canlı servisten gelir (`ServiceSnapshot.period_starts`;
Sportmonks ve API-Football ikisi de verir). İkinci yarı başlamadan önce ve ilk
yarının normal süresi + `MAX_ADDED_MIN` geçtikten sonra an "devre arası" sayılır:
o segment işlenmez (GPU boşa çalışmasın, panele sahte kare düşmesin).

## Yayın gecikmesi

TV/yayın akışı stadyumdan 30–60 sn geride gelir; servis ise stadyum saatini verir.
Gecikme bilinmiyorsa dakika o kadar kayar. İki yol:

- operatör verir (`delay_s`), ya da
- başlama vuruşu karesinden çıkarılır (`detect_kickoff`): iki takım kendi yarı
  sahasında, bir oyuncu orta noktada. O karenin duvar saati − servisin devre
  başlama anı = gecikme. Sezgiseldir; kalabalık kadraj ya da kesme sonrası
  yanılabilir, bu yüzden makul aralık (`DELAY_RANGE_S`) dışındaki sonuç alınmaz.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain import TrackingFrame

PERIOD_BASE_MIN = (0.0, 45.0, 90.0, 105.0)
PERIOD_LENGTH_MIN = (45.0, 45.0, 15.0, 15.0)
MAX_ADDED_MIN = 10.0
DELAY_RANGE_S = (-10.0, 180.0)
KICKOFF_CENTER_M = 3.0         # orta noktaya bu kadar yakın bir oyuncu
KICKOFF_HALF_TOLERANCE_M = 1.5  # oyuncu yarı çizgisini bu kadar geçebilir
KICKOFF_MIN_PLAYERS = 14
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


@dataclass(frozen=True)
class ClockState:
    period: int | None       # 1, 2, 3, 4; None = başlamadı / devre arası / bitti
    minute: float | None
    status: str              # pre_match | in_play | break | finished_or_unknown


@dataclass(frozen=True)
class MatchClock:
    period_starts: tuple[datetime, ...] = ()
    delay_s: float = 0.0
    stream_started_at: datetime | None = None
    segment_seconds: float = 30.0
    delay_anchored_periods: tuple[int, ...] = field(default=())

    def state_at(self, wall: datetime) -> ClockState:
        """Videonun `wall` anında maç saati."""
        real = wall - timedelta(seconds=self.delay_s)
        if not self.period_starts or real < self.period_starts[0]:
            return ClockState(None, None, "pre_match")
        idx = max(i for i, t in enumerate(self.period_starts) if t <= real)
        if idx >= len(PERIOD_BASE_MIN):
            return ClockState(None, None, "finished_or_unknown")
        elapsed = (real - self.period_starts[idx]).total_seconds() / 60.0
        if elapsed > PERIOD_LENGTH_MIN[idx] + MAX_ADDED_MIN:
            # sonraki devre henüz başlamadı (servis bildirmedi): devre arası / maç sonu
            return ClockState(None, None, "break")
        return ClockState(idx + 1, round(PERIOD_BASE_MIN[idx] + elapsed, 4), "in_play")

    def segment_wall(self, index: int) -> datetime:
        if self.stream_started_at is None:
            raise ValueError("stream_started_at bilinmiyor")
        return self.stream_started_at + timedelta(seconds=index * self.segment_seconds)

    def segment_state(self, index: int) -> ClockState:
        """Segmentin BAŞLANGIÇ anındaki maç saati."""
        return self.state_at(self.segment_wall(index))

    def with_period_starts(self, starts: Sequence[datetime]) -> MatchClock:
        return replace(self, period_starts=tuple(sorted(starts)))

    def anchor_delay(self, period: int, kickoff_wall: datetime) -> MatchClock | None:
        """Başlama vuruşunun duvar saatinden gecikme; makul aralık dışındaysa None."""
        if period < 1 or period > len(self.period_starts):
            return None
        delay = (kickoff_wall - self.period_starts[period - 1]).total_seconds()
        if not DELAY_RANGE_S[0] <= delay <= DELAY_RANGE_S[1]:
            return None
        return replace(self, delay_s=round(delay, 1),
                       delay_anchored_periods=tuple(sorted({*self.delay_anchored_periods, period})))

    # ---- dosya (canli_mac yazar ve segment adlarına uygular) --------------- #

    def to_json(self) -> dict:
        return {
            "period_starts": [t.isoformat() for t in self.period_starts],
            "delay_s": self.delay_s,
            "stream_started_at": self.stream_started_at.isoformat() if self.stream_started_at else None,
            "segment_seconds": self.segment_seconds,
            "delay_anchored_periods": list(self.delay_anchored_periods),
        }

    @classmethod
    def from_json(cls, data: dict) -> MatchClock:
        def ts(v: str | None) -> datetime | None:
            if not v:
                return None
            t = datetime.fromisoformat(v)
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        return cls(
            period_starts=tuple(t for t in (ts(v) for v in data.get("period_starts") or []) if t is not None),
            delay_s=float(data.get("delay_s") or 0.0), stream_started_at=ts(data.get("stream_started_at")),
            segment_seconds=float(data.get("segment_seconds") or 30.0),
            delay_anchored_periods=tuple(int(p) for p in data.get("delay_anchored_periods") or []))

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_json(), indent=1), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> MatchClock:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


def is_kickoff_frame(frame: TrackingFrame, home: int, away: int) -> bool:
    """İki takım kendi yarısında, en az bir oyuncu orta noktada mı (saha 105×68 m)."""
    pts = [(p.team_external_id, p.x / 100.0 * PITCH_LENGTH_M, p.y / 100.0 * PITCH_WIDTH_M) for p in frame.players
           if p.team_external_id in (home, away)]
    if len(pts) < KICKOFF_MIN_PLAYERS:
        return False
    half = PITCH_LENGTH_M / 2
    if not any(abs(x - half) <= KICKOFF_CENTER_M and abs(y - PITCH_WIDTH_M / 2) <= KICKOFF_CENTER_M
               for _, x, y in pts):
        return False
    home_x = [x for t, x, _ in pts if t == home]
    away_x = [x for t, x, _ in pts if t == away]
    if not home_x or not away_x:
        return False
    tol = KICKOFF_HALF_TOLERANCE_M
    home_left = sum(home_x) / len(home_x) < sum(away_x) / len(away_x)
    lo, hi = (home_x, away_x) if home_left else (away_x, home_x)
    return max(lo) <= half + tol and min(hi) >= half - tol


def detect_kickoff(frames: Iterable[TrackingFrame], home: int, away: int, min_run: int = 3) -> TrackingFrame | None:
    """Başlama vuruşu dizilişinin SON karesi (top oyuna girmeden hemen önce).

    En az `min_run` ardışık kare dizilişte olmalı (tek karelik rastlantı elenir);
    birden çok dizi varsa ilki alınır."""
    run: list[TrackingFrame] = []
    for f in sorted(frames, key=lambda f: f.minute):
        if is_kickoff_frame(f, home, away):
            run.append(f)
        elif run:
            if len(run) >= min_run:
                return run[-1]
            run = []
    return run[-1] if len(run) >= min_run else None


# ---- canlı mod klasörü (canli_mac; dondurulmuş takip koduna dokunulmaz) --- #

CLOCK_FILE = "clock.json"            # canli_mac: devre başlangıçları, akış başlangıcı, elle gecikme
ANCHOR_FILE = "clock_anchor.json"    # canli_mac: takip çıktısındaki başlama vuruşundan çıkarılan gecikme
KICKOFF_SEARCH_MIN = 3.0             # devrenin ilk bu kadar dakikasındaki segmentlerde aranır


def load_watch_clock(watch: Path) -> MatchClock | None:
    """İki dosyayı birleştir: devre yenilemesi (`clock.json`) çapalanmış gecikmeyi ezmesin."""
    path = watch / CLOCK_FILE
    if not path.exists():
        return None
    clock = MatchClock.load(path)
    anchor = watch / ANCHOR_FILE
    if anchor.exists():
        data = json.loads(anchor.read_text(encoding="utf-8"))
        clock = replace(clock, delay_s=float(data["delay_s"]),
                        delay_anchored_periods=tuple(int(p) for p in data.get("delay_anchored_periods") or []))
    return clock


def save_anchor(watch: Path, clock: MatchClock) -> None:
    tmp = watch / f"{ANCHOR_FILE}.tmp"
    tmp.write_text(json.dumps({"delay_s": clock.delay_s,
                               "delay_anchored_periods": list(clock.delay_anchored_periods)}), encoding="utf-8")
    tmp.replace(watch / ANCHOR_FILE)


def kickoff_anchor(clock: MatchClock, state: ClockState, segment_index: int, offset_minute: float,
                   frames: Iterable[TrackingFrame], home: int, away: int) -> MatchClock | None:
    """Devrenin başındaki segmentte başlama vuruşu bulunursa gecikmesi çapalanmış saat.

    Karenin dakikası `offset_minute`'tan itibaren segment içi zamandır; duvar saati
    = segment başlangıcı + (dakika − offset) × 60 sn."""
    if state.status != "in_play" or state.period is None or state.minute is None:
        return None
    if state.period in clock.delay_anchored_periods:
        return None
    if state.minute - PERIOD_BASE_MIN[state.period - 1] > KICKOFF_SEARCH_MIN:
        return None
    hit = detect_kickoff(frames, home, away)
    if hit is None:
        return None
    wall = clock.segment_wall(segment_index) + timedelta(seconds=(hit.minute - offset_minute) * 60.0)
    return clock.anchor_delay(state.period, wall)

