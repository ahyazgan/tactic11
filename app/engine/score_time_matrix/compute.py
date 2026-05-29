"""Score-Time Matrix — skor-zaman karar reçetesi (Faz 7 K: #13, #14).

İki sinyal (saf karar reçetesi, event gerekmez):
13. Kapanış reçetesi: son N dakika + skor durumuna göre net talimat
    ("1-0 öndesin, 83. dk → topu köşeye götür, oyunu böl").
14. Risk/getiri eşiği: lig durumuna göre berabere yeterli mi yoksa galibiyet
    şart mı → hücum/savunma postürünü değiştirir.

Pure: current_minute + skor + (opsiyonel lig bağlamı).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.score_time_matrix"
ENGINE_VERSION = "1"

# Kapanış penceresi başlangıcı (dk)
CLOSING_MINUTE = 75.0
LATE_MINUTE = 85.0


@dataclass(frozen=True)
class ScoreTimeMatrixReport:
    team_external_id: int
    current_minute: float
    my_score: int
    opponent_score: int
    score_state: str            # "leading" | "drawing" | "trailing"
    in_closing_phase: bool
    # #13 kapanış reçetesi
    posture: str                # "see_out" | "balanced" | "chase" | "all_out"
    closing_recipe: str
    # #14 risk/getiri
    draw_acceptable: bool
    must_win: bool
    risk_reward_note: str
    alerts: tuple[str, ...] = field(default_factory=tuple)


def compute_score_time_matrix(
    team_external_id: int,
    *,
    current_minute: float,
    my_score: int,
    opponent_score: int,
    draw_is_enough: bool = False,
    must_win: bool = False,
) -> EngineResult[ScoreTimeMatrixReport]:
    diff = my_score - opponent_score
    state = "leading" if diff > 0 else "trailing" if diff < 0 else "drawing"
    closing = current_minute >= CLOSING_MINUTE
    late = current_minute >= LATE_MINUTE

    # #14 risk/getiri — berabere yeterli mi
    draw_ok = draw_is_enough and not must_win
    # Eğer berabere yeterliyse ve berabere/öndeysek riske girme
    risk_note_parts: list[str] = []
    if must_win:
        risk_note_parts.append("Galibiyet şart — beraberlik yetmez, risk al")
    elif draw_is_enough:
        risk_note_parts.append("Beraberlik yeterli — gereksiz risk alma")
    else:
        risk_note_parts.append("Standart lig maçı — skor durumuna göre yönet")
    risk_note = "; ".join(risk_note_parts)

    # #13 kapanış reçetesi — skor × zaman × bağlam
    if state == "leading":
        if late:
            posture = "see_out"
            recipe = (f"{my_score}-{opponent_score} öndesin, {current_minute:.0f}. dk "
                      "→ topu köşeye götür, oyunu böl, derinlik verme")
        elif closing:
            posture = "see_out" if draw_ok or diff >= 2 else "balanced"
            recipe = ("Öndesin — temkinli yönet, kontra fırsatı dışında riske girme")
        else:
            posture = "balanced"
            recipe = "Öndesin ama erken — oyun planını koru, ikinci golü ara"
    elif state == "drawing":
        if must_win and late:
            posture = "all_out"
            recipe = ("Berabere ve galibiyet şart, son dakikalar → tüm hücum, "
                      "ekstra forvet, riski göze al")
        elif must_win and closing:
            posture = "chase"
            recipe = "Berabere, galibiyet şart → baskıyı artır, hücum hamlesi yap"
        elif draw_is_enough and closing:
            posture = "see_out"
            recipe = "Beraberlik yeterli → mevcut dengeyi koru, gereksiz risk yok"
        else:
            posture = "balanced"
            recipe = "Berabere — dengeyi koru, fırsat kollayarak öne geç"
    else:  # trailing
        if late:
            posture = "all_out"
            recipe = (f"{my_score}-{opponent_score} gerideysen, {current_minute:.0f}. dk "
                      "→ tüm hücum, kale önüne yüklen, riski göze al")
        elif closing:
            posture = "chase"
            recipe = "Gerideysen — hücum hamlesi yap, kanatları zorla, tempoyu yükselt"
        else:
            posture = "chase"
            recipe = "Gerideysen ama vakit var — sabırlı bas, aceleci olma"

    alerts: list[str] = []
    if closing:
        alerts.append(f"KAPANIŞ ({current_minute:.0f}. dk): {recipe}")
    if must_win or draw_is_enough:
        alerts.append(f"RİSK/GETİRİ: {risk_note}")

    report = ScoreTimeMatrixReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        my_score=my_score,
        opponent_score=opponent_score,
        score_state=state,
        in_closing_phase=closing,
        posture=posture,
        closing_recipe=recipe,
        draw_acceptable=draw_ok,
        must_win=must_win,
        risk_reward_note=risk_note,
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="score_time_matrix",
        value={
            "score_state": state, "posture": posture,
            "closing_recipe": recipe, "must_win": must_win,
            "draw_acceptable": draw_ok, "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute, "my_score": my_score,
            "opponent_score": opponent_score,
            "draw_is_enough": draw_is_enough, "must_win": must_win,
        },
        formula="skor durumu × kapanış penceresi × lig bağlamı → postür + reçete",
    )
    return EngineResult(value=report, audit=audit)
