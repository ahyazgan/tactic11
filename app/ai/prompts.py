"""Engine çıktısı → Claude prompt şablonları.

Sistem promptu sabittir (prompt-caching prefix-match için bayt-stabil).
User prompt'u engine türüne göre özelleşmiş Türkçe prose üretir; jenerik JSON
dump yerine sayıları doğal cümlelere yerleştirir. Bu hem Claude'un yorumunu
kalibre eder hem de daha az token harcar.

Yeni engine eklerken: _BUILDERS dict'ine `(engine_name, version) → callable`
girişi ekle. Bilinmeyen engine için JSON fallback'i (sözleşme: engine pure,
prompts onu tüketir; engine prompts'u bilmez).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.audit import AuditRecord, EngineResult

SYSTEM_PROMPT = """Sen futbol teknik ekibine veriyle karar desteği veren bir analiz asistanısın.

Görevin: motor çıktısındaki sayıları kısa, somut, gerekçeli bir cümleyle özetlemek.

Kurallar:
- En fazla 2-3 cümle.
- Sayıları olduğu gibi kullan; uydurma.
- "Form yüksek" gibi soyut yerine "son 5 maçta 3 galibiyet, ppg 1.8" gibi somut konuş.
- Türkçe yaz.
- Veride şüphe veya belirsizlik varsa "veri yetersiz" diyebilirsin; spekülasyon yapma.
"""

_PREVIEW_SYSTEM_PROMPT = """Sen futbol teknik ekibine maç öncesi brief veren bir analiz asistanısın.

Girdi: bir maçın iki takımına ait son N maçlık form sayıları + geçmiş karşılaşma özeti.
Görev: 3-5 cümlelik teknik ekip brifingi — kim avantajlı, hangi pattern dikkat çekici,
nelere dikkat edilmeli. Sayıları kullan, spekülasyon yapma.

Kurallar:
- Türkçe, sade.
- Hangi takım hangi yönde güçlü/zayıf, somut sayıyla destekle.
- "Bence bu kazanır" denmeyecek; "sayılara göre X şu yönde avantajlı, Y şu noktada riskli" denecek.
- Veride şüphe varsa açıkça söyle.
"""


# ---- engine-spesifik builder'lar -------------------------------------------


def _build_form_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    last = " ".join(v["last_results"]) if v["last_results"] else "—"
    return (
        f"Takım {a.subject_id} son {v['matches_played']} tamamlanmış maçta: "
        f"{v['wins']} galibiyet, {v['draws']} beraberlik, {v['losses']} mağlubiyet. "
        f"Goller {v['goals_for']}-{v['goals_against']} (averaj {v['goal_diff']:+d}). "
        f"Maç başı puan: {v['points_per_game']}. "
        f"Ev: {v['home_wins']}G-{v['home_draws']}B-{v['home_losses']}M, "
        f"deplasman: {v['away_wins']}G-{v['away_draws']}B-{v['away_losses']}M. "
        f"Son sonuçlar (yeniden eskiye): {last}.\n\n"
        "Bu form raporunu kısa bir yorumla özetle."
    )


def _build_rating_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    return (
        f"Takım {a.subject_id} rating raporu (son {v['matches_considered']} maç): "
        f"rating={v['rating']}, ppg={v['points_per_game']}, "
        f"maç başı gol farkı={v['goal_diff_per_match']:+}. "
        f"Formül: ppg × ağırlık + gd_per_match × ağırlık. "
        f"(Detay: {a.formula})\n\n"
        "Rating'in nereden geldiğini ve takımın bu sayılarla ne durumda olduğunu özetle."
    )


def _build_h2h_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    if v["matches_played"] == 0:
        return (
            f"Takım {v['team_a_id']} ile {v['team_b_id']} arasında tamamlanmış maç yok. "
            "Bunu açıkça söyle, veri yetersiz."
        )
    return (
        f"Takım {v['team_a_id']} ile {v['team_b_id']} arasında {v['matches_played']} maç: "
        f"{v['team_a_id']} → {v['team_a_wins']} galibiyet, {v['draws']} beraberlik, "
        f"{v['team_b_id']} → {v['team_b_wins']} galibiyet. "
        f"Goller: {v['team_a_id']} {v['team_a_goals']} - {v['team_b_goals']} {v['team_b_id']}.\n\n"
        "Bu head-to-head özetini kısa yorumla."
    )


def _build_load_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    high = "evet" if v["high_load"] else "hayır"
    return (
        f"Oyuncu {a.subject_id} son penceredeki yük: "
        f"{v['matches_in_window']} maç, {v['minutes_in_window']} dk toplam, "
        f"maç başı {v['minutes_per_match']} dk, haftalık {v['minutes_per_week']} dk. "
        f"Yüksek yük eşiği aşıldı mı: {high}.\n\n"
        "Bu yük tablosunu rotasyon açısından kısa yorumla."
    )


_BUILDERS: dict[str, Callable[[dict[str, Any], AuditRecord], str]] = {
    "engine.form": _build_form_prompt,
    "engine.rating": _build_rating_prompt,
    "engine.opponent": _build_h2h_prompt,
    "engine.load": _build_load_prompt,
}


def build_user_prompt(result: EngineResult) -> str:
    """EngineResult'ı engine'e özgü Türkçe prompt'a çevirir.

    Bilinmeyen engine için jenerik JSON fallback'i (forward-compat — yeni
    engine eklendiğinde bile sistem patlamadan çalışmaya devam eder).
    """
    builder = _BUILDERS.get(result.audit.engine)
    if builder is None:
        body = json.dumps(
            {
                "engine": result.audit.engine,
                "metric": result.audit.metric,
                "value": result.audit.value,
                "formula": result.audit.formula,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"Motor çıktısı (JSON, bilinmeyen engine):\n{body}\n\nKısa yorumla."
    return builder(result.audit.value, result.audit)


def build_match_preview_prompt(
    home_form: EngineResult,
    away_form: EngineResult,
    h2h: EngineResult,
    *,
    home_team_id: int,
    away_team_id: int,
    kickoff_iso: str,
) -> str:
    """Maç öncesi brief için — üç engine çıktısını tek prompt'a sentezler."""
    hv = home_form.audit.value
    av = away_form.audit.value
    hv_last = " ".join(hv["last_results"]) if hv["last_results"] else "—"
    av_last = " ".join(av["last_results"]) if av["last_results"] else "—"
    hh = h2h.audit.value

    h2h_line = (
        f"Geçmiş karşılaşma yok."
        if hh["matches_played"] == 0
        else (
            f"Geçmiş {hh['matches_played']} karşılaşma: "
            f"ev sahibi ({home_team_id}) {hh['team_a_wins']}G, "
            f"{hh['draws']}B, deplasman ({away_team_id}) {hh['team_b_wins']}G; "
            f"goller {hh['team_a_goals']}-{hh['team_b_goals']}."
        )
    )

    return (
        f"Maç ön bakışı — kickoff {kickoff_iso}\n\n"
        f"EV SAHİBİ (takım {home_team_id}) son {hv['matches_played']} maç: "
        f"{hv['wins']}G-{hv['draws']}B-{hv['losses']}M, "
        f"goller {hv['goals_for']}-{hv['goals_against']} (averaj {hv['goal_diff']:+d}), "
        f"ppg {hv['points_per_game']}, ev: {hv['home_wins']}G-{hv['home_draws']}B-{hv['home_losses']}M, "
        f"son: {hv_last}.\n\n"
        f"DEPLASMAN (takım {away_team_id}) son {av['matches_played']} maç: "
        f"{av['wins']}G-{av['draws']}B-{av['losses']}M, "
        f"goller {av['goals_for']}-{av['goals_against']} (averaj {av['goal_diff']:+d}), "
        f"ppg {av['points_per_game']}, dep: {av['away_wins']}G-{av['away_draws']}B-{av['away_losses']}M, "
        f"son: {av_last}.\n\n"
        f"{h2h_line}\n\n"
        "Bu sayılara dayanarak teknik ekibe 3-5 cümlelik maç öncesi brief ver: kim ne yönde "
        "avantajlı, dikkat edilecek pattern var mı, hangi tarafta risk."
    )


def stub_response(result: EngineResult) -> str:
    return (
        f"[stub:{result.audit.engine} v{result.audit.engine_version}] "
        f"{result.audit.subject_type}:{result.audit.subject_id} "
        f"{result.audit.metric} — ANTHROPIC_API_KEY tanımlı değil."
    )


def stub_match_preview(home_team_id: int, away_team_id: int) -> str:
    return (
        f"[stub:match_preview] {home_team_id} vs {away_team_id} — "
        "ANTHROPIC_API_KEY tanımlı değil."
    )
