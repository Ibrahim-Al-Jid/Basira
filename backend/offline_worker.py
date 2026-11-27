"""File-based handoff to a scanner that can run with networking disabled."""
import json
import os
from pathlib import Path
from hashlib import sha256
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .artifact_review import (
    EXTENDED_IDS, InputError, decode_payload, prepare, redact_label, resolve_scan_tools, review_prepared, tool_record,
)
from .checks import openapi_contract, zap_passive
from .contracts import AgentExecution
from .scan_contracts import ALL_INPUTS, ROLE_TOOLS, json_digest
from .rules import RULES
from .source_adapters import SOURCE_TOOLS

DOCUMENT_RULES = {"openapi": tuple(openapi_contract.RULES), "zap": tuple(zap_passive.RULES)}
WORKFLOW_EDGES = (
    (START, "orchestrator"), ("orchestrator", "planning"), ("planning", "analysis"),
    ("analysis", "validation"), ("validation", "reporting"), ("reporting", END),
)
INVALID_SNAPSHOT = "لقطة الفحص لا تطابق المصدر المسجّل."
INVALID_EVIDENCE = "فيه نتيجة خارج الأدلة أو الأدوات المسجلة للفحص."


def write_json(path, content):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(content, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Review(TypedDict, total=False):
    kind: str
    name: str
    content: str
    policy: dict
    source_sha256: str
    inventory_sha256: str
    trace_id: str
    raw: bytes
    prepared: tuple
    result: dict
    rules: tuple
    actual_source_sha256: str
    actual_inventory_sha256: str
    tool_plan: list[dict]
    evidence_sha256: str


def verify_evidence(report, prepared, plan, rules):
    files, har, _, _ = prepared
    line_limits = {}
    for path, text in files.items():
        label = redact_label(path)
        line_limits[label] = max(line_limits.get(label, 0), text.count("\n") + 1)
    if not files and isinstance(har, dict):
        line_limits["capture.har"] = 1
    tools = {row["id"]: row["version"] for row in plan if row["status"] == "selected"}
    fingerprints = set()
    for finding in report["findings"]:
        path, line = finding.get("path"), finding["line"]
        fingerprint = json_digest([finding["rule"], path, line, finding["evidence"]])
        if (finding["rule"] not in rules or not 0 < line <= line_limits.get(path, 0)
                or finding.get("fingerprint") != fingerprint or fingerprint in fingerprints
                or not finding["origins"]
                or any(tools.get(origin["tool"]) != origin["version"] for origin in finding["origins"])):
            raise InputError(INVALID_EVIDENCE)
        fingerprints.add(fingerprint)
    return json_digest(sorted(fingerprints))


def scan_payload(data, *, external=False):
    steps = []
    tasks = []

    def node(role, parent, ar, en, operation):
        def event(status):
            steps.append({"node": role, "role": role, "status": status,
                          "parents": [parent] if parent else [], "source": "system",
                          "detail": ar, "detail_en": en,
                          "occurred_at": datetime.now(timezone.utc).isoformat()})

        def run(state):
            event("start")
            output = operation(state)
            event("done")
            return output
        return run

    def validate(state):
        report = state["result"]
        counts = Counter(item["rule"] for item in report["findings"])
        coverage = {row["rule"]: row["match_count"] for row in report["coverage"]}
        ran = {row["tool"] for row in report["task_runs"]}
        document_rules = DOCUMENT_RULES.get(state["kind"])
        expected = set(document_rules) if document_rules else {
            *RULES, *EXTENDED_IDS, *(tool.rule for tool in SOURCE_TOOLS if tool.id in ran)
        }
        if (set(coverage) != expected or not set(counts) <= expected
                or any(coverage[rule] != counts[rule] for rule in coverage)):
            raise InputError("تعذّر مطابقة النتائج مع تغطية القواعد.")
        return {}

    def task(name, agent, tool, operation, state):
        if tool not in ROLE_TOOLS[agent]:
            raise InputError("الأداة خارج صلاحيات الدور.")
        started = time.monotonic()
        output = operation(state)
        tasks.append(tool_record(name, agent, tool, started))
        return output

    def orchestrate(state):
        raw = task("orchestrator-input-limit", "orchestrator", "base64-envelope",
                   lambda item: decode_payload(item["content"]), state)
        def route(item):
            if item["kind"] not in ALL_INPUTS:
                raise InputError("نوع المدخل غير مدعوم.")
        task("orchestrator-kind", "orchestrator", "artifact-router", route, state)
        source_sha256 = sha256(raw).hexdigest()
        trace_id = state.get("trace_id", uuid4().hex)
        if (state.get("source_sha256", source_sha256) != source_sha256
                or not isinstance(trace_id, str) or not re.fullmatch(r"[a-f0-9]{32}", trace_id)):
            raise InputError(INVALID_SNAPSHOT)
        return {"raw": raw, "actual_source_sha256": source_sha256, "trace_id": trace_id}

    def plan(state):
        prepared = task("planning-normalize", "planning", "artifact-normalizer",
                        lambda item: prepare(item["kind"], item["name"], item["raw"]), state)
        inventory = json_digest(prepared[0])
        if state.get("inventory_sha256", inventory) != inventory:
            raise InputError(INVALID_SNAPSHOT)

        def rule_plan(item):
            choices = resolve_scan_tools(item["kind"], item["policy"], external=external)
            pinned_decisions = [choice.model_dump(mode="json") for choice in choices.values()]
            if item["kind"] in DOCUMENT_RULES:
                return DOCUMENT_RULES[item["kind"]], pinned_decisions
            scheduled = {tool.id for tool in choices.values() if tool.status == "selected"}
            source_rules = tuple(tool.rule for tool in SOURCE_TOOLS if tool.id in scheduled)
            return (*RULES, *EXTENDED_IDS, *source_rules), pinned_decisions
        rules, decisions = task("planning-rules", "planning", "rule-registry", rule_plan, state)
        return {"prepared": prepared, "rules": rules, "tool_plan": decisions, "actual_inventory_sha256": inventory}

    def review(state):
        task("validation-counts", "validation", "coverage-contract", validate, state)
        def validate_scope(item):
            if item["result"]["tool_selection"] != item["tool_plan"]:
                raise InputError("الأدوات المنفّذة لا تطابق خطة الفحص.")
            return verify_evidence(item["result"], item["prepared"], item["tool_plan"], set(item["rules"]))
        return {"evidence_sha256": task("validation-scope", "validation", "evidence-registry", validate_scope, state)}

    def report(state):
        def check_summary(item):
            report = item["result"]
            if not report["summary_ar"] or not report["summary_en"]:
                raise InputError("ملخص التقرير غير مكتمل.")
        task("reporting-summary", "reporting", "bilingual-summary", check_summary, state)
        def project(item):
            execution = AgentExecution(
                trace_id=item["trace_id"], input_kind=item["kind"], source_sha256=item["actual_source_sha256"],
                inventory_sha256=item["actual_inventory_sha256"], plan_sha256=json_digest(item["tool_plan"]),
                evidence_sha256=item["evidence_sha256"], files_read=len(item["prepared"][0]),
                validated_locations=len(item["result"]["findings"]),
            )
            return {**item["result"], "execution": execution.model_dump(mode="json")}
        result = task("reporting-package", "reporting", "report-projection", project, state)
        return {"result": result}

    try:
        operations = [
            ("orchestrator", "تحديد المدخل المرسل", "Identify the supplied artifact",
             orchestrate),
            ("planning", "تجهيز المدخل والقواعد", "Prepare the artifact and checks",
             plan),
            ("analysis", "تنفيذ الفحوصات الدفاعية", "Run offline defensive checks",
             lambda state: {"result": review_prepared(
                 state["prepared"], state["policy"], kind=state["kind"], external=external,
             )}),
            ("validation", "مطابقة الأدلة مع التغطية", "Verify evidence counts against coverage", review),
            ("reporting", "تجهيز التقرير", "Assemble the report", report),
        ]
        graph = StateGraph(Review)
        parents = {child: parent for parent, child in WORKFLOW_EDGES}
        for role, ar, en, operation in operations:
            parent = parents[role]
            graph.add_node(role, node(role, None if parent == START else parent, ar, en, operation))
        for parent, child in WORKFLOW_EDGES:
            graph.add_edge(parent, child)
        result = graph.compile().invoke(data)["result"]
        before_analysis = [row for row in tasks if row["agent"] in {"orchestrator", "planning"}]
        after_analysis = [row for row in tasks if row["agent"] in {"validation", "reporting"}]
        return {"result": {**result, "steps": steps,
                           "task_runs": [*before_analysis, *result["task_runs"], *after_analysis]}}
    except InputError as exc:
        return {"error": str(exc)}
    except Exception:
        return {"error": "تعذّر تحليل الملفات المقدّمة."}


def clear_expired(spool):
    cutoff = time.time() - 300
    for item in spool.iterdir():
        if item.suffix in {".request", ".working", ".result", ".tmp"}:
            try:
                if item.is_file() and not item.is_symlink() and item.stat().st_mtime < cutoff:
                    item.unlink(missing_ok=True)
            except OSError:
                pass


def run():
    spool = Path(os.environ["MARSAD_ANALYSIS_SPOOL"])
    spool.mkdir(parents=True, exist_ok=True)
    while True:
        clear_expired(spool)
        for item in sorted(spool.glob("*.request")):
            claimed = item.with_suffix(".working")
            try:
                item.rename(claimed)
            except FileNotFoundError:
                continue
            try:
                data = json.loads(claimed.read_text(encoding="utf-8"))
                result = scan_payload(data, external=True)
                if claimed.exists():
                    write_json(item.with_suffix(".result"), result)
            except (OSError, ValueError, RecursionError):
                pass
            finally:
                claimed.unlink(missing_ok=True)
        time.sleep(0.25)


if __name__ == "__main__":
    run()
