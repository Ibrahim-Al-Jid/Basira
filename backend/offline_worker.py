"""File-based handoff to a scanner that can run with networking disabled."""
import json
import os
from pathlib import Path
import time
from collections import Counter
from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .artifact_review import EXTENDED_IDS, InputError, decode_payload, prepare, review_prepared, tool_record
from .rules import RULES


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
    raw: bytes
    prepared: tuple
    result: dict
    rules: tuple


def scan_payload(data):
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
        if (set(coverage) != set(RULES) | set(EXTENDED_IDS)
                or any(coverage[rule] != counts[rule] for rule in coverage)):
            raise InputError("تعذّر مطابقة النتائج مع تغطية القواعد.")
        return {}

    def task(name, agent, tool, operation, state):
        started = time.monotonic()
        output = operation(state)
        tasks.append(tool_record(name, agent, tool, started))
        return output

    def orchestrate(state):
        raw = task("orchestrator-input-limit", "orchestrator", "base64-envelope",
                   lambda item: decode_payload(item["content"]), state)
        def route(item):
            if item["kind"] not in {"html", "repository", "har", "config"}:
                raise InputError("نوع المدخل غير مدعوم.")
        task("orchestrator-kind", "orchestrator", "artifact-router", route, state)
        return {"raw": raw}

    def plan(state):
        prepared = task("planning-normalize", "planning", "artifact-normalizer",
                        lambda item: prepare(item["kind"], item["name"], item["raw"]), state)
        def rule_plan(item):
            if not isinstance(item["policy"], dict):
                raise InputError("صيغة سياسة المشروع غير صالحة.")
            return (*RULES, *EXTENDED_IDS)
        return {"prepared": prepared, "rules": task("planning-rules", "planning", "rule-registry", rule_plan, state)}

    def review(state):
        task("validation-counts", "validation", "coverage-contract", validate, state)
        def validate_scope(item):
            planned = set(item["rules"])
            if any(row["rule"] not in planned for row in item["result"]["findings"]):
                raise InputError("النتيجة غير موجودة في خطة الفحص.")
        task("validation-scope", "validation", "evidence-registry", validate_scope, state)
        return {}

    def report(state):
        def check_summary(item):
            report = item["result"]
            if not report["summary_ar"] or not report["summary_en"]:
                raise InputError("ملخص التقرير غير مكتمل.")
        task("reporting-summary", "reporting", "bilingual-summary", check_summary, state)
        result = task("reporting-package", "reporting", "report-projection", lambda item: dict(item["result"]), state)
        return {"result": result}

    try:
        operations = [
            ("orchestrator", "تحديد المدخل المرسل", "Identify the supplied artifact",
             orchestrate),
            ("planning", "تجهيز المدخل والقواعد", "Prepare the artifact and checks",
             plan),
            ("analysis", "تنفيذ الفحوصات الدفاعية", "Run offline defensive checks",
             lambda state: {"result": review_prepared(state["prepared"], state["policy"], kind=state["kind"])}),
            ("validation", "مطابقة الأدلة مع التغطية", "Verify evidence counts against coverage", review),
            ("reporting", "تجهيز التقرير", "Assemble the report", report),
        ]
        graph = StateGraph(Review)
        previous = START
        for role, ar, en, operation in operations:
            graph.add_node(role, node(role, None if previous == START else previous, ar, en, operation))
            graph.add_edge(previous, role)
            previous = role
        graph.add_edge(previous, END)
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
                result = scan_payload(data)
                if claimed.exists():
                    write_json(item.with_suffix(".result"), result)
            except (OSError, ValueError, RecursionError):
                pass
            finally:
                claimed.unlink(missing_ok=True)
        time.sleep(0.25)


if __name__ == "__main__":
    run()
