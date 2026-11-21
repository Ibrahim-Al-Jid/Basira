"""Offline analysis of explicitly submitted files. No target connection or execution."""
import base64
import binascii
from collections import Counter
from dataclasses import dataclass
from importlib import import_module
import io
import json
from pathlib import PurePosixPath
import re
import stat
import time
from zipfile import BadZipFile, ZipFile

from .contracts import Finding, RuleCoverage
from .phase9_contracts import ANALYZER_INPUTS, TOOL_PROTOCOL_VERSION
from .rules import RULES, SourceIndex

MAX_ARTIFACT = 2_000_000
MAX_EXPANDED = 8_000_000
MAX_FILE = 1_000_000
MAX_FILES = 200
RULESET_VERSION = "marsad-static-2"
DOMAINS = {"HTML": "html", "WEB": "web", "DEP": "dependencies", "INF": "infrastructure",
           "CI": "ci", "APP": "application"}


def rule_ids(*ranges):
    return tuple(f"{prefix}-{index:02d}" for prefix, start, stop in ranges for index in range(start, stop + 1))


@dataclass(frozen=True)
class Adapter:
    id: str
    module: str
    rules: tuple[str, ...]
    title_ar: str


ADAPTERS = (
    Adapter("browser-controls", "web", rule_ids(("HTML", 4, 10), ("WEB", 1, 10)), "ضوابط HTML والاستجابات"),
    Adapter("dependency-evidence", "dependencies", rule_ids(("DEP", 1, 8)), "مطابقة التبعيات والتنبيهات"),
    Adapter("deployment-config", "config", rule_ids(("INF", 1, 10), ("CI", 1, 6), ("APP", 1, 6)), "إعدادات التشغيل والنشر"),
    Adapter("browser-controls-extra", "web_extra", rule_ids(("HTML", 11, 20), ("WEB", 11, 25)), "ضوابط المتصفح الإضافية"),
    Adapter("deployment-config-extra", "config_extra", rule_ids(("DEP", 9, 16), ("INF", 11, 18),
            ("CI", 7, 10), ("APP", 7, 11)), "إعدادات التبعيات والبنية الإضافية"),
)
EXTENDED_IDS = [rule for adapter in ADAPTERS for rule in adapter.rules]
TEXT_SUFFIXES = {
    ".html", ".htm", ".json", ".yaml", ".yml", ".env", ".properties", ".ini", ".conf",
    ".cfg", ".py", ".sql", ".lock", ".toml", ".pem", ".key", ".txt", ".tf", ".xml",
    ".js", ".ts", ".jsx", ".tsx", ".sh", ".rb", ".php", ".java", ".cs", ".go", ".rs",
}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".jar"}


class InputError(ValueError):
    """A bounded, generic error that can be shown to the submitter."""


def redact_label(label):
    if not label:
        return label
    return re.sub(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})",
                  "[redacted]", label)


def safe_path(value):
    if not isinstance(value, str) or len(value) > 240 or any(
        any(ord(char) < 32 or ord(char) == 127 or char in "\\:" for char in part)
        or part in ("", ".", "..") for part in value.split("/")
    ):
        raise InputError("مسار ملف داخل اللقطة غير صالح.")
    return value


def plain_text(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise InputError("ملف نصي في اللقطة مش بترميز UTF-8 صالح.") from None
    if "\x00" in text or len(raw) > MAX_FILE:
        raise InputError("ملف نصي في اللقطة تجاوز الحدود أو فيه بيانات ثنائية.")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_object(raw, *, limit=MAX_FILE):
    if len(raw) > limit:
        raise InputError("ملف JSON تجاوز الحد.")
    try:
        result = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        raise InputError("ملف JSON غير صالح.") from None
    if not isinstance(result, dict):
        raise InputError("ملف JSON لازم يحتوي على كائن.")
    return result


def zip_texts(raw):
    files = {}
    seen = set()
    total = 0
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise InputError("عدد عناصر ZIP لازم يكون بين ١ و٢٠٠.")
            for entry in entries:
                original = entry.orig_filename
                path = safe_path(original.removesuffix("/") if entry.is_dir() else original)
                stamp = path.casefold()
                if stamp in seen:
                    raise InputError("ZIP فيه أسماء مكررة.")
                seen.add(stamp)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or entry.flag_bits & 1:
                    raise InputError("الروابط الرمزية والملفات المشفرة غير مدعومة.")
                if entry.is_dir():
                    continue
                parsed = PurePosixPath(path)
                if parsed.suffix.lower() in ARCHIVE_SUFFIXES:
                    raise InputError("الأرشيفات المتداخلة غير مدعومة.")
                total += entry.file_size
                if total > MAX_EXPANDED or entry.file_size > MAX_FILE:
                    raise InputError("حجم ملفات ZIP بعد الفك تجاوز الحد.")
                if (parsed.suffix.lower() in TEXT_SUFFIXES or parsed.name.lower() == ".npmrc"
                        or parsed.name.lower().startswith(("dockerfile", ".env"))):
                    with archive.open(entry) as stream:
                        files[path] = plain_text(stream.read(MAX_FILE + 1))
    except (BadZipFile, NotImplementedError, RuntimeError, OSError):
        raise InputError("لقطة المستودع لازم تكون ZIP صالح.") from None
    if not files:
        raise InputError("اللقطة خالية من الملفات النصية المدعومة.")
    return files


def decode_payload(content):
    try:
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        raise InputError("ترميز محتوى الملف غير صالح.") from None
    if not 0 < len(raw) <= MAX_ARTIFACT:
        raise InputError("الملف لازم يكون أقل من أو يساوي ٢ ميجابايت.")
    return raw


def prepare(kind, name, raw):
    if kind == "repository":
        return zip_texts(raw), None, []
    if kind == "har":
        har = read_object(raw, limit=MAX_ARTIFACT)
        log = har.get("log")
        entries = log.get("entries") if isinstance(log, dict) else None
        if not isinstance(entries, list) or not 0 < len(entries) <= 200 or not all(
            isinstance(row, dict) and isinstance(row.get("request"), dict)
            and isinstance(row.get("response"), dict) for row in entries
        ):
            raise InputError("ملف HAR لازم يحتوي على ١–٢٠٠ استجابة محفوظة.")
        return {}, har, []
    if kind == "config":
        package = read_object(raw, limit=MAX_ARTIFACT)
        entries = package.get("files")
        advisories = package.get("advisories", [])
        if (not isinstance(entries, dict) or not 0 < len(entries) <= MAX_FILES
                or not all(isinstance(text, str) for text in entries.values())
                or not isinstance(advisories, list) or len(advisories) > 2000
                or not all(isinstance(record, dict) for record in advisories)):
            raise InputError("لقطة الإعدادات تحتاج files، وقائمة advisories اختيارية.")
        if len(set(path.casefold() for path in entries)) != len(entries):
            raise InputError("اللقطة فيها أسماء ملفات مكررة.")
        try:
            files = {safe_path(path): plain_text(text.encode("utf-8")) for path, text in entries.items()}
        except UnicodeError:
            raise InputError("لقطة الإعدادات فيها نص غير صالح.") from None
        return files, None, advisories
    text = plain_text(raw)
    if len(text) > 250_000 or not SourceIndex(text).tags:
        raise InputError("مدخل HTML محتاج عنصر واحد على الأقل، بحد ٢٥٠ ألف حرف.")
    return {safe_path(name): text}, None, []


def defensive_review(kind, name, raw, policy):
    return review_prepared(prepare(kind, name, raw), policy, kind=kind)


def tool_record(identifier, agent, tool, started, rows=()):
    statuses = Counter(row.status for row in rows)
    if statuses["error"]:
        outcome = "partial" if statuses["clear"] or statuses["matched"] else "error"
    elif rows and statuses["not_applicable"] == len(rows):
        outcome = "not_applicable"
    else:
        outcome = "done"
    return {"id": identifier, "agent": agent, "tool": tool, "status": outcome,
            "checks": statuses["clear"] + statuses["matched"], "matched": statuses["matched"],
            "coverage": [row.rule for row in rows], "duration_ms": round((time.monotonic() - started) * 1000),
            "version": RULESET_VERSION if tool in ANALYZER_INPUTS else TOOL_PROTOCOL_VERSION}


def catalog():
    rules = [{"id": entry.id, "title": entry.title, "title_ar": entry.title_ar, "domain": entry.domain,
              "tool": "html-attributes"} for entry in RULES.values()]
    tools = [{"id": "html-attributes", "title_ar": "خصائص HTML الأساسية", "rules": list(RULES)}]
    for adapter in ADAPTERS:
        module = import_module(".checks." + adapter.module, __package__)
        info = getattr(module, "RULE_TEXT", getattr(module, "DESCRIPTIONS",
                       getattr(module, "TEXT", getattr(module, "SPEC", {}))))
        tools.append({"id": adapter.id, "title_ar": adapter.title_ar, "rules": list(adapter.rules)})
        for rule_id in adapter.rules:
            _, title, title_ar, *_ = info.get(rule_id, ("", rule_id, rule_id))
            rules.append({"id": rule_id, "title": title, "title_ar": title_ar,
                          "domain": DOMAINS[rule_id.split("-")[0]], "tool": adapter.id})
    return {"version": RULESET_VERSION, "rules": rules, "tools": tools}


def review_prepared(prepared, policy, *, kind=None):
    # Adapters are statically registered. Uploaded data cannot select executable commands.
    started = time.monotonic()
    files, har, advisories = prepared
    findings = []
    coverage = []
    pinned = policy.get("_analysis_plan")
    if pinned is None:
        planned = set(ANALYZER_INPUTS)  # Compatibility for the anonymous lab and queued historical jobs.
    else:
        planned = {item["id"] for item in pinned}
        expected = [{"id": tool, "version": RULESET_VERSION} for tool, inputs in ANALYZER_INPUTS.items()
                    if kind in inputs and tool in planned]
        if policy.get("_ruleset_version") != RULESET_VERSION or not expected or expected != pinned:
            raise InputError("نسخة خطة الفحص غير متوافقة. قدّم الملف من جديد.")
    local_status = {rule_id: "not_applicable" for rule_id in RULES}
    for path, html in files.items() if "html-attributes" in planned else ():
        if PurePosixPath(path).suffix.lower() not in {".html", ".htm"}:
            continue
        index = SourceIndex(html)
        findings.extend({**item, "path": redact_label(path)} for item in index.evidence)
        if len(findings) > 5000:
            raise InputError("عدد مواضع الأدلة تجاوز الحد. قسّم اللقطة إلى ملفات أصغر.")
        for row in index.coverage():
            if row["status"] == "matched" or local_status[row["rule"]] == "not_applicable":
                local_status[row["rule"]] = row["status"]
    counts = Counter(item["rule"] for item in findings)
    for rule in RULES.values():
        coverage.append(RuleCoverage(rule=rule.id, domain=rule.domain, match_count=counts[rule.id],
                                     status=local_status[rule.id]))
    task_runs = [tool_record("analysis-html", "analysis", "html-attributes", started, coverage)] if "html-attributes" in planned else []
    for adapter in ADAPTERS:
        tool_started = time.monotonic()
        expected = adapter.rules
        if adapter.id not in planned:
            eligible = kind in ANALYZER_INPUTS[adapter.id]
            coverage.extend(
                RuleCoverage(rule=rule, domain=DOMAINS[rule.split("-")[0]],
                             status="skipped" if eligible else "not_applicable", match_count=0,
                             reason="adapter_unavailable" if eligible else "unsupported_input") for rule in expected
            )
            continue
        try:
            module = import_module(".checks." + adapter.module, __package__)
            results = module.check(files, har, policy, advisories)
            if set(results) != set(expected):
                raise ValueError("Unregistered result")
            adapter_findings, adapter_coverage = [], []
            for rule_id in expected:
                domain = DOMAINS[rule_id.split("-")[0]]
                hits = results[rule_id]
                status = "not_applicable" if hits is None else "matched" if hits else "clear"
                adapter_coverage.append(RuleCoverage(rule=rule_id, domain=domain,
                                                     status=status, match_count=len(hits or [])))
                for item in hits or []:
                    if len(findings) + len(adapter_findings) >= 5000:
                        raise InputError("عدد مواضع الأدلة تجاوز الحد. قسّم اللقطة إلى ملفات أصغر.")
                    adapter_findings.append(Finding.model_validate({
                        "rule": rule_id, "domain": domain, "severity": "medium", "confidence": "medium",
                        "assessment": "review_required", "title": rule_id,
                        "remediation": "Review the indicated setting against the project policy.",
                        **item, "path": redact_label(item.get("path")),
                    }).model_dump(mode="json"))
            findings.extend(adapter_findings)
            coverage.extend(adapter_coverage)
        except InputError:
            raise
        except Exception:
            adapter_coverage = [RuleCoverage(rule=rule, domain=DOMAINS[rule.split("-")[0]],
                                             status="error", match_count=0, reason="adapter_failed")
                                for rule in expected]
            coverage.extend(adapter_coverage)
        task_runs.append(tool_record("analysis-" + adapter.id, "analysis", adapter.id, tool_started, adapter_coverage))
    applied = sum(row.status in ("matched", "clear") for row in coverage)
    unique = len({finding["rule"] for finding in findings})
    errors = sum(row.status in {"error", "skipped"} for row in coverage)
    return {
        "summary_ar": f"انطبقت {applied} قاعدة على الملفات المقدّمة. ظهرت {unique} أنواع نتائج في "
                      f"{len(findings)} مواضع، وتعذّر تنفيذ {errors} قاعدة.",
        "summary_en": f"{applied} {'rule' if applied == 1 else 'rules'} applied to the submitted artifacts. "
                      f"Found {unique} {'finding type' if unique == 1 else 'finding types'} "
                      f"at {len(findings)} {'location' if len(findings) == 1 else 'locations'}. "
                      f"{errors} {'rule' if errors == 1 else 'rules'} could not run.",
        "summary_source": "system",
        "enrichment": "disabled",
        "findings": findings,
        "coverage": [row.model_dump(mode="json") for row in coverage],
        "input_paths": sorted(redact_label(path) for path in files),
        "task_runs": task_runs,
        "metrics": {"checksRun": applied, "findingsCount": len(findings), "validatedCount": len(findings),
                    "modelCalls": 0, "durationMs": round((time.monotonic() - started) * 1000)},
    }
