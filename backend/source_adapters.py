"""Pinned classifiers for read-only, submitted source snapshots in the isolated worker."""
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from tempfile import TemporaryDirectory
from types import MappingProxyType
from urllib.parse import unquote, urlsplit


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
NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")
NPM_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?")
JSON_WHITESPACE = re.compile(r"[ \t\r\n]*")
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
SOURCE_TIMEOUTS = MappingProxyType({GITLEAKS.id: 8, OSV.id: 22})


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


def gitleaks_command(directory, report):
    return [
        "dir", str(directory / "snapshot"), "--config", str(directory / "gitleaks.toml"),
        "--gitleaks-ignore-path", str(directory / ".gitleaksignore"), "--ignore-gitleaks-allow",
        "--redact=100", "--no-banner", "--no-color", "--log-level=error",
        "--max-archive-depth=0", "--max-decode-depth=0", "--max-target-megabytes=1",
        "--exit-code=42", "--report-format=json", "--report-path", str(report),
    ]


def osv_command(directory, report, manifests=()):
    return [
        "scan", "source", "--offline", "--no-resolve", "--all-packages",
        "--verbosity=error", "--format=json", "--output-file", str(report), "--config",
        str(directory / "osv-scanner.toml"),
        *(value for path in manifests for value in ("--lockfile", path)),
    ]


def approved_cli(tool, args, directory, report):
    root = directory.resolve()
    if tool is GITLEAKS:
        return (report == directory / "gitleaks.json" and args == gitleaks_command(directory, report)
                and all(path.resolve().is_relative_to(root) for path in (
                    directory / "snapshot", directory / "gitleaks.toml", directory / ".gitleaksignore",
                )))
    if report != directory / "osv.json":
        return False
    prefix = osv_command(directory, report)
    flags = args[len(prefix):]
    manifests = flags[1::2]
    return (args[:len(prefix)] == prefix and bool(manifests) and len(flags) % 2 == 0
            and all(flag == "--lockfile" for flag in flags[::2])
            and (directory / "osv-scanner.toml").resolve().is_relative_to(root)
            and all(Path(path).is_absolute() and Path(path).resolve().is_relative_to(root)
                    for path in manifests))


def run_cli(tool, args, directory, report, *, timeout, success, env=None):
    if not any(tool is registered for registered in SOURCE_TOOLS):
        raise AdapterError("adapter_not_registered")
    if type(timeout) not in (int, float) or not 0 < timeout <= SOURCE_TIMEOUTS[tool.id]:
        raise AdapterError("adapter_budget_exceeded")
    if (not report.resolve().is_relative_to(directory.resolve()) or not approved_cli(tool, args, directory, report)
            or set(env or {}) - {"OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY", "GOMAXPROCS", "GOMEMLIMIT"}):
        raise AdapterError("adapter_execution_denied")
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
    output, code = run_cli(GITLEAKS, gitleaks_command(directory, report), directory, report,
                           timeout=SOURCE_TIMEOUTS[GITLEAKS.id], success={0, 42})
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


@dataclass
class DependencyManifest:
    path: str
    ecosystem: str
    pins: dict[tuple[str, str], tuple[str, int]]


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
            manifests[str(target)] = DependencyManifest(path, "PyPI", rows)
    return manifests, partial


def strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate lockfile key")
        result[key] = value
    return result


def json_members(text, offset):
    decoder = json.JSONDecoder()
    offset = JSON_WHITESPACE.match(text, offset + 1).end()
    while text[offset] != "}":
        key_offset = offset
        key, offset = decoder.raw_decode(text, offset)
        value_offset = JSON_WHITESPACE.match(text, JSON_WHITESPACE.match(text, offset).end() + 1).end()
        yield key, key_offset, value_offset
        _, offset = decoder.raw_decode(text, value_offset)
        end_offset = JSON_WHITESPACE.match(text, offset).end()
        if text[end_offset] == "}":
            return
        offset = JSON_WHITESPACE.match(text, end_offset + 1).end()


def npm_registry_pin(location, descriptor):
    if not location.startswith("node_modules/") or not isinstance(descriptor, dict):
        return None
    modules = location.removeprefix("node_modules/").split("/node_modules/")
    if not all(NPM_NAME.fullmatch(module) for module in modules):
        return None
    name = modules[-1]
    version = descriptor.get("version")
    if (len(name) > 150 or descriptor.get("link", False) is not False or descriptor.get("name", name) != name
            or not isinstance(version, str) or len(version) > 100 or not NPM_VERSION.fullmatch(version)):
        return None
    resolved = descriptor.get("resolved", "")
    if not isinstance(resolved, str):
        return None
    if resolved:
        try:
            url = urlsplit(resolved)
        except ValueError:
            return None
        tarball = f"/{name}/-/{name.rsplit('/', 1)[-1]}-{version}.tgz"
        if (url.scheme != "https" or url.netloc != "registry.npmjs.org"
                or unquote(url.path) != tarball or url.query or url.fragment):
            return None
    return name, version


def npm_inputs(files, directory):
    manifests = {}
    partial = False
    pin_count = 0
    for index, (path, text) in enumerate(sorted(files.items())):
        source = PurePosixPath(path)
        if source.name != "package-lock.json" or {".git", "node_modules"}.intersection(source.parts):
            continue
        try:
            lock = json.loads(text, object_pairs_hook=strict_json_object)
        except (ValueError, RecursionError):
            partial = True
            continue
        if (not isinstance(lock, dict) or type(lock.get("lockfileVersion")) is not int
                or lock["lockfileVersion"] not in (2, 3) or not isinstance(lock.get("packages"), dict)):
            partial = True
            continue
        root_start = JSON_WHITESPACE.match(text).end()
        packages_start = next(offset for key, _, offset in json_members(text, root_start) if key == "packages")
        newlines = [match.start() for match in re.finditer("\n", text)]
        rows = {}
        safe_packages = {}
        for location, offset, _ in json_members(text, packages_start):
            if not location:
                continue
            key = npm_registry_pin(location, lock["packages"][location])
            if key is None:
                partial = True
                continue
            if key in rows:
                continue
            if pin_count >= MAX_OBSERVATIONS:
                partial = True
                break
            name, version = key
            rows[key] = (name, bisect_right(newlines, offset) + 1)
            safe_packages[location] = {"version": version}
            pin_count += 1
        if rows:
            target = directory / str(index) / source.name
            target.parent.mkdir()
            target.write_text(json.dumps({"lockfileVersion": 3, "packages": safe_packages}), encoding="ascii")
            manifests[str(target)] = DependencyManifest(path, "npm", rows)
    return manifests, partial


def database(ecosystem="PyPI"):
    cache = Path(os.environ.get("MARSAD_OSV_DB_DIRECTORY", "/opt/marsad-osv"))
    if not (cache / "osv-scalibr" / ecosystem / "all.zip").is_file():
        raise AdapterError("database_unavailable")
    stamp_name = "npm-database-date" if ecosystem == "npm" else "database-date"
    try:
        with (cache / stamp_name).open("rb") as stamp:
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
    python_manifests, pypi_partial = pypi_inputs(files, directory)
    javascript_manifests, npm_partial = npm_inputs(files, directory)
    manifests = {**python_manifests, **javascript_manifests}
    if not manifests:
        if pypi_partial or npm_partial:
            return AdapterResult([], "error", "unsupported_dependency_pin")
        return AdapterResult([], "not_applicable", "unsupported_input")

    databases = {}
    for ecosystem in sorted({manifest.ecosystem for manifest in manifests.values()}):
        try:
            databases[ecosystem] = database(ecosystem)
        except AdapterError:
            continue
    missing_database = any(manifest.ecosystem not in databases for manifest in manifests.values())
    manifests = {path: manifest for path, manifest in manifests.items() if manifest.ecosystem in databases}
    if not manifests:
        return AdapterResult([], "error", "database_unavailable")
    cache = next(iter(databases.values()))[0]
    oldest_snapshot = min(published for _, published in databases.values())
    config = directory / "osv-scanner.toml"
    config.touch()
    report = directory / "osv.json"
    output, _ = run_cli(OSV, osv_command(directory, report, manifests),
                        directory, report, timeout=SOURCE_TIMEOUTS[OSV.id], success={0, 1}, env={
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
        ecosystem = location.ecosystem
        published = databases[ecosystem][1]
        for entry in package_result["packages"]:
            package = entry["package"]
            canonical_name = pypi_key(package["name"]) if ecosystem == "PyPI" else package["name"]
            key = (canonical_name, package["version"])
            if key not in location.pins or package["ecosystem"] != ecosystem:
                raise AdapterError("adapter_invalid_output")
            seen.add((str(directory / source), key))
            name, line = location.pins[key]
            operator = "==" if ecosystem == "PyPI" else "@"
            for identifier, *aliases in advisory_groups(entry.get("vulnerabilities") or []):
                observations.append({
                    "rule": OSV.rule, "domain": OSV.domain, "line": line, "path": location.path,
                    "title": f"Pinned {ecosystem} dependency matches a known advisory",
                    "title_ar": f"تبعية {ecosystem} مثبّتة تطابق تنبيهًا معروفًا",
                    "evidence": f"{ecosystem} dependency {name}{operator}{key[1]} matches {identifier}.",
                    "remediation": "Review the advisory and upgrade the dependency to an approved fixed version.",
                    "remediation_ar": "راجع التنبيه وحدّث التبعية لإصدار معتمد فيه الإصلاح.",
                    "severity": "medium", "confidence": "high", "assessment": "observed",
                    "origins": [origin(OSV, identifier)],
                    "advisory": {"id": identifier, "aliases": aliases[:30], "ecosystem": ecosystem,
                                 "package": name, "version": key[1], "database_date": published.isoformat()},
                })
                if len(observations) > MAX_OBSERVATIONS:
                    raise AdapterError("adapter_output_limit")
    expected = {(path, key) for path, manifest in manifests.items() for key in manifest.pins}
    if missing_database:
        return AdapterResult(observations, "error", "database_unavailable", oldest_snapshot)
    if pypi_partial or npm_partial or seen != expected:
        return AdapterResult(observations, "error", "unsupported_dependency_pin", oldest_snapshot)
    return AdapterResult(observations, "matched" if observations else "clear", database_date=oldest_snapshot)


OPERATIONS = {GITLEAKS: gitleaks, OSV: osv}


def review_source(tool, files):
    if not any(tool is registered for registered in SOURCE_TOOLS):
        return AdapterResult([], "error", "adapter_not_registered")
    try:
        with TemporaryDirectory(prefix="marsad-source-") as scratch:
            return OPERATIONS[tool](files, Path(scratch))
    except AdapterError as exc:
        return AdapterResult([], "error", str(exc))
    except subprocess.TimeoutExpired:
        return AdapterResult([], "error", "adapter_timeout")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return AdapterResult([], "error", "adapter_invalid_output")
