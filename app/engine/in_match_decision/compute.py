"""In-Match Decision Assistant — anlık maç durumundan TD kararları.

MatchState (skor, dakika, xG, yorgunluk, sub hakları, kartlar) → öncelikli
karar listesi:
  - sub (taze ayak gerek + sub var)
  - formation_change (skor durumu × dakika)
  - intensity_up / intensity_down (xG farkı + dakika)
  - game_management (önde + son 15 dk → vakit harca)
  - foul_trouble (oyuncu kart riski → değişiklik)
  - kill_the_game (önde + son 10 dk + yorgunsa)

Her decision: type, priority (urgent|recommended|optional), rationale (TR),
recommended_action (TR), risk_if_ignored (TR).

Pure compute, tek MatchState input.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.in_match_decision"
ENGINE_VERSION = "1"

# Eşikler
FATIGUE_SUB_THRESHOLD = 0.65            # avg yorgunluk (0=fresh,1=exhausted)
LATE_GAME_MINUTE = 75.0
END_GAME_MINUTE = 80.0
XG_DEFICIT_MAJOR = 0.35
YELLOW_TROUBLE_COUNT = 2                # oyuncu başına


@dataclass(frozen=True)
class MatchState:
    minute: float
    our_score: int = 0
    opp_score: int = 0
    our_xg_running: float = 0.0
    opp_xg_running: float = 0.0
    fatigue_avg: float = 0.5            # 0..1
    subs_left: int = 5
    yellows_in_starting_xi: int = 0     # toplam sarı kart sayısı
    opp_subs_used: int = 0
    formation_drift_alert: bool = False  # live_shape_drift sinyali


@dataclass(frozen=True)
class Decision:
    type: str                            # sub | formation_change | ...
    priority: str                        # urgent | recommended | optional
    rationale: str                       # TR
    recommended_action: str              # TR
    risk_if_ignored: str                 # TR
    confidence: float = 0.7              # 0..1


@dataclass(frozen=True)
class DecisionReport:
    minute: float
    score_state: str                     # leading | trailing | level
    decisions: tuple[Decision, ...]      # priority desc
    headline: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _score_state(state: MatchState) -> str:
    if state.our_score > state.opp_score:
        return "leading"
    if state.our_score < state.opp_score:
        return "trailing"
    return "level"


def _fatigue_sub(state: MatchState) -> Decision | None:
    if state.subs_left <= 0 or state.fatigue_avg < FATIGUE_SUB_THRESHOLD:
        return None
    priority = "urgent" if state.fatigue_avg > 0.80 else "recommended"
    return Decision(
        type="sub",
        priority=priority,
        rationale=f"Ortalama yorgunluk {state.fatigue_avg:.2f} — kritik eşik üstü",
        recommended_action="2 oyuncuyu değiştir (bir orta saha + bir defansif)",
        risk_if_ignored="Defansif aksiyon kaybı + sarı kart + sakatlık riski",
        confidence=min(1.0, state.fatigue_avg),
    )


def _intensity_change(state: MatchState, score_state: str) -> Decision | None:
    xg_gap = state.our_xg_running - state.opp_xg_running
    if score_state == "trailing" and state.minute >= LATE_GAME_MINUTE and xg_gap < XG_DEFICIT_MAJOR:
        return Decision(
            type="intensity_up",
            priority="urgent",
            rationale=f"Geride + dk {state.minute:.0f} + xG farkı {xg_gap:+.2f}",
            recommended_action="Yüksek pres + 4-2-4'e geç, taze ayaklarla risk al",
            risk_if_ignored="Maç istemediğin sonuçla bitebilir",
            confidence=0.9,
        )
    if score_state == "leading" and state.minute >= END_GAME_MINUTE:
        return Decision(
            type="intensity_down",
            priority="recommended",
            rationale=f"Önde + dk {state.minute:.0f} — son 10 dk vakit oyunu",
            recommended_action="Mid-block'a çekil, top sirkülasyonu + üst seviyeye uzun toplar",
            risk_if_ignored="Kontrol kaybı + skor değişebilir",
            confidence=0.85,
        )
    return None


def _formation_change(state: MatchState, score_state: str) -> Decision | None:
    if state.formation_drift_alert and state.minute < END_GAME_MINUTE:
        return Decision(
            type="formation_change",
            priority="recommended",
            rationale="Live shape drift alert — rakip şekli değiştirdi",
            recommended_action="Formasyonu rakibin yenisine göre güncelle (örn. 4-2-3-1 → 4-3-3)",
            risk_if_ignored="Orta saha sayısal dezavantajı + line kayması",
            confidence=0.75,
        )
    if score_state == "trailing" and state.minute >= LATE_GAME_MINUTE and state.subs_left > 0:
        return Decision(
            type="formation_change",
            priority="recommended",
            rationale="Geride + son 15 dk — agresif şekle geçiş zamanı",
            recommended_action="3 stoper + 5 hücum (3-2-5) veya 4-2-4; bir santrfor ekle",
            risk_if_ignored="Skor sabit kalır, kontra yememe avantajı kaybolur",
            confidence=0.80,
        )
    return None


def _foul_trouble(state: MatchState) -> Decision | None:
    if state.yellows_in_starting_xi < YELLOW_TROUBLE_COUNT:
        return None
    if state.subs_left <= 0:
        return None
    return Decision(
        type="foul_trouble",
        priority="recommended",
        rationale=f"İlk 11'de {state.yellows_in_starting_xi} sarı — kırmızı riski",
        recommended_action="Sarılı oyuncuyu çıkar, defansif yedek ile değiştir",
        risk_if_ignored="2. sarı + kırmızı → 10 kişi kalma riski",
        confidence=0.85,
    )


def _kill_the_game(state: MatchState, score_state: str) -> Decision | None:
    if score_state != "leading":
        return None
    if state.minute < END_GAME_MINUTE:
        return None
    return Decision(
        type="kill_the_game",
        priority="optional",
        rationale=f"Önde + dk {state.minute:.0f} — kapatma fazı",
        recommended_action="Top çevir + uzak köşeden korner kazan + tahaminli faul oyna",
        risk_if_ignored="Son dakika beraberlik veya kayıp riski",
        confidence=0.70,
    )


def _opportunity_exploit(state: MatchState) -> Decision | None:
    """Rakip sub'ları tükendi + geriden geliyoruz → momentum'u zorla."""
    if state.opp_subs_used < 4:
        return None
    if state.minute < 60:
        return None
    return Decision(
        type="exploit_opportunity",
        priority="recommended",
        rationale=f"Rakip {state.opp_subs_used} sub kullandı — taze ayak limiti",
        recommended_action="Bizim taze oyuncularla tempo'yu artır, sürekli koşturt",
        risk_if_ignored="Pencerey kapanır, rakip dengeleyebilir",
        confidence=0.75,
    )


PRIORITY_RANK = {"urgent": 3, "recommended": 2, "optional": 1}


def compute_in_match_decisions(state: MatchState) -> EngineResult[DecisionReport]:
    score_state = _score_state(state)
    decisions: list[Decision] = []
    for fn in (
        _fatigue_sub,
        _formation_change,
        _intensity_change,
        _foul_trouble,
        _kill_the_game,
        _opportunity_exploit,
    ):
        # closures take varying args
        if fn is _fatigue_sub:
            d = fn(state)
        elif fn in (_intensity_change, _formation_change, _kill_the_game):
            d = fn(state, score_state)
        else:
            d = fn(state)
        if d:
            decisions.append(d)

    decisions.sort(key=lambda d: (-PRIORITY_RANK[d.priority], -d.confidence))

    if not decisions:
        headline = (
            f"Dk {state.minute:.0f} {score_state} — durumu koru, "
            "akışı izle"
        )
    else:
        top = decisions[0]
        headline = (
            f"Dk {state.minute:.0f} {score_state} — {top.priority.upper()} "
            f"{top.type}: {top.recommended_action[:70]}"
        )

    report = DecisionReport(
        minute=state.minute,
        score_state=score_state,
        decisions=tuple(decisions),
        headline=headline,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=0,
        metric="in_match_decisions",
        value={
            "minute": state.minute,
            "score_state": score_state,
            "decision_count": len(decisions),
            "decision_types": [d.type for d in decisions],
            "top_priority": decisions[0].priority if decisions else None,
        },
        inputs={
            "state": {
                "our_score": state.our_score,
                "opp_score": state.opp_score,
                "fatigue_avg": state.fatigue_avg,
                "subs_left": state.subs_left,
                "yellows": state.yellows_in_starting_xi,
                "opp_subs_used": state.opp_subs_used,
                "shape_drift": state.formation_drift_alert,
            },
            "thresholds": {
                "fatigue_sub": FATIGUE_SUB_THRESHOLD,
                "late_game_minute": LATE_GAME_MINUTE,
                "end_game_minute": END_GAME_MINUTE,
                "xg_deficit_major": XG_DEFICIT_MAJOR,
                "yellow_trouble": YELLOW_TROUBLE_COUNT,
            },
        },
        formula=(
            "6 kural: fatigue_sub, formation_change, intensity_change, "
            "foul_trouble, kill_the_game, exploit_opportunity; "
            "priority sırasıyla sortlanır"
        ),
    )
    return EngineResult(value=report, audit=audit)
