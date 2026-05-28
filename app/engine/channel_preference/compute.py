"""Channel Preference — sol/orta/sağ koridor tercihi.

Tanım: takımın hücum üçündeki paslarının y-koordinat dağılımı.
- left channel:   y < 33
- central channel: 33 ≤ y ≤ 67
- right channel:  y > 67

Salah-Robertson vs Bayern (kanat-merkezli takımlar) için sayısal cevap.

Saf hesap. PassEvent → ChannelPreferenceReport.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.channel_preference"
ENGINE_VERSION = "1"

# Channel sınırları (y ekseni 0-100)
LEFT_Y_MAX = 33.3
RIGHT_Y_MIN = 66.7

# Hücum üçü x sınırı (sadece son üçteki pasları say)
ATTACKING_THIRD_X_MIN = 66.7


@dataclass(frozen=True)
class ChannelPreferenceReport:
    team_external_id: int
    matches_analyzed: int
    total_attacking_passes: int
    left_passes: int
    central_passes: int
    right_passes: int
    left_share: float          # %
    central_share: float
    right_share: float
    dominant_channel: str      # "left" | "central" | "right" | "balanced"


def _classify_channel(y: float) -> str:
    if y < LEFT_Y_MAX:
        return "left"
    if y > RIGHT_Y_MIN:
        return "right"
    return "central"


def _dominant(left: float, central: float, right: float) -> str:
    """En yüksek share %40+ ise o kanal dominant; aksi → balanced."""
    if max(left, central, right) < 0.40:
        return "balanced"
    if left >= central and left >= right:
        return "left"
    if right >= central and right >= left:
        return "right"
    return "central"


def compute_channel_preference(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[ChannelPreferenceReport]:
    counts = {"left": 0, "central": 0, "right": 0}
    total = 0
    for p in all_passes:
        if p.team_external_id != team_external_id:
            continue
        if p.start_x < ATTACKING_THIRD_X_MIN:
            continue
        counts[_classify_channel(p.start_y)] += 1
        total += 1

    if total == 0:
        report = ChannelPreferenceReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            total_attacking_passes=0,
            left_passes=0, central_passes=0, right_passes=0,
            left_share=0.0, central_share=0.0, right_share=0.0,
            dominant_channel="insufficient_data",
        )
    else:
        ls = counts["left"] / total
        cs = counts["central"] / total
        rs = counts["right"] / total
        report = ChannelPreferenceReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            total_attacking_passes=total,
            left_passes=counts["left"],
            central_passes=counts["central"],
            right_passes=counts["right"],
            left_share=round(ls, 3),
            central_share=round(cs, 3),
            right_share=round(rs, 3),
            dominant_channel=_dominant(ls, cs, rs),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="channel_preference",
        value={
            "left_share": report.left_share,
            "central_share": report.central_share,
            "right_share": report.right_share,
            "dominant_channel": report.dominant_channel,
            "total_attacking_passes": report.total_attacking_passes,
        },
        inputs={
            "left_y_max": LEFT_Y_MAX,
            "right_y_min": RIGHT_Y_MIN,
            "attacking_third_x_min": ATTACKING_THIRD_X_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="count passes in attacking third by y-band; share per channel",
    )
    return EngineResult(value=report, audit=audit)
