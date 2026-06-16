"""İki takım kıyaslama sentezi — preview brief'ı için engine seviyesi malzeme.

Üst katman `engine.form` (iki kez) + `engine.opponent` çağırır, sonuçları bu
fonksiyona verir. Burası saf hesap: deltalar, ev avantajı katsayısı,
H2H baskınlığı, momentum farkı.

AI prompt'u sayıları doğrudan yorumlayabilir; engine'in kendisi karar vermez.
"Bence X kazanır" çıkmaz — sadece "X'in form_delta'sı +0.8, momentum_delta
+1.2" gibi gözlenebilir sayılar üretir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.engine.confidence import score_confidence
from app.engine.form import FormReport
from app.engine.opponent import HeadToHead

ENGINE_NAME = "engine.matchup"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class MatchupReport:
    home_team_id: int
    away_team_id: int

    # Form farkları (home perspektifinden); pozitif=ev sahibi avantajlı
    form_delta_ppg: float  # home.ppg - away.ppg
    form_delta_goal_diff: float  # home (gf-ga)/match - away (gf-ga)/match
    momentum_delta: float  # home.momentum - away.momentum
    clean_sheets_delta: int  # home.clean_sheets - away.clean_sheets

    # Ev sahibi avantajı sinyali — son maçlarda evde ne kadar etkili
    home_advantage_factor: float  # home_team home_wins / home_played (0..1)

    # H2H baskınlığı (-100..+100). pozitif=ev sahibi (team_a) baskın
    h2h_dominance: float  # 100*(a_wins-b_wins)/matches_played; 0 maç=0

    # Yön sinyali — "kim avantajlı" özet skor (-N..+N); sadece ipucu
    advantage_score: float


def compute_matchup(
    home_form: FormReport,
    away_form: FormReport,
    h2h: HeadToHead,
    *,
    home_team_id: int,
    away_team_id: int,
) -> EngineResult[MatchupReport]:
    """İki form raporunu + H2H'i alıp bir kıyas raporu üretir."""
    home_gd_per_match = (
        home_form.goal_diff / home_form.matches_played if home_form.matches_played else 0.0
    )
    away_gd_per_match = (
        away_form.goal_diff / away_form.matches_played if away_form.matches_played else 0.0
    )
    form_delta_ppg = home_form.points_per_game - away_form.points_per_game
    form_delta_gd = home_gd_per_match - away_gd_per_match
    momentum_delta = home_form.momentum - away_form.momentum
    cs_delta = home_form.clean_sheets - away_form.clean_sheets

    home_played_at_home = home_form.home_wins + home_form.home_draws + home_form.home_losses
    home_advantage = (
        home_form.home_wins / home_played_at_home if home_played_at_home else 0.0
    )

    if h2h.matches_played > 0:
        # Not: HeadToHead'in team_a = burada home_team_id ise pozitif ev lehine,
        # değilse işareti çevirmek gerek.
        a_is_home = h2h.team_a_id == home_team_id
        a_dominance = 100 * (h2h.team_a_wins - h2h.team_b_wins) / h2h.matches_played
        h2h_dominance = a_dominance if a_is_home else -a_dominance
    else:
        h2h_dominance = 0.0

    # Yön ipucu — bileşenlerin basit toplam skoru. Sayısal kompozit; "tahmin"
    # değil "şu yöne işaret" kalitesi taşır.
    advantage_score = (
        form_delta_ppg * 1.0
        + form_delta_gd * 0.5
        + momentum_delta * 0.5
        + home_advantage * 1.0
        + h2h_dominance / 100.0
    )

    report = MatchupReport(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        form_delta_ppg=round(form_delta_ppg, 3),
        form_delta_goal_diff=round(form_delta_gd, 3),
        momentum_delta=round(momentum_delta, 3),
        clean_sheets_delta=cs_delta,
        home_advantage_factor=round(home_advantage, 3),
        h2h_dominance=round(h2h_dominance, 2),
        advantage_score=round(advantage_score, 3),
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team_pair",
        subject_id=home_team_id,
        metric="matchup_report",
        value=asdict(report),
        inputs={
            "away_team_id": away_team_id,
            "home_form_matches": home_form.matches_played,
            "away_form_matches": away_form.matches_played,
            "h2h_matches": h2h.matches_played,
        },
        formula=(
            "form_delta = home - away (ppg, gd/match, momentum); "
            "home_advantage = home_wins/home_played; "
            "h2h_dominance = 100*(a_wins-b_wins)/N (ev perspektifine çevrilmiş); "
            "advantage_score = ppg*1 + gd*0.5 + mom*0.5 + home_adv*1 + h2h_dom/100"
        ),
    )
    # Güven: sample_size = iki formun min maç sayısı; magnitude = |advantage_score|/3.
    conf = score_confidence(
        sample_size=min(home_form.matches_played, away_form.matches_played),
        magnitude=min(1.0, abs(advantage_score) / 3.0),
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
