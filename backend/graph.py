"""Bounded, source-only review graph. The model sees counts and structural flags."""
import asyncio
import json
import operator
import re
import time
from collections import Counter
from html.parser import HTMLParser
from typing import Annotated, TypedDict
from urllib.parse import urlsplit

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


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
CDNS = {"cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"}
RULES = {
    "http-script": ("high", "Script loaded over HTTP", "تحميل سكربت عبر HTTP",
                    "Serve this script over HTTPS.", "استخدم HTTPS لتحميل السكربت."),
    "http-form": ("medium", "Form submits over HTTP", "إرسال نموذج عبر HTTP",
                  "Change the form destination to HTTPS.", "استخدم HTTPS لوجهة إرسال النموذج."),
    "cdn-integrity": ("low", "CDN script lacks an integrity attribute", "سكربت CDN بدون بصمة سلامة",
                      "Pin the asset version and add its verified integrity digest.",
                      "ثبّت إصدار السكربت وأضف بصمة سلامة موثوقة في خاصية integrity."),
}


class SourceIndex(HTMLParser):
    CDATA_CONTENT_ELEMENTS = ("script", "style", "textarea", "title", "xmp", "iframe",
                              "noembed", "noframes", "noscript")

    def __init__(self, source):
        super().__init__()
        self.tags = 0
        self.profiles = {"scripts": Counter(), "forms": Counter()}
        self.evidence = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if tag not in ("script", "form"):
            return
        attrs = dict(reversed(attrs))
        is_script = tag == "script"
        try:
            url = urlsplit(attrs.get("src" if is_script else "action") or "")
            http, cdn = url.scheme == "http" and bool(url.hostname), url.hostname in CDNS
        except ValueError:
            http, cdn = False, False
        integrity = bool((attrs.get("integrity") or "").strip())
        group = "scripts" if is_script else "forms"
        self.profiles[group][(http, cdn, integrity)] += 1
        matches = []
        if http:
            matches.append("http-script" if is_script else "http-form")
        if is_script and cdn and not integrity:
            matches.append("cdn-integrity")
        for rule in matches:
            severity, title, title_ar, remediation, remediation_ar = RULES[rule]
            # Preserve only the attributes that prove this rule. Source URLs and
            # unrelated attributes can contain credentials or user information.
            if rule == "cdn-integrity":
                evidence = f'<script src="//{url.hostname}/…"> [integrity absent or blank]'
            else:
                attribute = "src" if is_script else "action"
                evidence = f'<{tag} {attribute}="http://…">'
            self.evidence.append(dict(rule=rule, severity=severity, line=self.getpos()[0],
                                      evidence=evidence, title=title,
                                      title_ar=title_ar, remediation=remediation, remediation_ar=remediation_ar))


class ReviewState(TypedDict, total=False):
    layout: str
    groups: list[str]
    assessments: Annotated[list[dict], operator.add]
    findings: list[dict]
    summaries: dict


class GraphError(ValueError):
    """Safe for clients. Never include provider exception bodies or model outputs."""


def known_list(value, allowed, *, complete=False):
    if (not isinstance(value, list) or not all(isinstance(i, str) and i in allowed for i in value)
            or len(value) != len(set(value)) or (complete and set(value) != set(allowed))):
        raise GraphError("The model returned an invalid review decision. Retry or choose another model.")
    return value


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
    llm = _llm if _llm is not None else ChatOpenAI(
        api_key=key, model=model, base_url="https://openrouter.ai/api/v1",
        timeout=40, max_retries=0, max_tokens=750, use_responses_api=False,
    )
    call_count = 0

    async def ask(role, instruction, data):
        nonlocal call_count
        call_count += 1
        try:
            message = await llm.ainvoke([
                ("system", f"You are the {role} agent for a passive HTML configuration review. "
                           "Respond only with the requested JSON object. " + instruction),
                ("user", json.dumps(data, ensure_ascii=False)),
            ])
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            reason = {401: "Check the API key.", 402: "Review the account balance or model tier.",
                      403: "Check model access and privacy settings.", 429: "Rate limit reached. Retry later."}
            raise GraphError(f"OpenRouter call failed in {role}. " + reason.get(status, "Retry or choose another model.")) from None
        content = message.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        try:
            raw = re.sub(r"^\s*`{3}(?:json)?\s*|\s*`{3}\s*$", "", content, flags=re.I)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
        except (TypeError, ValueError):
            raise GraphError(f"The {role} agent returned an unreadable response. Retry or choose another model.") from None
        return result

    async def event(node, status, parents, detail):
        await emit(dict(node=node, role=node.split(":")[0], status=status, parents=parents, detail=detail))

    async def orchestrate(state):
        await event("orchestrator", "start", [], "تحديد مسار المراجعة")
        memory = {}
        prior = previous.get("findingsCount") if isinstance(previous, dict) else None
        if type(prior) is int and 0 <= prior <= 250000:
            memory["prior_findings_count"] = prior
        result = await ask("orchestrator", 'Choose {"layout":"split"} for independent script and form work, '
                           'or {"layout":"combined"} for a single document review.', {"elements": counts, "memory": memory})
        layout = result.get("layout")
        if layout not in ("split", "combined"):
            raise GraphError("The orchestrator returned an unsupported route.")
        await event("orchestrator", "done", [], "تم تحديد مسار التخطيط")
        return {"layout": layout}

    async def plan(state):
        await event("planning", "start", ["orchestrator"], "توزيع فحوصات المصدر")
        available = [g for g, n in counts.items() if n] if state["layout"] == "split" else []
        available = available or ["document"]
        result = await ask("planning", 'Order the supplied groups by review priority. Return {"groups":[...]} '
                           'using every supplied group exactly once.', {"groups": available, "elements": counts})
        groups = known_list(result.get("groups"), available, complete=True)
        await event("planning", "done", ["orchestrator"], f"تجهيز {len(groups)} مهام تحليل")
        return {"groups": groups}

    def fanout(state):
        return [Send("analyze", {"group": group}) for group in state["groups"]]

    async def analyze(task):
        group = task["group"]
        node = "analysis:" + group
        await event(node, "start", ["planning"], "فحص خصائص العناصر")
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
        rules = known_list(result.get("rules"), RULES)
        await event(node, "done", ["planning"], f"ترشيح {len(rules)} أنواع ملاحظات")
        return {"assessments": [dict(group=group, rules=rules)]}

    async def validate(state):
        parents = ["analysis:" + g for g in state["groups"]]
        await event("validation", "start", parents, "مطابقة الترشيحات بالدليل المحلي")
        nominated = set()
        for assessment in state["assessments"]:
            for rule in assessment["rules"]:
                branch = "forms" if rule == "http-form" else "scripts"
                if assessment["group"] in ("document", branch):
                    nominated.add(rule)
        evidence_counts = Counter(f["rule"] for f in index.evidence)
        verified = sorted(nominated & evidence_counts.keys())
        result = await ask("validation", 'Accept only nominated rules with local matching evidence. Return {"confirmed":[...]} '
                           'with all supported nominated rule IDs.', {"nominated": sorted(nominated), "local_matches": dict(evidence_counts)})
        confirmed = known_list(result.get("confirmed"), verified)
        findings = [f for f in index.evidence if f["rule"] in confirmed]
        await event("validation", "done", parents, f"توثيق {len(findings)} ملاحظات")
        return {"findings": findings}

    async def report(state):
        await event("reporting", "start", ["validation"], "كتابة التقرير باللغتين")
        frequencies = Counter(f["rule"] for f in state["findings"])
        result = await ask("reporting", 'Write one concise executive summary in English and its Arabic translation. '
                           'Describe only the supplied validated findings, scope and remediation. Never imply the website is secure. '
                           'Return {"summary_en":"...","summary_ar":"..."}.',
                           {"scope": "submitted HTML script/form configuration", "findings": [
                               dict(rule=r, count=n, title=RULES[r][1], remediation=RULES[r][3]) for r, n in frequencies.items()]})
        summaries = {}
        for field, alphabet in (("summary_en", "[A-Za-z]"), ("summary_ar", "[\u0621-\u064a]")):
            value = result.get(field)
            if not isinstance(value, str) or not re.search(alphabet, value) or len(value) > 5000:
                raise GraphError("The reporting agent did not produce both report languages.")
            summaries[field] = value.strip()
        await event("reporting", "done", ["validation"], "اكتمل التقرير العربي والإنجليزي")
        return {"summaries": summaries}

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
        state = await asyncio.wait_for(graph.compile().ainvoke({"assessments": []},
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
    return dict(findings=findings, **state["summaries"], model=model, metrics=dict(
        checksRun=len(RULES), findingsCount=len(findings), validatedCount=len(findings),
        durationMs=round((time.monotonic() - started) * 1000), modelCalls=call_count, benchmark=benchmark))
