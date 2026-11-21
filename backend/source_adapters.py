"""Pinned classifiers for read-only, submitted source snapshots in the isolated worker."""
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from tempfile import TemporaryDirectory


TOOLS_DIR = Path("/opt/marsad-tools")
MAX_REPORT_BYTES = 2_000_000
MAX_OBSERVATIONS = 1000
SOURCE_KINDS = ("repository", "config")
GITLEAKS_RULE = "SRC-01"
PYPI_RULE = "SCA-01"
SAFE_RULE = re.compile(r"[a-z][a-z0-9-]{0,79}")
SAFE_ADVISORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}")
PYPI_PIN = re.compile(
    r"(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]{0,149})(?:\[[a-zA-Z0-9._,-]+\])?\s*==\s*"
    r"(?P<version>[0-9][a-zA-Z0-9.!+_-]{0,99})(?:\s*#.*)?"
)
GITLEAKS_PROVIDERS = {
    "github-pat": "GitHub", "github-fine-grained-pat": "GitHub", "github-oauth": "GitHub",
    "github-app-token": "GitHub", "github-refresh-token": "GitHub", "slack-bot-token": "Slack",
}


@dataclass(frozen=True)
class SourceTool:
    id: str
    version: str
    rule: str
    domain: str
    title_en: str
    title_ar: str

    @property
    def pin(self):
        return {"id": self.id, "version": self.version}


GITLEAKS = SourceTool("gitleaks", "8.30.1", GITLEAKS_RULE, "application", "Secret signatures", "بصمات الأسرار")
OSV = SourceTool("osv-scanner", "2.7.1", PYPI_RULE, "dependencies", "PyPI advisories", "تنبيهات تبعيات PyPI")
SOURCE_TOOLS = (GITLEAKS, OSV)


@dataclass
class AdapterResult:
    observations: list[dict]
    status: str
    reason: str | None = None
    database_date: date | None = None


class AdapterError(Exception):
    """Carries only fixed machine codes that can safely enter a report."""


def configured_tools():
    selected = {name.strip() for name in os.environ.get("MARSAD_SOURCE_ADAPTERS", "").split(",")}
    return tuple(tool for tool in SOURCE_TOOLS if tool.id in selected)


def run_cli(tool, args, directory, report, *, timeout, success, env=None):
    executable = TOOLS_DIR / tool.id
    if not executable.is_file():
        raise AdapterError("adapter_unavailable")
    variables = {"PATH": "/usr/bin:/bin", "HOME": str(directory), "TMPDIR": str(directory), "LANG": "C.UTF-8",
                 "GOMAXPROCS": "1", "GOMEMLIMIT": "275MiB"}
    result = subprocess.run(
        [str(executable), *args], cwd=directory, env={**variables, **(env or {})}, check=False,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode not in success:
        raise AdapterError("adapter_failed")
    with report.open("rb") as stream:
        data = stream.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise AdapterError("adapter_output_limit")
    return json.loads(data), result.returncode


def gitleaks(files, directory):
    snapshot = directory / "snapshot"
    snapshot.mkdir()
    lookup = {}
    for index, (path, text) in enumerate(sorted(files.items())):
        source = PurePosixPath(path)
        if ".git" in source.parts:
            continue
        # A numbered parent and a safe filename prevent repository settings from taking effect.
        name = source.name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", source.name) else "source" + source.suffix
        target = snapshot / str(index) / name
        target.parent.mkdir()
        target.write_text(text, encoding="utf-8")
        lookup[str(target)] = (path, text.count("\n") + 1)
    if not lookup:
        return AdapterResult([], "not_applicable", "unsupported_input")
    config = directory / "gitleaks.toml"
    config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
    ignored = directory / ".gitleaksignore"
    ignored.touch()
    report = directory / "gitleaks.json"
    output, code = run_cli(GITLEAKS, [
        "dir", str(snapshot), "--config", str(config), "--gitleaks-ignore-path", str(ignored),
        "--ignore-gitleaks-allow", "--redact=100", "--no-banner", "--no-color", "--log-level=error",
        "--max-archive-depth=0", "--max-decode-depth=0", "--max-target-megabytes=1",
        "--exit-code=42", "--report-format=json", "--report-path", str(report),
    ], directory, report, timeout=8, success={0, 42})
    if not isinstance(output, list) or bool(output) != (code == 42):
        raise AdapterError("adapter_invalid_output")
    if len(output) > MAX_OBSERVATIONS:
        raise AdapterError("adapter_output_limit")
    observations = []
    for item in output:
        if not isinstance(item, dict):
            raise AdapterError("adapter_invalid_output")
        source = item.get("File")
        location = lookup.get(str(directory / source)) if isinstance(source, str) else None
        rule = item.get("RuleID")
        line = item.get("StartLine")
        if (location is None or not isinstance(rule, str) or not SAFE_RULE.fullmatch(rule)
                or type(line) is not int or not 0 < line <= location[1]):
            raise AdapterError("adapter_invalid_output")
        path, _ = location
        # Project a fixed message. Match, Secret, fingerprint, and source snippets never cross the boundary.
        observations.append({
            "rule": GITLEAKS.rule, "domain": GITLEAKS.domain, "line": line, "path": path,
            "title": "Credential signature in a submitted file", "title_ar": "بصمة بيانات اعتماد في ملف مرفوع",
            "evidence": f"Gitleaks detected a credential pattern ({rule}).",
            "remediation": "Remove the value and rotate it if it was used.",
            "remediation_ar": "احذف القيمة ودوّرها لو كانت مستخدمة.",
            "severity": "high", "confidence": "medium", "assessment": "review_required",
            "origins": [origin(GITLEAKS, rule)],
        })
    return AdapterResult(observations, "matched" if observations else "clear")


def origin(tool, rule):
    return {"tool": tool.id, "version": tool.version, "rule": rule}


def pypi_key(name):
    return re.sub(r"[-_.]+", "-", name.casefold())


def pypi_inputs(files, directory):
    manifests = {}
    partial = False
    pin_count = 0
    for index, (path, text) in enumerate(sorted(files.items())):
        source = PurePosixPath(path)
        if source.name != "requirements.txt" or ".git" in source.parts:
            continue
        rows = {}
        for line, raw in enumerate(text.splitlines(), 1):
            rendered = raw.strip()
            if not rendered or rendered.startswith("#"):
                continue
            match = PYPI_PIN.fullmatch(rendered)
            if not match:
                partial = True
                continue
            name, version = match["name"], match["version"]
            key = (pypi_key(name), version)
            if key in rows:
                continue
            if pin_count >= MAX_OBSERVATIONS:
                partial = True
                continue
            rows[key] = (name, line)
            pin_count += 1
        if rows:
            target = directory / str(index) / "requirements.txt"
            target.parent.mkdir()
            target.write_text("".join(f"{name}=={version}\n" for name, version in rows), encoding="ascii")
            manifests[str(target)] = (path, rows)
    return manifests, partial


def database():
    cache = Path(os.environ.get("MARSAD_OSV_DB_DIRECTORY", "/opt/marsad-osv"))
    if not (cache / "osv-scalibr" / "PyPI" / "all.zip").is_file():
        raise AdapterError("database_unavailable")
    try:
        with (cache / "database-date").open("rb") as stamp:
            published = date.fromisoformat(stamp.read(16).decode("ascii").strip())
    except (OSError, ValueError):
        raise AdapterError("database_unavailable") from None
    return cache, published


def advisory_groups(records):
    groups = []
    if not isinstance(records, list):
        raise AdapterError("adapter_invalid_output")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise AdapterError("adapter_invalid_output")
        identifier = record["id"]
        if not SAFE_ADVISORY.fullmatch(identifier):
            raise AdapterError("adapter_invalid_output")
        related = record.get("aliases") or []
        if not isinstance(related, list):
            raise AdapterError("adapter_invalid_output")
        cluster = {identifier, *(name for name in related if isinstance(name, str) and SAFE_ADVISORY.fullmatch(name))}
        overlaps = [old for old in groups if old & cluster]
        for old in overlaps:
            cluster |= old
            groups.remove(old)
        groups.append(cluster)
    return [sorted(cluster, key=lambda name: (not name.startswith("CVE-"), name)) for cluster in groups]


def osv(files, directory):
    manifests, partial = pypi_inputs(files, directory)
    if not manifests:
        if partial:
            return AdapterResult([], "error", "unsupported_dependency_pin")
        return AdapterResult([], "not_applicable", "unsupported_input")
    cache, published = database()
    config = directory / "osv-scanner.toml"
    config.touch()
    report = directory / "osv.json"
    flags = [value for manifest in manifests for value in ("--lockfile", manifest)]
    output, _ = run_cli(OSV, [
        "scan", "source", "--offline", "--no-resolve", "--all-packages",
        "--verbosity=error", "--format=json", "--output-file", str(report), "--config", str(config),
        *flags,
    ], directory, report, timeout=22, success={0, 1}, env={
        "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY": str(cache),
    })
    if not isinstance(output, dict) or not isinstance(output.get("results"), list):
        raise AdapterError("adapter_invalid_output")
    observations = []
    seen = set()
    for package_result in output["results"]:
        source = package_result["source"]["path"]
        location = manifests.get(str(directory / source)) if isinstance(source, str) else None
        if location is None or not isinstance(package_result["packages"], list):
            raise AdapterError("adapter_invalid_output")
        path, rows = location
        for entry in package_result["packages"]:
            package = entry["package"]
            key = (pypi_key(package["name"]), package["version"])
            if key not in rows or package["ecosystem"] != "PyPI":
                raise AdapterError("adapter_invalid_output")
            seen.add((str(directory / source), key))
            name, line = rows[key]
            for identifier, *aliases in advisory_groups(entry.get("vulnerabilities") or []):
                observations.append({
                    "rule": OSV.rule, "domain": OSV.domain, "line": line, "path": path,
                    "title": "Pinned PyPI dependency matches a known advisory",
                    "title_ar": "تبعية PyPI مثبّتة تطابق تنبيهًا معروفًا",
                    "evidence": f"PyPI dependency {name}=={key[1]} matches {identifier}.",
                    "remediation": "Review the advisory and upgrade the dependency to an approved fixed version.",
                    "remediation_ar": "راجع التنبيه وحدّث التبعية لإصدار معتمد فيه الإصلاح.",
                    "severity": "medium", "confidence": "high", "assessment": "observed",
                    "origins": [origin(OSV, identifier)],
                    "advisory": {"id": identifier, "aliases": aliases[:30], "ecosystem": "PyPI",
                                 "package": name, "version": key[1], "database_date": published.isoformat()},
                })
                if len(observations) > MAX_OBSERVATIONS:
                    raise AdapterError("adapter_output_limit")
    expected = {(path, key) for path, (_, pins) in manifests.items() for key in pins}
    if partial or seen != expected:
        return AdapterResult(observations, "error", "unsupported_dependency_pin", published)
    return AdapterResult(observations, "matched" if observations else "clear", database_date=published)


OPERATIONS = {GITLEAKS: gitleaks, OSV: osv}


def review_source(tool, files):
    try:
        with TemporaryDirectory(prefix="marsad-source-") as scratch:
            return OPERATIONS[tool](files, Path(scratch))
    except AdapterError as exc:
        return AdapterResult([], "error", str(exc))
    except subprocess.TimeoutExpired:
        return AdapterResult([], "error", "adapter_timeout")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return AdapterResult([], "error", "adapter_invalid_output")
