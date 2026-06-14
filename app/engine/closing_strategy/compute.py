"""Closing Strategy — kapanış reçetesi + risk/getiri eşiği (K kategorisi).

İki maç-içi karar sinyali:
1. Kapanış reçetesi: (skor_diff, dakika) → tempo + pozisyon + ikame + duran top
2. Risk/getiri eşiği: skor + kalan dakika → riski al/koru/dengele

Pure compute. Tek girdi: skor + dakika + (opsiyonel) momentum/kart/ikame durumu.
TD'nin "önde 1-0, 80'inci dk, ne yapayım?" sorusuna doğrudan cevap.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.closing_strategy"
ENGINE_VERSION = "1"

# Kapanış evresi sınırları (dakika)
PHASE_EARLY_END = 60.0
PHASE_MID_END = 75.0
PHASE_LATE_END = 90.0

# Skor durumu sınırları (mutlak gol farkı)
BIG_MARGIN = 3

# Risk eşikleri
RISK_TRAILING_BIG_MINUTE = 60.0   # 2+ geride → 60. dk'dan sonra tam risk
RISK_TRAILING_SMALL_MINUTE = 80.0  # 1 geride → 80'den sonra risk
RISK_LEADING_LOCK_MINUTE = 80.0    # Önde → 80'den sonra riski azalt


@dataclass(frozen=True)
class ClosingRecipe:
    """Skor+dakika kombinasyonu için somut taktik reçete."""
    tempo: str          # "düşür" | "normal" | "yükselt" | "agresif" | "acil"
    positioning: str    # "alçal" | "normal" | "yüksel" | "all-out"
    sub_priority: str   # "savunmacı" | "taze koşucu" | "hücumcu" | "yıldızı çek" | "yok"
    set_pieces: str     # "kısa-tut" | "alma" | "risk-al" | "her şey"
    extra_note: str     # serbest açıklama


@dataclass(frozen=True)
class RiskRewardAdvice:
    """Riski al / koru eşiği."""
    take_risk: bool
    rationale: str
    threshold_breached: str  # hangi eşik fırladı (örn. "trailing>=1 ve dk>=80")


@dataclass(frozen=True)
class ClosingStrategyReport:
    team_external_id: int
    current_minute: float
    minutes_remaining: float
    my_score: int
    opponent_score: int
    score_diff: int             # my - opp
    score_state: str            # big_lead | leading | level | trailing | big_deficit
    closing_phase: str          # early | mid | late | stoppage
    urgency_level: str          # low | moderate | high | critical
    recipe: ClosingRecipe
    risk_reward: RiskRewardAdvice
    key_message: str            # tek cümlelik özet


def _score_state(diff: int) -> str:
    if diff >= BIG_MARGIN:
        return "big_lead"
    if diff > 0:
        return "leading"
    if diff == 0:
        return "level"
    if diff > -BIG_MARGIN:
        return "trailing"
    return "big_deficit"


def _closing_phase(minute: float) -> str:
    if minute < PHASE_EARLY_END:
        return "early"
    if minute < PHASE_MID_END:
        return "mid"
    if minute < PHASE_LATE_END:
        return "late"
    return "stoppage"


def _urgency_level(state: str, phase: str, momentum_score: float) -> str:
    """Kararın aciliyeti — kullanıcı arayüzünde renk/icon."""
    # Stoppage + level/trailing + negatif momentum → critical
    if phase == "stoppage" and state in ("level", "trailing", "big_deficit"):
        return "critical"
    if phase == "late" and state in ("trailing", "big_deficit"):
        return "high"
    if phase == "late" and state == "level":
        return "high"
    if phase == "late" and state == "leading" and momentum_score < -0.3:
        return "high"  # önde olsak da rakip baskılıyor
    if phase == "mid":
        return "moderate"
    return "low"


def _build_recipe(state: str, phase: str, momentum: float) -> ClosingRecipe:
    """Skor × evre → somut reçete. Karar tablosu (pure logic)."""
    # Erken evre: kapanış henüz devreye girmedi
    if phase == "early":
        return ClosingRecipe(
            tempo="normal", positioning="normal", sub_priority="yok",
            set_pieces="alma",
            extra_note="Kapanış evresi değil — standart oyun planına devam",
        )

    # Önde + büyük farkla (big_lead): koru
    if state == "big_lead":
        if phase in ("late", "stoppage"):
            return ClosingRecipe(
                tempo="düşür", positioning="alçal",
                sub_priority="yıldızı çek",
                set_pieces="alma",
                extra_note="Yıldızları dinlendir, oyunu öldür, sakatlık riski azalt",
            )
        return ClosingRecipe(
            tempo="normal", positioning="normal",
            sub_priority="taze koşucu",
            set_pieces="kısa-tut",
            extra_note="Üstünlüğü koru, gereksiz risk yok",
        )

    # Önde tek-iki farkla (leading)
    if state == "leading":
        if phase == "stoppage":
            return ClosingRecipe(
                tempo="acil", positioning="alçal",
                sub_priority="savunmacı",
                set_pieces="alma",
                extra_note="Maçı bitir — top tuttur, ayak izini kaybet",
            )
        if phase == "late":
            note = "Beklet + savunmacı ikame"
            if momentum < -0.3:
                note += " — rakip baskısı yüksek, ekstra savunmacı"
            return ClosingRecipe(
                tempo="düşür", positioning="alçal",
                sub_priority="savunmacı",
                set_pieces="alma", extra_note=note,
            )
        # mid
        return ClosingRecipe(
            tempo="normal", positioning="normal",
            sub_priority="taze koşucu",
            set_pieces="kısa-tut",
            extra_note="Skoru koru, fırsat çıkarsa 2. golü kovala",
        )

    # Beraberlik (level)
    if state == "level":
        if phase == "stoppage":
            return ClosingRecipe(
                tempo="acil", positioning="yüksel",
                sub_priority="hücumcu",
                set_pieces="risk-al",
                extra_note="Berabere kabul mu? Kazanmak istiyorsan tam risk",
            )
        if phase == "late":
            return ClosingRecipe(
                tempo="yükselt", positioning="yüksel",
                sub_priority="hücumcu",
                set_pieces="risk-al",
                extra_note="3 puan kovalamanın zamanı — kanat genişlet",
            )
        return ClosingRecipe(
            tempo="normal", positioning="normal",
            sub_priority="taze koşucu",
            set_pieces="alma",
            extra_note="Dengeli — momentum izle",
        )

    # Geride tek-iki farkla (trailing)
    if state == "trailing":
        if phase == "stoppage":
            return ClosingRecipe(
                tempo="acil", positioning="all-out",
                sub_priority="hücumcu",
                set_pieces="her şey",
                extra_note="Kale önüne yığ — GK'yi de gönder",
            )
        if phase == "late":
            return ClosingRecipe(
                tempo="agresif", positioning="all-out",
                sub_priority="hücumcu",
                set_pieces="risk-al",
                extra_note="Tam risk — beraberliği ya da galibiyeti zorla",
            )
        # mid
        note = "Tempo yükselt + kanat değişikliği düşün"
        if momentum > 0.3:
            note += " — momentum bizde, sabırlı baskı"
        return ClosingRecipe(
            tempo="yükselt", positioning="yüksel",
            sub_priority="hücumcu",
            set_pieces="risk-al", extra_note=note,
        )

    # Büyük farkla geride (big_deficit)
    if phase == "stoppage":
        return ClosingRecipe(
            tempo="acil", positioning="all-out",
            sub_priority="hücumcu",
            set_pieces="her şey",
            extra_note="Onuru kurtar — büyük dezavantaj, fark kapanmaz ama gol gerekli",
        )
    if phase == "late":
        return ClosingRecipe(
            tempo="agresif", positioning="all-out",
            sub_priority="hücumcu",
            set_pieces="risk-al",
            extra_note="Fark çok büyük ama 1-2 gol moral için kritik",
        )
    return ClosingRecipe(
        tempo="yükselt", positioning="yüksel",
        sub_priority="hücumcu",
        set_pieces="risk-al",
        extra_note="Fark kapanması zor — sistemli baskı, paniğe gerek yok",
    )


def _risk_reward(state: str, diff: int, minute: float) -> RiskRewardAdvice:
    """Risk eşiği: skor + dakika → riski al/koru."""
    # 2+ geride + 60. dk sonrası → tam risk
    if diff <= -2 and minute >= RISK_TRAILING_BIG_MINUTE:
        return RiskRewardAdvice(
            take_risk=True,
            rationale=(
                f"{abs(diff)} gol gerideyiz ve {int(minute)}. dk — "
                f"savunmacı oynamanın anlamı yok, tam risk al"
            ),
            threshold_breached=f"diff<=-2 ve dk>={RISK_TRAILING_BIG_MINUTE:.0f}",
        )
    # 1 geride + son 10 dk → risk
    if diff == -1 and minute >= RISK_TRAILING_SMALL_MINUTE:
        return RiskRewardAdvice(
            take_risk=True,
            rationale=(
                "1 gol gerideyiz ve son 10 dk — beraberliği kovala, "
                "kanat genişlet, hücum ikame"
            ),
            threshold_breached=f"diff==-1 ve dk>={RISK_TRAILING_SMALL_MINUTE:.0f}",
        )
    # Önde + son 10 dk → riski azalt
    if diff >= 1 and minute >= RISK_LEADING_LOCK_MINUTE:
        return RiskRewardAdvice(
            take_risk=False,
            rationale=(
                f"{diff} gol öndeyiz, son 10 dk — kontra riski yüksek, "
                "topu tut, alçal, savunmacı ikame"
            ),
            threshold_breached=f"diff>=1 ve dk>={RISK_LEADING_LOCK_MINUTE:.0f}",
        )
    # Berabere + son 5 dk → temkinli risk
    if diff == 0 and minute >= 85.0:
        return RiskRewardAdvice(
            take_risk=True,
            rationale=(
                "Berabere + son 5 dk — kazanmak için risk al, "
                "ama kontradan yememeye dikkat"
            ),
            threshold_breached="diff==0 ve dk>=85",
        )
    # Erken evre veya nötr — risk eşiği fırlamadı
    return RiskRewardAdvice(
        take_risk=False,
        rationale="Risk eşiği henüz fırlamadı — standart oyun planı",
        threshold_breached="none",
    )


def _key_message(state: str, phase: str, recipe: ClosingRecipe) -> str:
    """Kısa-cümle özet — UI'de büyük başlık."""
    state_tr = {
        "big_lead": "Büyük farkla önde",
        "leading": "Önde",
        "level": "Berabere",
        "trailing": "Geride",
        "big_deficit": "Büyük farkla geride",
    }[state]
    phase_tr = {
        "early": "erken evre",
        "mid": "orta evre",
        "late": "son 15 dk",
        "stoppage": "uzatma",
    }[phase]
    return (
        f"{state_tr} · {phase_tr} → "
        f"tempo: {recipe.tempo}, dizilim: {recipe.positioning}, "
        f"ikame: {recipe.sub_priority}"
    )


def compute_closing_strategy(
    team_external_id: int,
    *,
    current_minute: float,
    my_score: int,
    opponent_score: int,
    match_total_minutes: float = 90.0,
    momentum_score: float = 0.0,
) -> EngineResult[ClosingStrategyReport]:
    """Kapanış reçetesi + risk/getiri eşiği.

    Pure compute — skor + dakika + (opsiyonel) momentum → reçete.
    """
    diff = my_score - opponent_score
    state = _score_state(diff)
    phase = _closing_phase(current_minute)
    urgency = _urgency_level(state, phase, momentum_score)
    recipe = _build_recipe(state, phase, momentum_score)
    risk = _risk_reward(state, diff, current_minute)
    msg = _key_message(state, phase, recipe)
    minutes_remaining = max(0.0, match_total_minutes - current_minute)

    report = ClosingStrategyReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        minutes_remaining=minutes_remaining,
        my_score=my_score,
        opponent_score=opponent_score,
        score_diff=diff,
        score_state=state,
        closing_phase=phase,
        urgency_level=urgency,
        recipe=recipe,
        risk_reward=risk,
        key_message=msg,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="closing_strategy",
        value={
            "score_state": state,
            "closing_phase": phase,
            "urgency_level": urgency,
            "score_diff": diff,
            "minutes_remaining": minutes_remaining,
            "recipe": {
                "tempo": recipe.tempo,
                "positioning": recipe.positioning,
                "sub_priority": recipe.sub_priority,
                "set_pieces": recipe.set_pieces,
                "extra_note": recipe.extra_note,
            },
            "risk_reward": {
                "take_risk": risk.take_risk,
                "rationale": risk.rationale,
                "threshold_breached": risk.threshold_breached,
            },
            "key_message": msg,
        },
        inputs={
            "current_minute": current_minute,
            "my_score": my_score, "opponent_score": opponent_score,
            "match_total_minutes": match_total_minutes,
            "momentum_score": momentum_score,
            "thresholds": {
                "phase_early_end": PHASE_EARLY_END,
                "phase_mid_end": PHASE_MID_END,
                "phase_late_end": PHASE_LATE_END,
                "risk_trailing_big_minute": RISK_TRAILING_BIG_MINUTE,
                "risk_trailing_small_minute": RISK_TRAILING_SMALL_MINUTE,
                "risk_leading_lock_minute": RISK_LEADING_LOCK_MINUTE,
            },
        },
        formula=(
            "(score_diff, minute) → state×phase → reçete; "
            "(diff, minute) → risk eşiği"
        ),
    )
    return EngineResult(value=report, audit=audit)
