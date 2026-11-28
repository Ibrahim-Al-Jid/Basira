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
import unicodedata
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
import zlib

from .checks import openapi_contract, zap_passive
from .contracts import Finding, RuleCoverage
from .scan_contracts import ANALYZER_INPUTS, TOOL_PROTOCOL_VERSION, json_digest, resolve_analyzers
from .rules import RULES, SourceIndex
from .source_adapters import GITLEAKS, GITLEAKS_PROVIDERS, SOURCE_TOOLS, review_source

MAX_ARTIFACT = 2_000_000
MAX_EXPANDED = 8_000_000
MAX_FILE = 1_000_000
MAX_FILES = 200
RULESET_VERSION = "basira-static-3"
DOMAINS = {"HTML": "html", "WEB": "web", "DEP": "dependencies", "INF": "infrastructure",
           "CI": "ci", "APP": "application", "SRC": "source"}


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
    Adapter("source-code", "source_code", rule_ids(("SRC", 1, 14)), "تحليل الكود المصدري"),
)
EXTENDED_IDS = [rule for adapter in ADAPTERS for rule in adapter.rules]
TEXT_SUFFIXES = {
    ".html", ".htm", ".css", ".json", ".yaml", ".yml", ".env", ".properties", ".ini", ".conf",
    ".cfg", ".py", ".sql", ".lock", ".toml", ".pem", ".key", ".txt", ".tf", ".xml",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".phtml", ".inc", ".sh", ".rb", ".php", ".java", ".cs", ".go", ".rs",
}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".jar"}


class InputError(ValueError):
    """A bounded, generic error that can be shown to the submitter."""


def redact_label(label):
    if not label:
        return label
    return re.sub(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|"
                  r"(?:sk|rk)_(?:live|prod|test)_[A-Za-z0-9]{10,}|AKIA[A-Z0-9]{16}|xoxb-[A-Za-z0-9-]{32,})",
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


def unique_keys(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = entry
    return value


def reject_json_constant(_name):
    raise ValueError("invalid JSON constant")


def read_object(raw, *, limit=MAX_FILE, strict=False):
    if len(raw) > limit:
        raise InputError("ملف JSON تجاوز الحد.")
    try:
        options = {"object_pairs_hook": unique_keys, "parse_constant": reject_json_constant} if strict else {}
        result = json.loads(raw.decode("utf-8-sig"), **options)
    except (ValueError, RecursionError):
        raise InputError("ملف JSON غير صالح.") from None
    if not isinstance(result, dict):
        raise InputError("ملف JSON لازم يحتوي على كائن.")
    return result


def zip_texts(raw, *, manifest=None, metrics=None):
    files = {}
    seen = set()
    total = 0
    executable_entries = 0
    try:
        with ZipFile(io.BytesIO(raw) if isinstance(raw, bytes) else raw) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise InputError("عدد عناصر ZIP لازم يكون بين ١ و٢٠٠.")
            for entry in entries:
                original = entry.orig_filename
                path = safe_path(original.removesuffix("/") if entry.is_dir() else original)
                stamp = unicodedata.normalize("NFKC", path).casefold()
                safe_path(stamp)
                if stamp in seen:
                    raise InputError("ZIP فيه أسماء مكررة.")
                seen.add(stamp)
                mode = entry.external_attr >> 16
                if (stat.S_IFMT(mode) not in {0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG}
                        or entry.flag_bits & 1 or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}):
                    raise InputError("ZIP يحتوي على رابط أو ملف خاص أو طريقة ضغط غير مدعومة.")
                if entry.is_dir():
                    if entry.file_size:
                        raise InputError("عنصر مجلد ZIP غير صالح.")
                    continue
                parsed = PurePosixPath(path)
                executable_entries += bool(mode & 0o111) or parsed.suffix.lower() in {".exe", ".dll", ".sh", ".bat", ".ps1"}
                if parsed.suffix.lower() in ARCHIVE_SUFFIXES:
                    raise InputError("الأرشيفات المتداخلة غير مدعومة.")
                total += entry.file_size
                if total > MAX_EXPANDED or entry.file_size > MAX_FILE:
                    raise InputError("حجم ملفات ZIP بعد الفك تجاوز الحد.")
                if entry.file_size > 100_000 and entry.file_size > 200 * entry.compress_size:
                    raise InputError("نسبة ضغط ملف داخل ZIP تجاوزت الحد.")
                supported = (parsed.suffix.lower() in TEXT_SUFFIXES or parsed.name.lower() == ".npmrc"
                             or parsed.name.lower().startswith(("dockerfile", ".env")))
                with archive.open(entry) as stream:
                    payload = stream.read(MAX_FILE + 1)
                if len(payload) != entry.file_size or payload.startswith((b"PK\x03\x04", b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c", b"Rar!")):
                    raise InputError("محتوى ZIP تالف أو يحتوي على أرشيف متداخل.")
                build = bool({".git", "node_modules", "dist", "build", "__pycache__", "vendor"} & set(parsed.parts[:-1]))
                supported = supported and not build
                if supported:
                    files[path] = plain_text(payload)
                if manifest is not None:
                    manifest.append({"path": redact_label(path), "status": "included" if supported else "skipped",
                                     "reason": None if supported else ("build_artifact" if build else "unsupported_extension")})
    except (BadZipFile, NotImplementedError, RuntimeError, OSError, UnicodeError, zlib.error):
        raise InputError("لقطة المستودع لازم تكون ZIP صالح.") from None
    if not files:
        raise InputError("اللقطة خالية من الملفات النصية المدعومة.")
    if metrics is not None:
        metrics["executable_entries"] = executable_entries
    return files


def decode_payload(content):
    try:
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        raise InputError("ترميز محتوى الملف غير صالح.") from None
    if not 0 < len(raw) <= MAX_ARTIFACT:
        raise InputError("الملف لازم يكون أقل من أو يساوي ٢ ميجابايت.")
    return raw


def prepare(kind, name, raw, *, archive_metrics=None):
    if kind == "repository":
        manifest = []
        files = zip_texts(raw, manifest=manifest, metrics=archive_metrics)
        return files, None, [], sorted(manifest, key=lambda row: row["path"])
    if kind == "openapi":
        document = read_object(raw, limit=MAX_ARTIFACT, strict=True)
        try:
            summary = openapi_contract.inspect_document(document)
        except ValueError:
            raise InputError("ملف OpenAPI لازم يكون JSON بإصدار 3.0 أو 3.1 وفيه info وpaths صالحين.") from None
        return {safe_path(name): ""}, summary, [], None
    if kind == "zap":
        return {safe_path(name): ""}, read_object(raw, limit=MAX_ARTIFACT, strict=True), [], None
    if kind == "har":
        har = read_object(raw, limit=MAX_ARTIFACT)
        log = har.get("log")
        entries = log.get("entries") if isinstance(log, dict) else None
        if not isinstance(entries, list) or not 0 < len(entries) <= 200 or not all(
            isinstance(row, dict) and isinstance(row.get("request"), dict)
            and isinstance(row.get("response"), dict) for row in entries
        ):
            raise InputError("ملف HAR لازم يحتوي على ١–٢٠٠ استجابة محفوظة.")
        return {}, har, [], None
    if kind == "config":
        package = read_object(raw, limit=MAX_ARTIFACT)
        entries = package.get("files")
        if entries is None:
            # A submitted configuration document is reviewed as itself. The bundle envelope
            # ({"files": {...}}) stays supported for the synthetic corpus and its tests.
            return {safe_path(name): plain_text(raw)}, None, [], None
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
        return files, None, advisories, None
    text = plain_text(raw)
    if len(text) > 250_000 or not SourceIndex(text).tags:
        raise InputError("مدخل HTML محتاج عنصر واحد على الأقل، بحد ٢٥٠ ألف حرف.")
    return {safe_path(name): text}, None, [], None


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
    return {"id": identifier, "agent": agent, "tool": tool, "status": outcome, "contract": "basira-tool-result-1",
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


def source_observations(observations, findings):
    builtin_secrets = {
        (item["rule"], item.get("path"), item["line"], item["evidence"]): item
        for item in findings if item["rule"] in {"APP-01", "APP-02"}
    }
    supplemental = []
    for item in observations:
        item["path"] = redact_label(item["path"])
        origin = item["origins"][0]
        provider = GITLEAKS_PROVIDERS.get(origin["rule"]) if origin["tool"] == GITLEAKS.id else None
        existing = None
        if provider:
            existing = builtin_secrets.get(("APP-02", item["path"], item["line"],
                                            f"{provider} token signature is present."))
        elif origin["tool"] == GITLEAKS.id and origin["rule"] == "private-key":
            existing = builtin_secrets.get(("APP-01", item["path"], item["line"], "PEM private-key marker is present."))
        if existing is not None:
            if origin not in existing["origins"]:
                existing["origins"].append(origin)
        else:
            supplemental.append(item)
    return supplemental


def unique_observations(findings):
    # The same finding reported by two tools merges into one. Two identical
    # findings from one tool (two scripts on one minified line) stay separate:
    # each takes the next occurrence slot, and slot 0 keeps the old fingerprint.
    by_fingerprint = {}
    slots = {}
    for item in findings:
        base = [item["rule"], item.get("path"), item["line"], item["evidence"]]
        origins = {json_digest(origin) for origin in item["origins"]}
        buckets = slots.setdefault(json_digest(base), [])
        for bucket in buckets:
            if not origins & bucket["seen"]:
                break
        else:
            bucket = {"seen": set(), "fingerprint": json_digest(base if not buckets else [*base, len(buckets)])}
            buckets.append(bucket)
        bucket["seen"] |= origins
        previous = by_fingerprint.get(bucket["fingerprint"])
        if previous is None:
            by_fingerprint[bucket["fingerprint"]] = {**item, "fingerprint": bucket["fingerprint"]}
        else:
            for origin in item["origins"]:
                if origin not in previous["origins"]:
                    previous["origins"].append(origin)
    return list(by_fingerprint.values())


def resolve_scan_tools(kind, policy, *, external):
    if not isinstance(policy, dict):
        raise InputError("صيغة سياسة المشروع غير صالحة.")
    pinned = policy.get("_analysis_plan")
    try:
        if "_analysis_plan" in policy and (pinned is None or policy.get("_ruleset_version") != RULESET_VERSION):
            raise ValueError("Incompatible ruleset or empty execution plan")
        return {item.id: item for item in resolve_analyzers(kind, pinned=pinned, external=external)}
    except ValueError:
        raise InputError("نسخة خطة الفحص غير متوافقة. قدّم الملف من جديد.") from None


def review_prepared(prepared, policy, *, kind=None, external=False):
    # Adapters are statically registered. Uploaded data cannot select executable commands.
    started = time.monotonic()
    files, har, advisories, input_manifest = prepared
    findings = []
    coverage = []
    api_inventory = None
    imported_evidence = None
    document_kinds = {"openapi": "openapi-contract", "zap": zap_passive.TOOL}
    decisions = resolve_scan_tools(kind, policy, external=external)
    pinned = policy.get("_analysis_plan")
    planned = {tool.id for tool in decisions.values() if tool.status == "selected"}
    source_ids = planned if pinned is None else {pin["id"] for pin in pinned}
    source_plan = tuple(tool for tool in SOURCE_TOOLS if tool.id in source_ids)
    local_status = {rule_id: "not_applicable" for rule_id in RULES}
    for path, html in files.items() if "html-attributes" in planned else ():
        if PurePosixPath(path).suffix.lower() not in {".html", ".htm"}:
            continue
        index = SourceIndex(html)
        findings.extend({**item, "path": redact_label(path), "origins": [{
            "tool": "html-attributes", "version": RULESET_VERSION, "rule": item["rule"],
        }]} for item in index.evidence)
        if len(findings) > 5000:
            raise InputError("عدد مواضع الأدلة تجاوز الحد. قسّم اللقطة إلى ملفات أصغر.")
        for row in index.coverage():
            if row["status"] == "matched" or local_status[row["rule"]] == "not_applicable":
                local_status[row["rule"]] = row["status"]
    counts = Counter(item["rule"] for item in findings)
    html_decision = decisions["html-attributes"]
    html_skipped = html_decision.status == "skipped" and html_decision.reason != "unsupported_input"
    for rule in RULES.values() if kind not in document_kinds else ():
        coverage.append(RuleCoverage(rule=rule.id, domain=rule.domain, match_count=counts[rule.id],
                                     status="skipped" if html_skipped else local_status[rule.id],
                                     reason=html_decision.reason if html_skipped else None))
    task_runs = [tool_record("analysis-html", "analysis", "html-attributes", started, coverage)] if "html-attributes" in planned else []
    for adapter in ADAPTERS if kind not in document_kinds else ():
        tool_started = time.monotonic()
        expected = adapter.rules
        if adapter.id not in planned:
            reason = decisions[adapter.id].reason
            eligible = reason != "unsupported_input"
            coverage.extend(
                RuleCoverage(rule=rule, domain=DOMAINS[rule.split("-")[0]],
                             status="skipped" if eligible else "not_applicable", match_count=0,
                             reason=reason) for rule in expected
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
                        **item, "path": redact_label(item.get("path")), "origins": [{
                            "tool": adapter.id, "version": RULESET_VERSION, "rule": rule_id,
                        }],
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
    if kind == "openapi":
        api_inventory, counts = har
        path = redact_label(next(iter(files)))
        for rule, count in counts.items():
            coverage.append(RuleCoverage(rule=rule, domain="api", match_count=int(bool(count)),
                                         status="matched" if count else "clear"))
            if count:
                title, title_ar, remediation, remediation_ar = openapi_contract.RULES[rule]
                findings.append(Finding(
                    rule=rule, severity="medium" if rule == "API-01" else "low",
                    line=1, path=path, evidence=f"{count} matching declarations in the document.",
                    title=title, title_ar=title_ar, remediation=remediation, remediation_ar=remediation_ar,
                    domain="api", confidence="high", assessment="review_required",
                    origins=[{"tool": "openapi-contract", "version": RULESET_VERSION, "rule": rule}],
                ).model_dump(mode="json"))
        task_runs.append(tool_record("analysis-openapi-contract", "analysis", "openapi-contract", started, coverage))
    if kind == "zap":
        try:
            imported_evidence, imported_counts = zap_passive.inspect_document(har, policy.get("base_url"))
        except ValueError as exc:
            if str(exc) == "scope":
                raise InputError("أصل الموقع في تقرير ZAP لازم يطابق مرجع الفحص.") from None
            raise InputError("ملف ZAP محتاج تقرير Traditional JSON صالح ضمن حدود الاستيراد.") from None
        path = redact_label(next(iter(files)))
        for rule, (severity, title, title_ar, remediation, remediation_ar) in zap_passive.RULES.items():
            count = imported_counts[rule]
            coverage.append(RuleCoverage(rule=rule, domain="web", match_count=int(bool(count)),
                                         status="matched" if count else "not_applicable",
                                         reason="imported_observation" if count else "alert_not_present_in_export"))
            if count:
                findings.append(Finding(
                    rule=rule, severity=severity, line=1, path=path,
                    evidence=f"Saved ZAP report contains {count} observation(s) for this rule.",
                    title=title, title_ar=title_ar, remediation=remediation, remediation_ar=remediation_ar,
                    domain="web", assessment="review_required",
                    origins=[{"tool": zap_passive.TOOL, "version": RULESET_VERSION, "rule": rule}],
                ).model_dump(mode="json"))
        run = tool_record("analysis-zap-import", "analysis", zap_passive.TOOL, started, coverage)
        task_runs.append({**run, "checks": 0, "reason": "imported_observations"})
    for tool in source_plan:
        tool_started = time.monotonic()
        result = review_source(tool, files) if tool.id in planned else None
        status = result.status if result else "skipped"
        reason = result.reason if result else decisions[tool.id].reason
        observations = []
        if result and len(findings) + len(result.observations) <= 5000:
            observations = source_observations(result.observations, findings)
        elif result and result.observations:
            status, reason = "error", "adapter_output_limit"
        if status == "matched" and not observations:
            status, reason = "clear", "merged_observations"
        findings.extend(Finding.model_validate(item).model_dump(mode="json") for item in observations)
        row = RuleCoverage(rule=tool.rule, domain=tool.domain, status=status, match_count=len(observations), reason=reason)
        coverage.append(row)
        task = tool_record("analysis-" + tool.id, "analysis", tool.id, tool_started, [row])
        task.update(version=tool.version, reason=reason, database_date=(
            result.database_date.isoformat() if result and result.database_date else None
        ))
        if status == "skipped" or (status == "error" and observations):
            task["status"] = "partial"
        task_runs.append(task)
    findings = unique_observations(findings)
    counts = Counter(item["rule"] for item in findings)
    for row in coverage:
        row.match_count = counts[row.rule]
    applied = 0 if imported_evidence else sum(row.status in ("matched", "clear") for row in coverage)
    unique = len({finding["rule"] for finding in findings})
    errors = sum(row.status in {"error", "skipped"} for row in coverage)
    if imported_evidence:
        summary_ar = f"استوردنا مجموعات ملاحظات من تقرير ZAP محفوظ تغطي {unique} أنواع."
        summary_en = f"Imported {unique} observation type(s) from the saved ZAP report."
    else:
        summary_ar = (f"انطبقت {applied} قاعدة على الملفات المقدّمة. ظهرت {unique} أنواع نتائج في "
                      f"{len(findings)} مواضع، وتعذّر تنفيذ {errors} قاعدة.")
        summary_en = (f"{applied} {'rule' if applied == 1 else 'rules'} applied to the submitted artifacts. "
                      f"Found {unique} {'finding type' if unique == 1 else 'finding types'} "
                      f"at {len(findings)} {'location' if len(findings) == 1 else 'locations'}. "
                      f"{errors} {'rule' if errors == 1 else 'rules'} could not run.")
    return {
        "summary_ar": summary_ar,
        "summary_en": summary_en,
        "summary_source": "system",
        "status": "partial" if errors else "completed",
        "enrichment": "disabled",
        "findings": findings,
        "api_inventory": api_inventory,
        "imported_evidence": imported_evidence,
        "input_manifest": input_manifest,
        "coverage": [row.model_dump(mode="json") for row in coverage],
        "input_paths": sorted(redact_label(path) for path in files),
        "task_runs": task_runs,
        "tool_selection": [item.model_dump(mode="json") for item in decisions.values()],
        "metrics": {"checksRun": applied, "findingsCount": len(findings), "validatedCount": len(findings),
                    "modelCalls": 0, "durationMs": round((time.monotonic() - started) * 1000)},
    }
