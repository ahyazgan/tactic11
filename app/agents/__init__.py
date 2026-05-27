from app.agents.base import Agent, AgentResult
from app.agents.injury_load import InjuryLoadAgent
from app.agents.mega_match import MegaMatchAgent
from app.agents.opponent_scout import NoUpcomingMatch, OpponentScoutAgent
from app.agents.post_match_report import PostMatchReportAgent
from app.agents.pre_match_report import PreMatchReportAgent
from app.agents.store import save_agent_output
from app.agents.weekly_digest import WeeklyDigestAgent

__all__ = [
    "Agent",
    "AgentResult",
    "InjuryLoadAgent",
    "MegaMatchAgent",
    "NoUpcomingMatch",
    "OpponentScoutAgent",
    "PostMatchReportAgent",
    "PreMatchReportAgent",
    "WeeklyDigestAgent",
    "save_agent_output",
]
