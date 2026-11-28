"""Run mode of a scan: rules only, agents only, or hybrid. One place decides what actually runs."""
import os
from typing import Literal

AnalysisMode = Literal["rules", "agents", "hybrid"]
MODES = ("rules", "agents", "hybrid")
DEFAULT_MODE = "hybrid"
# The Hunter reads a repository upload, so other input kinds always run the rules.
AGENT_KINDS = ("repository",)
FLAG = "BASIRA_AGENT_LOOP"


def agent_loop_enabled():
    """The one reader of the flag. This module is a low layer (contracts imports it), so it imports nothing local."""
    return os.environ.get(FLAG) == "1"


class ModeUnavailable(ValueError):
    pass


def resolve_mode(requested=None, *, has_model=False, kind="repository"):
    """Return the contract fields for a scan: what was asked, what runs, and why they differ.

    The agent path needs the BASIRA_AGENT_LOOP flag, a model connection on the scan and a repository input."""
    asked = requested or DEFAULT_MODE
    if asked not in MODES:
        raise ModeUnavailable("وضع التحليل غير معروف.")
    if asked == "rules" or (agent_loop_enabled() and has_model and kind in AGENT_KINDS):
        return {"analysis_mode": asked, "mode_effective": asked, "fallback_reason": None}
    if asked == "agents":
        # An agents scan must not quietly become a rules scan: the result would not be what was asked for.
        raise ModeUnavailable("وضع الوكلاء غير متاح لهذا الفحص. استخدم الوضع الهجين أو وضع القواعد.")
    return {"analysis_mode": asked, "mode_effective": "rules", "fallback_reason": "agent_path_unavailable"}
