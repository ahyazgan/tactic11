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
    # v2/v3 alanlarına geriye uyumlu erişim — eski cache satırı için fallback.
    clean = v.get("clean_sheets", 0)
    gpm = v.get("goals_for_per_match", 0.0)
    cpm = v.get("goals_against_per_match", 0.0)
    momentum = v.get("momentum", 0.0)
    streak = v.get("current_streak", 0)
    streak_text = (
        f"{streak} galibiyet serisi" if streak > 0
        else f"{abs(streak)} mağlubiyet serisi" if streak < 0
        else "seride yok (son maç beraberlik veya seri kırıldı)"
    )
    dominant = v.get("dominant_wins", 0)
    close_l = v.get("close_losses", 0)
    fts = v.get("failed_to_score", 0)
    scoring_rate = v.get("scoring_rate", 0.0)
    return (
        f"Takım {a.subject_id} son {v['matches_played']} tamamlanmış maçta: "
        f"{v['wins']} galibiyet, {v['draws']} beraberlik, {v['losses']} mağlubiyet. "
        f"Goller {v['goals_for']}-{v['goals_against']} "
        f"(averaj {v['goal_diff']:+d}; maç başı atılan {gpm}, yenilen {cpm}). "
        f"Maç başı puan: {v['points_per_game']}. "
        f"Clean sheet: {clean}. "
        f"Ev: {v['home_wins']}G-{v['home_draws']}B-{v['home_losses']}M, "
        f"deplasman: {v['away_wins']}G-{v['away_draws']}B-{v['away_losses']}M. "
        f"Son sonuçlar (yeniden eskiye): {last}. "
        f"Momentum: {momentum:+} (yakın geçmiş ppg ile eskinin farkı). "
        f"Şu an: {streak_text}. "
        f"Galibiyet kalitesi: {dominant} dominant (2+ farkla), "
        f"{close_l} dar mağlubiyet (1 farkla). "
        f"Gol atamadığı maç: {fts} (gol attığı oran %{int(scoring_rate * 100)}).\n\n"
        "Bu form raporunu kısa bir yorumla özetle; "
        "yön/momentum, gol üretimi, savunma örüntüsü varsa not düş."
    )


def _build_rating_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    # v2 alanları geriye uyumlu erişim (eski cache satırı için fallback)
    home_r = v.get("home_rating")
    away_r = v.get("away_rating")
    home_n = v.get("home_matches", 0)
    away_n = v.get("away_matches", 0)
    split_line = ""
    if home_r is not None and away_r is not None and (home_n > 0 or away_n > 0):
        split_line = (
            f" Ev rating'i {home_r} ({home_n} maç), "
            f"dep rating'i {away_r} ({away_n} maç)."
        )
    return (
        f"Takım {a.subject_id} rating raporu (son {v['matches_considered']} maç): "
        f"rating={v['rating']}, ppg={v['points_per_game']}, "
        f"maç başı gol farkı={v['goal_diff_per_match']:+}.{split_line} "
        f"Formül: ppg × ağırlık + gd_per_match × ağırlık. "
        f"(Detay: {a.formula})\n\n"
        "Rating'in nereden geldiğini ve takımın bu sayılarla ne durumda olduğunu özetle; "
        "ev-dep farkı belirginse not düş."
    )


def _build_h2h_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    if v["matches_played"] == 0:
        return (
            f"Takım {v['team_a_id']} ile {v['team_b_id']} arasında tamamlanmış maç yok. "
            "Bunu açıkça söyle, veri yetersiz."
        )
    extras = ""
    a_clean = v.get("team_a_clean_sheets")
    b_clean = v.get("team_b_clean_sheets")
    a_home_w = v.get("team_a_home_wins")
    a_away_w = v.get("team_a_away_wins")
    last_kickoff = v.get("last_meeting_kickoff")
    if a_clean is not None and b_clean is not None:
        extras += (
            f" {v['team_a_id']} clean sheet: {a_clean}, {v['team_b_id']} clean sheet: {b_clean}."
        )
    if a_home_w is not None and a_away_w is not None and v["team_a_wins"] > 0:
        extras += (
            f" {v['team_a_id']} galibiyetlerinin {a_home_w}'i evde, {a_away_w}'i deplasmanda."
        )
    if last_kickoff:
        extras += f" Son karşılaşma: {last_kickoff} ({v.get('last_meeting_result', '?')})."
    return (
        f"Takım {v['team_a_id']} ile {v['team_b_id']} arasında {v['matches_played']} maç: "
        f"{v['team_a_id']} → {v['team_a_wins']} galibiyet, {v['draws']} beraberlik, "
        f"{v['team_b_id']} → {v['team_b_wins']} galibiyet."
        f"{extras}"
        f" "
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


def _build_schedule_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    if v["upcoming_count"] == 0:
        return (
            f"Takım {a.subject_id} için ufuktaki maç yok. "
            "Bunu söyle, rotasyon kararına gerek yok."
        )
    next_3 = ", ".join(v.get("next_kickoffs", [])[:3]) or "—"
    dense = "evet" if v.get("dense_schedule") else "hayır"
    days = v.get("days_until_next_match")
    return (
        f"Takım {a.subject_id} fikstür yoğunluğu: önümüzdeki ufukta "
        f"{v['upcoming_count']} maç. "
        f"Önümüzdeki 7 günde {v['matches_next_7d']}, 14 günde {v['matches_next_14d']} maç. "
        f"İlk maça kalan: {days} gün. "
        f"En yakın 3 kickoff: {next_3}. "
        f"Yoğun fikstür uyarısı: {dense}.\n\n"
        "Bu yoğunluğu rotasyon/dinlenme açısından kısa yorumla."
    )


def _build_predict_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    home_id = v["home_team_id"]
    away_id = v["away_team_id"]
    lam_h = v["expected_home_goals"]
    lam_a = v["expected_away_goals"]
    pH = v["prob_home_win"]
    pD = v["prob_draw"]
    pA = v["prob_away_win"]
    score = v["most_likely_score"]
    score_p = v["most_likely_score_prob"]
    low = v.get("low_confidence", False)
    sample = v.get("sample_size", 0)
    confidence_note = (
        f" UYARI: örneklem küçük ({sample} maç), tahmin güveni DÜŞÜK."
        if low else ""
    )
    rho = v.get("rho_used", 0.0)
    model_note = (
        "Poisson + Dixon-Coles (düşük-skor düzeltmeli)" if rho != 0.0 else "saf Poisson"
    )
    return (
        f"Maç tahmini ({model_note}) — ev {home_id} vs deplasman {away_id}. "
        f"Beklenen goller: ev {lam_h}, dep {lam_a}. "
        f"1X2 olasılıkları: ev galibiyet %{int(pH * 100)}, "
        f"beraberlik %{int(pD * 100)}, dep galibiyet %{int(pA * 100)}. "
        f"En olası skor: {score[0]}-{score[1]} (P=%{score_p * 100:.1f}).{confidence_note}\n\n"
        "Bu sayıları yorumla; en olası ihtimal hangisi, fark ne kadar belirgin? "
        "Küçük örneklemde gürültülü olabilir. "
        "'Bu skor olur' deme — 'sayılara göre şu yöne işaret' de."
    )


def _build_matchup_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    dom = v.get("h2h_dominance", 0.0)
    if dom > 0:
        dom_text = f"{v['home_team_id']} {abs(dom):.0f}% baskın"
    elif dom < 0:
        dom_text = f"{v['away_team_id']} {abs(dom):.0f}% baskın"
    else:
        dom_text = "dengeli ya da veri yok"
    return (
        f"Maç kıyas raporu — ev sahibi {v['home_team_id']} vs deplasman {v['away_team_id']}. "
        f"Form farkı (ev perspektifi): ppg {v['form_delta_ppg']:+}, "
        f"gd/maç {v['form_delta_goal_diff']:+}, momentum {v['momentum_delta']:+}, "
        f"clean sheet farkı {v['clean_sheets_delta']:+d}. "
        f"Ev sahibi sahasında: galibiyet oranı %{int(v['home_advantage_factor'] * 100)}. "
        f"H2H baskınlığı: {dom_text}. "
        f"Yön ipucu (advantage_score): {v['advantage_score']:+}.\n\n"
        "Bu sayılara dayanarak 2-3 cümlelik kıyas özeti — kim hangi yönde "
        "avantajlı, hangi nokta riskli. 'Kazanır' tahmini yapma."
    )


def _build_fixture_difficulty_prompt(v: dict[str, Any], a: AuditRecord) -> str:
    considered = v["matches_considered"]
    unknown = v["matches_unknown_opponent"]
    if considered == 0:
        kapsam = (
            f" (rating'i bilinen rakip yok; {unknown} maç kapsam dışı)"
            if unknown > 0 else " (ufukta maç yok)"
        )
        return (
            f"Takım {a.subject_id} fikstür zorluğu hesaplanamadı{kapsam}. "
            "Bunu söyle, veri yetersiz."
        )
    hardest_id = v["hardest_opponent_id"]
    hardest_r = v["hardest_opponent_rating"]
    easiest_id = v["easiest_opponent_id"]
    easiest_r = v["easiest_opponent_rating"]
    kapsam_uyari = (
        f" UYARI: {unknown} rakibin rating'i bilinmiyor, kapsam dışı." if unknown > 0 else ""
    )
    return (
        f"Takım {a.subject_id} önündeki fikstür zorluğu: "
        f"{considered} maç (ev {v['home_match_count']}, dep {v['away_match_count']}). "
        f"Rakip rating ortalaması {v['avg_opponent_rating']}; "
        f"zaman ağırlıklı zorluk {v['weighted_difficulty']} (yakın maç ağırlıklı). "
        f"En zor: takım {hardest_id} (rating {hardest_r}). "
        f"En kolay: takım {easiest_id} (rating {easiest_r}).{kapsam_uyari}\n\n"
        "Bu sayıları rotasyon/dinlenme açısından kısa yorumla; "
        "'önümüzdeki haftalar' (weighted) ile 'ortalama' farkına dikkat çek."
    )


_BUILDERS: dict[str, Callable[[dict[str, Any], AuditRecord], str]] = {
    "engine.form": _build_form_prompt,
    "engine.rating": _build_rating_prompt,
    "engine.opponent": _build_h2h_prompt,
    "engine.load": _build_load_prompt,
    "engine.schedule": _build_schedule_prompt,
    "engine.matchup": _build_matchup_prompt,
    "engine.predict": _build_predict_prompt,
    "engine.fixture_difficulty": _build_fixture_difficulty_prompt,
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
        "Geçmiş karşılaşma yok."
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
