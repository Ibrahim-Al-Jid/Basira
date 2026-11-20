"""Bounded, source-only review graph. The model sees counts and structural flags."""
import asyncio
import json
import re
import time
from collections import Counter
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .rules import RULES, SourceIndex


SAMPLE = """<!doctype html>
<html lang="en">
<head>
  <title>Demo storefront</title>
  <script src="http://assets.example.test/store.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/demo-store@1.0.0/index.js"></script>
</head>
<body>
  <form action="http://checkout.example.test/order" method="post">
    <button>Place order</button>
  </form>
</body>
</html>"""

EXPECTED = {("http-script", 5), ("cdn-integrity", 6), ("http-form", 9)}


class ReviewState(TypedDict, total=False):
    layout: str
    groups: list[str]
    findings: list[dict]
    summaries: dict
    summary_source: str


class GraphError(ValueError):
    """Safe for clients. Never include provider exception bodies or model outputs."""


def exact_list(value, expected):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return False
    return len(value) == len(expected) and set(value) == set(expected)


def render_summaries(findings, coverage, priority=None):
    checked = sum(item["status"] in ("matched", "clear") for item in coverage)
    if not checked:
        return {
            "summary_en": "No registered check applied to the supplied HTML excerpt.",
            "summary_ar": "لم تنطبق أي قاعدة مسجّلة على مقتطف HTML المقدّم.",
        }
    matches = Counter(item["rule"] for item in findings)
    if not matches:
        return {
            "summary_en": f"{checked} checks applied to this HTML excerpt and found no matching evidence.",
            "summary_ar": f"انطبقت {checked} فحوصات على مقتطف HTML ولم ترصد دليلًا مطابقًا.",
        }
    order = priority if priority is not None else sorted(matches, key=lambda rule: (
        ("high", "medium", "low").index(RULES[rule].severity), rule,
    ))
    details_en = " ".join(f"{RULES[r].title} ({matches[r]}). {RULES[r].remediation}" for r in order)
    details_ar = " ".join(f"{RULES[r].title_ar} ({matches[r]}). {RULES[r].remediation_ar}" for r in order)
    return {
        "summary_en": f"Found {len(matches)} issue types at {len(findings)} matching locations in the supplied HTML. {details_en}",
        "summary_ar": f"رُصدت {len(matches)} أنواع من الملاحظات في {len(findings)} مواضع في HTML المقدّم. {details_ar}",
    }


async def run_graph(source, model, key, emit, previous=None, *, _llm=None):
    started = time.monotonic()
    if not isinstance(source, str) or not source.strip() or len(source) > 250000:
        raise GraphError("Submit an HTML excerpt of 1–250,000 characters.")
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    try:
        index = SourceIndex(source)
    except (ValueError, AssertionError):
        raise GraphError("The HTML excerpt could not be parsed.") from None
    if not index.tags:
        raise GraphError("The source must contain an HTML element.")
    counts = {g: sum(hist.values()) for g, hist in index.profiles.items()}
    coverage = index.coverage()
    evidence_counts = Counter(f["rule"] for f in index.evidence)
    enabled = _llm is not None or bool(key and model)
    llm = _llm
    if llm is None and enabled:
        try:
            llm = ChatOpenAI(
                api_key=key, model=model, base_url="https://openrouter.ai/api/v1",
                timeout=20, max_retries=0, max_tokens=750, use_responses_api=False,
            )
        except Exception:
            # A provider client failure only disables the optional enrichment.
            pass
    call_count = 0
    fallback_nodes = set()

    async def ask(role, instruction, data):
        nonlocal call_count
        if llm is None:
            return {}
        call_count += 1
        try:
            async with asyncio.timeout(20):
                message = await llm.ainvoke([
                    ("system", f"You are the {role} agent for a passive HTML configuration review. "
                               "Respond only with the requested JSON object. " + instruction),
                    ("user", json.dumps(data, ensure_ascii=False)),
                ])
        except Exception:
            return {}
        content = getattr(message, "content", None)
        if isinstance(content, list):
            content = "".join(
                block["text"] for block in content
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
            )
        if not isinstance(content, str) or len(content) > 20_000:
            return {}
        try:
            raw = re.sub(r"^\s*`{3}(?:json)?\s*|\s*`{3}\s*$", "", content, flags=re.I)
            result = json.loads(raw)
        except (ValueError, RecursionError):
            return {}
        return result if isinstance(result, dict) else {}

    def decision_source(node, accepted):
        if accepted:
            return "model"
        if enabled:
            fallback_nodes.add(node)
        return "system"

    async def event(node, status, parents, detail, detail_en, source="system"):
        await emit(dict(node=node, role=node.split(":")[0], status=status, parents=parents,
                        detail=detail, detail_en=detail_en, source=source))

    async def orchestrate(state):
        await event("orchestrator", "start", [], "تحديد مسار المراجعة", "Selecting a review route")
        memory = {}
        prior = previous.get("findingsCount") if isinstance(previous, dict) else None
        if type(prior) is int and 0 <= prior <= 250000:
            memory["prior_findings_count"] = prior
        result = await ask("orchestrator", 'Choose {"layout":"split"} for independent script and form work, '
                           'or {"layout":"combined"} for a single document review.', {"elements": counts, "memory": memory})
        layout = result.get("layout")
        accepted = layout in ("split", "combined")
        if not accepted:
            layout = "split" if all(counts.values()) else "combined"
        detail = "مراجعة السكربتات والنماذج في فروع مستقلة" if layout == "split" else "مراجعة المستند في فرع واحد"
        detail_en = "Separate script and form branches" if layout == "split" else "One document branch"
        await event("orchestrator", "done", [], detail, detail_en, decision_source("orchestrator", accepted))
        return {"layout": layout}

    async def plan(state):
        await event("planning", "start", ["orchestrator"], "توزيع فحوصات المصدر", "Organizing source checks")
        available = [g for g, n in counts.items() if n] if state["layout"] == "split" else []
        available = available or ["document"]
        result = await ask("planning", 'Order the supplied groups by review priority. Return {"groups":[...]} '
                           'using every supplied group exactly once.', {"groups": available, "elements": counts})
        groups = result.get("groups")
        accepted = exact_list(groups, available)
        if not accepted:
            groups = available
        await event("planning", "done", ["orchestrator"], f"تجهيز {len(groups)} مهام تحليل",
                    f"Prepared {len(groups)} analysis tasks", decision_source("planning", accepted))
        return {"groups": groups}

    def fanout(state):
        return [Send("analyze", {"group": group}) for group in state["groups"]]

    async def analyze(task):
        group = task["group"]
        node = "analysis:" + group
        await event(node, "start", ["planning"], "فحص خصائص العناصر", "Checking element attributes")
        profiles = []
        for name, histogram in index.profiles.items():
            if group not in (name, "document"):
                continue
            for (http, cdn, integrity), count in histogram.items():
                profiles.append(dict(group=name, explicit_http=http, recognized_cdn=cdn,
                                     integrity_present=integrity, count=count))
        result = await ask("analysis", 'Identify matching rule IDs from structural flags. http-script: scripts with explicit_http. '
                           'http-form: forms with explicit_http. cdn-integrity: scripts with recognized_cdn and no integrity_present. '
                           'Return {"rules":[...]} containing unique matching IDs or an empty list.', {"profiles": profiles})
        rules = [rule_id for rule_id in evidence_counts if group in ("document", RULES[rule_id].group)]
        accepted = exact_list(result.get("rules"), rules)
        await event(node, "done", ["planning"], f"مطابقة {len(rules)} أنواع ملاحظات",
                    f"Matched {len(rules)} finding types", decision_source(node, accepted))
        return {}

    async def validate(state):
        parents = ["analysis:" + g for g in state["groups"]]
        await event("validation", "start", parents, "التحقق من كل دليل مطابق للقواعد",
                    "Verifying all matching evidence")
        verified = sorted(evidence_counts)
        result = await ask("validation", 'Review the locally observed rule IDs. Return {"confirmed":[...]} '
                           'with every supported rule ID.', {"nominated": verified, "local_matches": dict(evidence_counts)})
        decision_source("validation", exact_list(result.get("confirmed"), verified))
        findings = index.evidence
        await event("validation", "done", parents, f"توثيق {len(findings)} ملاحظات بالدليل المحلي",
                    f"Verified {len(findings)} occurrences against local evidence")
        return {"findings": findings}

    async def report(state):
        await event("reporting", "start", ["validation"], "كتابة التقرير باللغتين",
                    "Preparing the bilingual report")
        frequencies = Counter(f["rule"] for f in state["findings"])
        result = await ask("reporting", 'Order the supplied finding rule IDs by remediation priority. '
                           'Return {"priority":[...]} with each supplied ID exactly once and no other IDs.',
                           {"scope": "submitted HTML script/form configuration", "coverage": coverage,
                            "findings": [dict(rule=r, count=n, title=RULES[r].title, remediation=RULES[r].remediation)
                                         for r, n in frequencies.items()]})
        priority = result.get("priority")
        accepted = exact_list(priority, frequencies)
        source = decision_source("reporting", accepted)
        summaries = render_summaries(state["findings"], coverage, priority if accepted else None)
        await event("reporting", "done", ["validation"], "اكتمل التقرير العربي والإنجليزي",
                    "Arabic and English reports are ready", source)
        return {"summaries": summaries, "summary_source": source}

    graph = StateGraph(ReviewState)
    for name, fn in (("orchestrate", orchestrate), ("plan", plan), ("analyze", analyze),
                     ("validate", validate), ("report", report)):
        graph.add_node(name, fn)
    graph.add_edge(START, "orchestrate")
    graph.add_edge("orchestrate", "plan")
    graph.add_conditional_edges("plan", fanout, ["analyze"])
    graph.add_edge("analyze", "validate")
    graph.add_edge("validate", "report")
    graph.add_edge("report", END)
    try:
        state = await asyncio.wait_for(graph.compile().ainvoke({},
                                              config={"recursion_limit": 10, "max_concurrency": 2}), 210)
    except TimeoutError:
        raise GraphError("The review exceeded its time budget. Retry or choose another model.") from None
    findings = state["findings"]
    benchmark = None
    if source == SAMPLE:
        matched = len({(f["rule"], f["line"]) for f in findings} & EXPECTED)
        unexpected = len(findings) - matched
        benchmark = dict(matched=matched, expected=len(EXPECTED), unexpected=unexpected,
                         passed=matched == len(EXPECTED) and unexpected == 0)
    enrichment = "disabled"
    if enabled:
        enrichment = "fallback" if fallback_nodes else "model"
    return dict(findings=findings, **state["summaries"], model=model, coverage=coverage,
                enrichment=enrichment, summary_source=state["summary_source"], metrics=dict(
                    checksRun=sum(item["status"] in ("matched", "clear") for item in coverage),
                    findingsCount=len(findings), validatedCount=len(findings),
                    durationMs=round((time.monotonic() - started) * 1000), modelCalls=call_count, benchmark=benchmark))
