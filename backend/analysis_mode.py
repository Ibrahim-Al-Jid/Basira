"""Run mode of a scan: rules only, agents only, or hybrid. One place decides what actually runs."""
from typing import Literal

AnalysisMode = Literal["rules", "agents", "hybrid"]
MODES = ("rules", "agents", "hybrid")
DEFAULT_MODE = "hybrid"
# The model-backed agent path (docs/ARCHITECTURE-agents.md, phase P4) is not built yet.
# Flip this when it ships; until then the effective mode of every scan is rules.
AGENT_PATH_AVAILABLE = False


class ModeUnavailable(ValueError):
    pass


def resolve_mode(requested=None):
    """Return the contract fields for a scan: what was asked, what runs, and why they differ."""
    asked = requested or DEFAULT_MODE
    if asked not in MODES:
        raise ModeUnavailable("وضع التحليل غير معروف.")
    if asked == "rules" or AGENT_PATH_AVAILABLE:
        return {"analysis_mode": asked, "mode_effective": asked, "fallback_reason": None}
    if asked == "agents":
        # An agents scan must not quietly become a rules scan: the result would not be what was asked for.
        raise ModeUnavailable("وضع الوكلاء غير متاح بعد. استخدم الوضع الهجين أو وضع القواعد.")
    return {"analysis_mode": asked, "mode_effective": "rules", "fallback_reason": "agent_path_unavailable"}
