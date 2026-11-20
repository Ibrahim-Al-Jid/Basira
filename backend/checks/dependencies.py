"""Offline checks for npm manifests, npm lockfile v2/v3, and supplied OSV records."""

from collections import defaultdict
from datetime import datetime
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit


IDS = tuple(f"DEP-{number:02}" for number in range(1, 9))
SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
LOCK_FILES = ("npm-shrinkwrap.json", "package-lock.json")
PACKAGE = re.compile(r"(?:@[a-zA-Z0-9._-]+/)?[a-zA-Z0-9][a-zA-Z0-9._-]*")
ADVISORY = re.compile(r"[A-Z0-9][A-Z0-9_.-]{2,79}")
SEMVER = re.compile(
    r"(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
HOSTED_GIT = re.compile(r"(?:github:|gitlab:|bitbucket:|gist:|git://|git\+|git@|ssh://)", re.IGNORECASE)
GIT_PIN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
JSON_KEY = re.compile(r'"(?:[^"\\]|\\.)+"\s*:')
RULE_TEXT = {
    "DEP-01": ("medium", "Direct dependency matches a supplied advisory", "تبعية مباشرة تطابق تنبيهًا مقدّمًا",
               "Review the advisory and update the pinned direct dependency to a fixed version.",
               "راجع التنبيه وحدّث التبعية المباشرة لإصدار فيه الإصلاح."),
    "DEP-02": ("medium", "Transitive dependency matches a supplied advisory", "تبعية انتقالية تطابق تنبيهًا مقدّمًا",
               "Review the advisory, then update the dependency chain to resolve a fixed version.",
               "راجع التنبيه وحدّث سلسلة التبعيات لإصدار فيه الإصلاح."),
    "DEP-03": ("medium", "npm application lockfile is missing", "ملف قفل تطبيق npm غايب",
               "Generate and commit the lockfile for this deployed application.",
               "ولّد ملف القفل واحفظه مع مصدر التطبيق المنشور."),
    "DEP-04": ("medium", "Dependency source uses HTTP", "مصدر التبعية بيستخدم HTTP",
               "Use an approved HTTPS dependency source.", "استخدم مصدر تبعيات معتمد عبر HTTPS."),
    "DEP-05": ("medium", "Git dependency is not pinned to a commit", "تبعية Git من غير commit ثابت",
               "Pin the dependency to a reviewed full commit ID.", "ثبّت التبعية على معرّف commit كامل ومُراجع."),
    "DEP-06": ("medium", "Registry tarball lacks an integrity digest", "أرشيف الحزمة من غير بصمة سلامة",
               "Use a lockfile with a verified integrity digest for the registry artifact.",
               "استخدم ملف قفل فيه بصمة سلامة متحقّقة لأرشيف الحزمة."),
    "DEP-07": ("medium", "Registry host is outside the allowlist", "مضيف سجل الحزم خارج القائمة المسموح بها",
               "Use an approved registry or review the allowlist.", "استخدم سجل حزم معتمد أو راجع قائمة السماح."),
    "DEP-08": ("medium", "npm lockfile disagrees with the manifest", "ملف قفل npm مختلف عن تعريف التبعيات",
               "Regenerate the npm lockfile from the reviewed package.json.",
               "أعد توليد ملف قفل npm من ملف package.json المُراجع."),
}


def json_object(raw):
    if raw is None:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (ValueError, RecursionError):
        return None


def groups(document):
    return {
        section: {name: spec for name, spec in value.items() if PACKAGE.fullmatch(name) and isinstance(spec, str)}
        for section in SECTIONS if isinstance(value := document.get(section), dict)
    }


def dependencies(document):
    return {name: spec for group in groups(document).values() for name, spec in group.items()}


def line_map(content):
    positions = {}
    for line, text in enumerate(content.splitlines(), start=1):
        for key in JSON_KEY.finditer(text):
            try:
                decoded = json.loads(key[0].rstrip()[:-1])
            except ValueError:
                continue
            positions.setdefault(decoded, line)
    return positions


def record(results, rule, path, line, evidence=None, *, contextual=False):
    if results[rule] is None:
        results[rule] = []
    if evidence is not None:
        severity, title, title_ar, remediation, remediation_ar = RULE_TEXT[rule]
        results[rule].append({
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "confidence": "medium" if contextual else "high",
            "assessment": "review_required" if contextual else "observed",
        })


def url_parts(value):
    if not isinstance(value, str):
        return None
    try:
        result = urlsplit(value)
        _ = result.port
        return result if result.hostname else None
    except ValueError:
        return None


def git_reference(spec):
    ref, _, revision = spec.partition("#")
    url = url_parts(ref)
    standard_git = url and url.scheme in {"http", "https"} and url.path.endswith(".git")
    shorthand = re.fullmatch(r"[\w.-]+/[\w.-]+", ref, re.ASCII) and not ref.startswith((".", "/"))
    if standard_git or shorthand or HOSTED_GIT.match(ref):
        return revision
    return None


def inspect_source(results, path, line, label, spec):
    url = url_parts(spec)
    plain_http = bool(url and url.scheme in {"http", "git+http"})
    record(results, "DEP-04", path, line, f"{label}: explicit dependency source uses HTTP." if plain_http else None)
    revision = git_reference(spec)
    if revision is not None:
        unpinned = not GIT_PIN.fullmatch(revision)
        record(results, "DEP-05", path, line,
               f"{label}: Git reference is not a full commit ID." if unpinned else None, contextual=True)
    return plain_http


def semver(version):
    if not isinstance(version, str) or len(version) > 150 or not (parsed := SEMVER.fullmatch(version)):
        return None
    major, minor, patch, suffix, _build = parsed.groups()
    prerelease = []
    if suffix:
        for part in suffix.split("."):
            if part.isdigit():
                if (len(part) > 1 and part.startswith("0")) or len(part) > 12:
                    return None
                prerelease.append((0, int(part)))
            else:
                prerelease.append((1, part))
    return (int(major), int(minor), int(patch), suffix is None, tuple(prerelease))


def osv_intervals(value):
    if not isinstance(value, dict) or value.get("type") != "SEMVER":
        return []
    events = value.get("events")
    if not isinstance(events, list):
        return []
    ranges = []
    start = None
    for event in events:
        if not isinstance(event, dict) or len(event) != 1:
            return []
        kind, raw = next(iter(event.items()))
        boundary = (0, 0, 0, False, ()) if kind == "introduced" and raw == "0" else semver(raw)
        if boundary is None:
            return []
        if kind == "introduced" and start is None:
            start = boundary
        elif kind in {"fixed", "last_affected", "limit"} and start is not None and boundary >= start:
            ranges.append((start, boundary, kind == "last_affected"))
            start = None
        else:
            return []
    if start is not None:
        ranges.append((start, None, False))
    return ranges


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def advisory_index(records):
    indexed = defaultdict(list)
    record_available = False
    for entry in records:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ADVISORY.fullmatch(entry["id"]):
            continue
        if entry.get("withdrawn") or not timestamp(entry.get("modified")):
            continue
        affected = entry.get("affected")
        if not isinstance(affected, list):
            continue
        for item in affected:
            package = item.get("package") if isinstance(item, dict) else None
            if not isinstance(package, dict) or package.get("ecosystem") != "npm":
                continue
            name = package.get("name")
            versions, ranges = item.get("versions"), item.get("ranges")
            versions = [v for v in versions if semver(v)] if isinstance(versions, list) else []
            intervals = [interval for value in ranges for interval in osv_intervals(value)] if isinstance(ranges, list) else []
            if isinstance(name, str) and PACKAGE.fullmatch(name) and (versions or intervals):
                indexed[name].append((entry["id"], set(versions), intervals))
                record_available = True
    return indexed if record_available else None


def advisories_for(index, name, version):
    parsed = semver(version)
    return {
        advisory for advisory, versions, intervals in index.get(name, ())
        if version in versions or any(
            lower <= parsed and (upper is None or parsed < upper or inclusive and parsed == upper)
            for lower, upper, inclusive in intervals
        )
    }


def registry_url(url, name):
    if url is None or url.scheme not in {"http", "https"}:
        return False
    # Match the registry tarball convention, including scoped package names.
    path = unquote(url.path)
    prefix = f"/{name}/-/{name.rsplit('/', 1)[-1]}-"
    return prefix in path and path.endswith(".tgz")


def direct_locations(packages):
    found = set()
    for location, data in packages.items():
        if not isinstance(data, dict) or "node_modules/" in location:
            continue
        directories = PurePosixPath(location).parents
        for name in dependencies(data):
            for base in (location, *(str(p) for p in directories)):
                candidate = f"{base}/node_modules/{name}" if base not in ("", ".") else f"node_modules/{name}"
                if candidate in packages:
                    found.add(candidate)
                    break
    return found


def inspect_lock(results, path, content, packages, manifest, osv, registry_allowlist):
    line_by_key = line_map(content)
    root = packages.get("")
    if manifest is not None and isinstance(root, dict):
        requested, locked = groups(manifest), groups(root)
        changed = [name for name in SECTIONS if requested.get(name, {}) != locked.get(name, {})]
        evidence = f"Manifest and npm lockfile root differ in {', '.join(changed)}." if changed else None
        record(results, "DEP-08", path, 1, evidence)
    direct = direct_locations(packages)
    affected = {}
    for key, data in packages.items():
        if "node_modules/" not in key or not isinstance(data, dict) or data.get("link") is True:
            continue
        label = key.rsplit("node_modules/", 1)[-1]
        if not PACKAGE.fullmatch(label):
            continue
        name = data.get("name", label)
        if not isinstance(name, str) or not PACKAGE.fullmatch(name):
            continue
        line = line_by_key.get(key, 1)
        resolved = data.get("resolved")
        plain_http = False
        if isinstance(resolved, str):
            plain_http = inspect_source(results, path, line, name, resolved)
        url = url_parts(resolved)
        if registry_url(url, name):
            integrity = data.get("integrity")
            digest_missing = not isinstance(integrity, str) or not integrity.strip()
            record(results, "DEP-06", path, line, f"{name}: registry tarball has no integrity digest." if digest_missing else None)
            if registry_allowlist is not None and not plain_http:
                record(results, "DEP-07", path, line,
                       f"{name}: registry host is outside the configured allowlist."
                       if url.hostname not in registry_allowlist else None)
        version = data.get("version")
        if osv is None or not isinstance(root, dict) or not semver(version):
            continue
        # Match package ecosystem records only for registry tarballs or lock
        # entries without a source URL, not for forks and custom archives.
        if resolved is not None and not registry_url(url, name):
            continue
        rule = "DEP-01" if key in direct else "DEP-02"
        record(results, rule, path, line)
        for advisory in advisories_for(osv, name, version):
            identifier = name, version, advisory
            old = affected.get(identifier)
            if old is None or (old[0] == "DEP-02" and rule == "DEP-01"):
                affected[identifier] = rule, line
    for (name, version, advisory), (rule, line) in sorted(affected.items()):
        record(results, rule, path, line, f"npm lockfile pins {name}@{version}; matches advisory {advisory}.")


def npm_manifest(manifest, root, files):
    manager = manifest.get("packageManager")
    if isinstance(manager, str):
        return manager.startswith("npm@")
    return not any(str(root / other) in files for other in ("yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"))


def covered_workspace(directory, manifests):
    for parent in directory.parents:
        root = manifests.get(parent) or {}
        workspaces = root.get("workspaces")
        if isinstance(workspaces, list) and any(
            directory.relative_to(parent).full_match(pattern.removeprefix("./").rstrip("/"))
            for pattern in workspaces if isinstance(pattern, str) and pattern.removeprefix("./").rstrip("/")
        ):
            return True
    return False


def check(text_inputs, har, policy, advisories):
    results = dict.fromkeys(IDS)
    osv = advisory_index(advisories or [])
    allowed = policy.get("registry_allowlist")
    registry_allowlist = {value.lower() for value in allowed if isinstance(value, str)} if isinstance(allowed, list) else None
    manifests = {}
    for path, content in text_inputs.items():
        file = PurePosixPath(path)
        if file.name != "package.json" or not (manifest := json_object(content)):
            continue
        manifests[file.parent] = manifest
        positions = line_map(content)
        for name, spec in dependencies(manifest).items():
            inspect_source(results, path, positions.get(name, 1), name, spec)
    for directory, manifest in manifests.items():
        if (policy.get("application") is True and policy.get("repository_complete") is True
                and npm_manifest(manifest, directory, text_inputs) and not covered_workspace(directory, manifests)):
            missing = not any(str(directory / lockfile) in text_inputs for lockfile in LOCK_FILES)
            record(results, "DEP-03", str(directory / "package.json"), 1,
                   "Complete npm application snapshot lacks a lockfile." if missing else None)
    for path, content in text_inputs.items():
        file = PurePosixPath(path)
        if file.name not in LOCK_FILES:
            continue
        if file.name == "package-lock.json" and str(file.parent / "npm-shrinkwrap.json") in text_inputs:
            continue
        lock = json_object(content)
        if lock and lock.get("lockfileVersion") in (2, 3) and isinstance(lock.get("packages"), dict):
            inspect_lock(results, path, content, lock["packages"], manifests.get(file.parent), osv, registry_allowlist)
    return results
