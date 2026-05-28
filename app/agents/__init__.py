from app.agents.base import Agent, AgentResult
from app.agents.game_plan import GamePlanAgent
from app.agents.halftime_analysis import HalftimeAnalysisAgent
from app.agents.injury_load import InjuryLoadAgent
from app.agents.lineup_recommendation import LineupRecommendationAgent
from app.agents.media_brief import MediaBriefAgent
from app.agents.mega_match import MegaMatchAgent
from app.agents.opponent_scout import NoUpcomingMatch, OpponentScoutAgent
from app.agents.player_feedback import PlayerFeedbackAgent
from app.agents.post_match_report import PostMatchReportAgent
from app.agents.pre_match_report import PreMatchReportAgent
from app.agents.scout_watchlist_digest import ScoutWatchlistDigestAgent
from app.agents.store import save_agent_output
from app.agents.substitution_advice import SubstitutionAdviceAgent
from app.agents.tactical_adjustment import TacticalAdjustmentAgent
from app.agents.training_plan import TrainingPlanAgent
from app.agents.weekly_digest import WeeklyDigestAgent

__all__ = [
    "Agent",
    "AgentResult",
    "GamePlanAgent",
    "HalftimeAnalysisAgent",
    "InjuryLoadAgent",
    "LineupRecommendationAgent",
    "MediaBriefAgent",
    "MegaMatchAgent",
    "NoUpcomingMatch",
    "OpponentScoutAgent",
    "PlayerFeedbackAgent",
    "PostMatchReportAgent",
    "PreMatchReportAgent",
    "ScoutWatchlistDigestAgent",
    "SubstitutionAdviceAgent",
    "TacticalAdjustmentAgent",
    "TrainingPlanAgent",
    "WeeklyDigestAgent",
    "save_agent_output",
]
