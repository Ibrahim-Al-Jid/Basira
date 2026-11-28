import re
from pathlib import Path
from typing import get_args

from .agent_roles import AGENT_ROLES, DISPLAY, ROLE_IDS
from .scan_contracts import AgentRole, ROLE_TOOLS

ROOT = Path(__file__).resolve().parents[1]
RETIRED = ("Coordinator", "Orchestrator", "Planner", "Reporter", "المنسّق", "المخطّط", "كاتب التقرير")


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_stored_ids_match_the_contract_and_the_tool_allow_lists():
    assert ROLE_IDS == get_args(AgentRole) == tuple(ROLE_TOOLS)


def test_display_names_are_unique_and_do_not_reuse_a_membership_role():
    names = [role[1] for role in AGENT_ROLES] + [role[2] for role in AGENT_ROLES]
    assert len(set(names)) == len(names)
    assert not {"Analyst", "Viewer", "Owner", "Admin"} & set(names)


def test_the_interface_shows_the_registered_names():
    lanes, data = text("frontend/src/AgentLanes.jsx"), text("frontend/src/data.js")
    for role, english, arabic, *_ in AGENT_ROLES:
        assert f'["{role}", "{arabic}", "{english}"' in lanes
        assert f'"{arabic}",\n    "{english}",' in data


def test_docs_use_the_registered_names_and_no_retired_ones():
    for path in ("README.md", "docs/ARCHITECTURE-agents.md", "docs/PLAN.md", "docs/DEMO.md"):
        body = text(path)
        for _, english, *_ in AGENT_ROLES:
            assert english in body, (path, english)
    for path in ("README.md", "docs/DEMO.md", "docs/PLAN.md", "docs/thesis/architecture_and_data.md",
                 "docs/thesis/problem_and_scope.md", "docs/RELEASE.md", "docs/ARCHITECTURE.md",
                 "frontend/src/AgentLanes.jsx", "frontend/src/data.js", "frontend/src/Dialogs.jsx", "frontend/src/main.jsx"):
        body = text(path)
        assert not [word for word in RETIRED if re.search(rf"(?<![A-Za-z]){word}(?![A-Za-z])", body)], path


def test_display_has_both_languages_for_every_role():
    assert all(DISPLAY[role]["en"] and DISPLAY[role]["ar"] and DISPLAY[role]["job_en"] for role in ROLE_IDS)
