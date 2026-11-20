"""Extra offline checks for npm, Kubernetes, GitHub Actions and app settings."""

import ast
import base64
import binascii
from pathlib import PurePosixPath
import re
from urllib.parse import unquote
import warnings

from yaml.nodes import ScalarNode, SequenceNode

from . import config, dependencies as npm


TEXT = {
    "DEP-09": ("high", "npm disables registry certificate validation", "التحقق من شهادة سجل npm معطّل",
               "Enable strict-ssl and configure any needed trust chain.", "فعّل strict-ssl واضبط سلسلة الشهادات الموثوقة."),
    "DEP-10": ("high", "Locked URL embeds authentication", "عنوان حزمة في ملف القفل يحتوي على اعتماد",
               "Remove embedded credentials and use a scoped registry secret.", "احذف بيانات الاعتماد من العنوان واستخدم سرًّا خاصًّا بالسجل."),
    "DEP-11": ("high", "npm config stores literal registry credentials", "إعداد npm يخزّن اعتماد السجل كنص صريح",
               "Reference a protected secret and rotate exposed credentials.", "استخدم مرجع سر محمي ودوّر بيانات الاعتماد المكشوفة."),
    "DEP-12": ("medium", "Direct dependency allows any release", "تبعية مباشرة تسمح بأي إصدار",
               "Use a reviewed version constraint and keep the lockfile current.", "استخدم نطاق إصدارات مُراجع وحدّث ملف القفل."),
    "DEP-13": ("high", "Package allows public publishing against policy", "إعداد الحزمة يسمح بالنشر العام خلافًا للسياسة",
               "Make the package private or use the authorized restricted registry policy.", "اجعل الحزمة خاصة أو استخدم سياسة التسجيل المقيّدة المعتمدة."),
    "DEP-14": ("medium", "Local dependency points outside the submitted repository", "تبعية محلية تشير لمسار خارج المستودع المرفوع",
               "Keep the local dependency inside the reviewed repository or use an approved package source.", "خلي التبعية المحلية داخل المستودع المُراجع أو استخدم مصدر حزم معتمد."),
    "DEP-15": ("medium", "Registry package integrity relies on SHA-1 only", "سلامة حزمة السجل تعتمد على SHA-1 فقط",
               "Refresh the lockfile with a verified SHA-256 or stronger integrity digest.", "حدّث ملف القفل ببصمة متحقّقة SHA-256 أو أقوى."),
    "DEP-16": ("low", "Direct locked dependency is marked deprecated", "تبعية مباشرة مثبتة ومعلّمة كموقوفة",
               "Review the maintainer guidance and plan a supported replacement.", "راجع إرشادات القائم بالصيانة وخطّط لاستخدام تبعية مدعومة."),
    "INF-11": ("high", "Pod shares the host IPC namespace", "الـPod يشارك مساحة IPC للمضيف",
               "Disable hostIPC unless explicitly approved.", "عطّل hostIPC إلا لو فيه استثناء معتمد."),
    "INF-12": ("medium", "Container requests an unapproved host port", "الحاوية تطلب منفذ مضيف غير معتمد",
               "Use a Service for exposure or limit hostPort to an approved value.", "استخدم Service لعرض الاتصال أو قيّد hostPort بقيمة معتمدة."),
    "INF-13": ("high", "Container requests an unmasked proc filesystem", "الحاوية تطلب نظام proc بدون حجب",
               "Use the default procMount masking.", "استخدم حجب procMount الافتراضي."),
    "INF-14": ("high", "Container has an unconfined seccomp profile", "الحاوية بإعداد seccomp غير مقيّد",
               "Set RuntimeDefault or an approved Localhost seccomp profile.", "حدّد RuntimeDefault أو إعداد seccomp من Localhost معتمد."),
    "INF-15": ("medium", "Container explicitly permits writes to its root filesystem", "الحاوية تسمح صراحةً بالكتابة في نظام الملفات الجذري",
               "Set readOnlyRootFilesystem and mount scoped writable volumes as needed.", "فعّل readOnlyRootFilesystem وركّب وحدات كتابة محددة عند الحاجة."),
    "INF-16": ("high", "Container config resolves to root UID", "إعداد الحاوية يحدد UID للمستخدم root",
               "Set a dedicated non-root runAsUser and enforce runAsNonRoot.", "حدّد مستخدم تشغيل غير root وفعّل runAsNonRoot."),
    "INF-17": ("medium", "Pod automatically mounts service-account credentials", "الـPod يركّب اعتماد حساب الخدمة تلقائيًا",
               "Disable automatic credential mounting and grant scoped credentials only if needed.", "عطّل التركيب التلقائي وامنح اعتماد بإذن محدود عند الحاجة."),
    "INF-18": ("high", "Pod sets a sysctl forbidden by policy", "الـPod يضبط sysctl محظور حسب السياسة",
               "Remove the disallowed sysctl or review a narrowly scoped exception.", "احذف إعداد sysctl المحظور أو راجع استثناء محدود."),
    "CI-07": ("high", "Reusable workflow receives inherited secrets", "الـWorkflow القابل لإعادة الاستخدام يرث الأسرار",
              "Pass only the secrets the reviewed workflow needs.", "مرّر الأسرار اللازمة فقط للـWorkflow المُراجع."),
    "CI-08": ("high", "Pull request workflow uses a self-hosted runner", "Workflow لطلب دمج يستخدم runner مستضافًا ذاتيًا",
              "Run untrusted changes on an isolated hosted runner or review the trust boundary.", "شغّل التغييرات غير الموثوقة على runner معزول أو راجع حدود الثقة."),
    "CI-09": ("medium", "Workflow job timeout exceeds policy", "مهلة مهمة الـWorkflow تتجاوز السياسة",
              "Set a job timeout within the approved resource budget.", "اضبط مهلة المهمة داخل ميزانية الموارد المعتمدة."),
    "CI-10": ("high", "Required workflow job allows failure", "مهمة Workflow مطلوبة تسمح بتجاهل الفشل",
              "Make failures in the required job block the workflow.", "خلّي فشل المهمة المطلوبة يوقف الـWorkflow."),
    "APP-07": ("high", "Node TLS certificate verification is disabled", "التحقق من شهادات TLS في Node متعطّل",
               "Remove the override and configure the trusted certificate chain.", "احذف الإعداد اللي بيعطّل التحقق واضبط سلسلة الشهادات الموثوقة."),
    "APP-08": ("medium", "Session cookie explicitly disables HttpOnly", "إعداد الكوكي يعطّل HttpOnly صراحةً",
               "Enable HttpOnly for session cookies.", "فعّل HttpOnly لكوكي الجلسة."),
    "APP-09": ("medium", "Django host allowlist admits all hosts", "قائمة مضيفي Django بتسمح بكل المضيفين",
               "Declare the hostnames that serve the application.", "حدّد أسماء المضيفين اللي بيقدّموا التطبيق."),
    "APP-10": ("high", "Django CORS allows all origins with credentials", "إعداد CORS يسمح بكل الأصول مع بيانات الاعتماد",
               "Restrict allowed origins and enable credentialed access only where required.", "قيّد الأصول المسموح بها وفعّل مرور بيانات الاعتماد عند الحاجة فقط."),
    "APP-11": ("high", "Flask-WTF explicitly disables CSRF protection", "Flask-WTF يعطّل حماية CSRF صراحةً",
               "Enable Flask-WTF CSRF protection and test form submissions.", "فعّل حماية CSRF في Flask-WTF واختبر إرسال النماذج."),
}


class Results:
    def __init__(self):
        self.matches = dict.fromkeys(TEXT)
        self.seen = set()

    def record(self, rule, path, line, evidence=None, *, review=False):
        if self.matches[rule] is None:
            self.matches[rule] = []
        if evidence is None or (key := (rule, path, line, evidence)) in self.seen:
            return
        self.seen.add(key)
        severity, title, title_ar, remediation, remediation_ar = TEXT[rule]
        self.matches[rule].append({
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "confidence": "medium" if review else "high", "assessment": "review_required" if review else "observed",
        })


def npmrc_settings(content):
    settings = {}
    for line, raw in enumerate(content.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        key, equals, value = stripped.partition("=")
        if not equals:
            continue
        if (quoted := re.fullmatch(r"""\s*(['"])(.*?)\1\s*(?:[;#].*)?""", value)):
            value = quoted[2]
        else:
            value = re.split(r"\s+[;#]", value, maxsplit=1)[0].strip()
        settings[key.strip().casefold()] = (line, value)
    return settings


def literal_secret(value):
    return not config.is_placeholder(value) and not re.search(r"\$\{[^}]+}", value)


def check_npmrc(path, content, results):
    for key, (line, value) in npmrc_settings(content).items():
        if key == "strict-ssl":
            results.record("DEP-09", path, line,
                           "npm is configured to skip registry certificate validation."
                           if config.false_value(value) else None)
        elif key.rsplit(":", 1)[-1] in {"_auth", "_authtoken", "_password"}:
            results.record("DEP-11", path, line,
                           "A registry authentication field contains a literal value."
                           if literal_secret(value) else None)


def outside_repository(path, spec):
    local = unquote(spec.partition(":")[2]).replace("\\", "/")
    if not local or local.startswith(("/", "~", "$")) or re.match(r"^[A-Za-z]:", local):
        return bool(local and not local.startswith("$"))
    depth = len(PurePosixPath(path).parent.parts)
    for part in local.split("/"):
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        elif part not in ("", "."):
            depth += 1
    return False


def check_manifest(path, content, files, policy, results):
    manifest = npm.json_object(content)
    if manifest is None or not npm.npm_manifest(manifest, PurePosixPath(path).parent, files):
        return
    positions = npm.line_map(content)
    groups = npm.groups(manifest)
    required = {**groups.get("dependencies", {}), **groups.get("optionalDependencies", {})}
    for name, spec in required.items():
        unrestricted = re.fullmatch(r"(?:latest|[xX*](?:\.[xX*]){0,2})?", spec.strip())
        results.record("DEP-12", path, positions.get(name, 1),
                       "A direct production dependency has an unrestricted version selector." if unrestricted else None)
    if policy.get("repository_complete") is True:
        for name, spec in npm.dependencies(manifest).items():
            if spec.startswith(("file:", "link:")):
                results.record("DEP-14", path, positions.get(name, 1),
                               "A local dependency resolves beyond the supplied repository root."
                               if outside_repository(path, spec) else None)
    publish = manifest.get("publishConfig")
    if policy.get("npm_require_private_package") is True and isinstance(publish, dict) and "access" in publish:
        public = publish["access"] == "public" and manifest.get("private") is not True
        results.record("DEP-13", path, positions.get("access", 1),
                       "Publishing access is explicitly public despite the private-package policy." if public else None)


def viable_sri_algorithms(value):
    lengths = {"sha1": 20, "sha256": 32, "sha384": 48, "sha512": 64}
    if not isinstance(value, str):
        return set()
    found = set()
    for item in value.split():
        algorithm, _, digest = item.partition("?")[0].partition("-")
        if algorithm not in lengths or not digest:
            continue
        try:
            decoded = base64.b64decode(digest, validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(decoded) == lengths[algorithm]:
            found.add(algorithm)
    return found


def check_lock(path, content, files, results):
    file = PurePosixPath(path)
    if file.name == "package-lock.json" and str(file.parent / "npm-shrinkwrap.json") in files:
        return
    lock = npm.json_object(content)
    if not lock or lock.get("lockfileVersion") not in (2, 3) or not isinstance(lock.get("packages"), dict):
        return
    packages = lock["packages"]
    positions = npm.line_map(content)
    direct = npm.direct_locations(packages)
    for key, data in packages.items():
        if "node_modules/" not in key or not isinstance(data, dict) or data.get("link") is True:
            continue
        name = data.get("name", key.rsplit("node_modules/", 1)[-1])
        if not isinstance(name, str) or not npm.PACKAGE.fullmatch(name):
            continue
        line = positions.get(key, 1)
        url = npm.url_parts(data.get("resolved"))
        if url and url.scheme in {"http", "https"}:
            username = unquote(url.username or "")
            password = unquote(url.password or "")
            username_only = url.password is None and literal_secret(username)
            embedded = literal_secret(password) or username_only
            results.record("DEP-10", path, line,
                           "The locked package URL contains literal URL authentication." if embedded else None,
                           review=username_only)
        if npm.registry_url(url, name):
            algorithms = viable_sri_algorithms(data.get("integrity"))
            if algorithms:
                results.record("DEP-15", path, line,
                               "The only valid integrity algorithm recorded for this registry package is SHA-1."
                               if algorithms == {"sha1"} else None)
            if key in direct:
                deprecated = data.get("deprecated")
                results.record("DEP-16", path, line,
                               "The resolved direct registry version has a deprecation marker in the lockfile."
                               if isinstance(deprecated, str) and deprecated.strip() else None, review=True)


def yaml_false(node):
    return (isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:bool"
            and node.value.lower() in {"false", "no", "off"})


def yaml_integer(node):
    if (isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:int"
            and re.fullmatch(r"(?:0|[1-9][0-9]{0,9})", node.value)):
        return int(node.value)
    return None


def check_pod(path, pod, policy, results):
    spec = config.members(pod)
    containers = [
        config.members(node) for collection in ("containers", "initContainers", "ephemeralContainers")
        for node in config.sequence(spec.get(collection))
    ]
    if not any(containers):
        return
    if (ipc := spec.get("hostIPC")) is not None:
        if config.yaml_true(ipc) or yaml_false(ipc):
            results.record("INF-11", path, config.source_line(ipc),
                           "Pod explicitly joins the host IPC namespace." if config.yaml_true(ipc) else None)
    else:
        results.record("INF-11", path, config.source_line(pod))
    if policy.get("kubernetes_forbid_service_account_token") is True and (token := spec.get("automountServiceAccountToken")):
        if config.yaml_true(token) or yaml_false(token):
            results.record("INF-17", path, config.source_line(token),
                           "Pod explicitly enables automatic service account credential mounting."
                           if config.yaml_true(token) else None, review=True)
    pod_security = config.members(spec.get("securityContext"))
    forbidden = {name.replace("/", ".") for name in config.config_list(policy, "kubernetes_forbidden_sysctls")}
    if forbidden:
        results.record("INF-18", path, config.source_line(pod))
        for value in config.sequence(pod_security.get("sysctls")):
            name = config.members(value).get("name")
            if (config.scalar(name) or "").replace("/", ".") in forbidden:
                results.record("INF-18", path, config.source_line(name), "Pod defines a sysctl forbidden by policy.")
    host_ports = policy.get("kubernetes_allowed_host_ports")
    allowed = {value for value in host_ports if type(value) is int and 1 <= value <= 65535} if isinstance(host_ports, list) else set()
    for container in filter(None, containers):
        check_container(path, container, pod_security, allowed, policy, results)


def check_container(path, container, pod_security, allowed_ports, policy, results):
    for value in config.sequence(container.get("ports")):
        port = config.members(value).get("hostPort")
        host_port = yaml_integer(port)
        if host_port is not None and 0 <= host_port <= 65535:
            results.record("INF-12", path, config.source_line(port),
                           "Container declares a hostPort that is outside the approved set."
                           if host_port and host_port not in allowed_ports else None)
    security = config.members(container.get("securityContext"))
    proc_mount = security.get("procMount")
    if config.scalar(proc_mount) in {"Default", "Unmasked"}:
        results.record("INF-13", path, config.source_line(proc_mount),
                       "Container explicitly opts out of proc filesystem masking."
                       if config.scalar(proc_mount) == "Unmasked" else None)
    profile = config.members(security.get("seccompProfile", pod_security.get("seccompProfile"))).get("type")
    if config.scalar(profile) in {"Unconfined", "RuntimeDefault", "Localhost"}:
        results.record("INF-14", path, config.source_line(profile),
                       "Container's effective authored seccomp profile is Unconfined."
                       if config.scalar(profile) == "Unconfined" else None)
    readonly = security.get("readOnlyRootFilesystem")
    if (policy.get("kubernetes_require_read_only_root") is True and
            (config.yaml_true(readonly) or yaml_false(readonly))):
        results.record("INF-15", path, config.source_line(readonly),
                       "Container explicitly disables its read-only root filesystem."
                       if yaml_false(readonly) else None, review=True)
    user = security.get("runAsUser", pod_security.get("runAsUser"))
    run_as_non_root = security.get("runAsNonRoot", pod_security.get("runAsNonRoot"))
    if (uid := yaml_integer(user)) is not None:
        results.record("INF-16", path, config.source_line(user),
                       "The authored security context sets root UID with no explicit non-root enforcement."
                       if uid == 0 and not config.yaml_true(run_as_non_root) else None)


def event_names(node):
    if isinstance(node, ScalarNode):
        return {config.scalar(node)}
    if isinstance(node, SequenceNode):
        return {config.scalar(item) for item in config.sequence(node)}
    return set(config.members(node))


def self_hosted_runner(node):
    labels = config.members(node).get("labels", node)
    return config.scalar(labels) == "self-hosted" or any(
        config.scalar(label) == "self-hosted" for label in config.sequence(labels)
    )


def check_workflows(path, documents, policy, results):
    max_timeout = policy.get("ci_max_job_timeout_minutes")
    required_jobs = config.config_list(policy, "ci_required_jobs")
    for document in documents:
        workflow = config.members(document)
        events = event_names(workflow.get("on"))
        pull_request = bool(events & {"pull_request", "pull_request_target"})
        for job_id, job_node in config.members(workflow.get("jobs")).items():
            job = config.members(job_node)
            if config.scalar(job.get("uses")) and policy.get("ci_forbid_secret_inheritance") is True:
                inherited = job.get("secrets")
                results.record("CI-07", path, config.source_line(inherited if inherited is not None else job_node),
                               "Reusable workflow job inherits the caller's secrets."
                               if config.scalar(inherited) == "inherit" else None)
            runner = job.get("runs-on")
            if runner is not None:
                if pull_request:
                    results.record("CI-08", path, config.source_line(runner),
                                   "A pull request workflow declares a self-hosted runner label."
                                   if self_hosted_runner(runner) else None, review=True)
                if type(max_timeout) is int and max_timeout > 0:
                    limit = job.get("timeout-minutes")
                    if limit is None:
                        limit_value = 360
                    else:
                        limit_value = yaml_integer(limit)
                    if limit_value is not None and limit_value > 0:
                        results.record("CI-09", path, config.source_line(limit if limit is not None else job_node),
                                       "An explicit or default job timeout exceeds the configured maximum."
                                       if limit_value > max_timeout else None)
            if job_id in required_jobs:
                allow_failure = job.get("continue-on-error")
                if allow_failure is None or config.yaml_true(allow_failure) or yaml_false(allow_failure):
                    results.record("CI-10", path, config.source_line(allow_failure if allow_failure is not None else job_node),
                                   "A policy-required job explicitly allows failed execution."
                                   if config.yaml_true(allow_failure) else None)


def check_allowed_hosts(path, content, results):
    """Read Django's literal ALLOWED_HOSTS list without importing settings."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            root = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError):
        return
    assignment = None
    for item in root.body:
        if isinstance(item, ast.Assign):
            targets = item.targets
        elif isinstance(item, (ast.AnnAssign, ast.AugAssign)):
            targets = [item.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == "ALLOWED_HOSTS" for target in targets):
            assignment = None if isinstance(item, ast.AugAssign) else item
    if assignment is None or not isinstance(assignment.value, (ast.List, ast.Tuple)):
        return
    values = assignment.value.elts
    if all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in values):
        results.record("APP-09", path, assignment.lineno,
                       "Django's literal ALLOWED_HOSTS list includes the universal wildcard."
                       if any(value.value == "*" for value in values) else None, review=True)


def check_settings(path, values, results):
    node_tls = values.get("NODE_TLS_REJECT_UNAUTHORIZED")
    if node_tls is not None and (isinstance(node_tls.value, str) or type(node_tls.value) is int):
        results.record("APP-07", path, node_tls.line,
                       "Node's TLS certificate verification override is explicitly zero."
                       if str(node_tls.value) == "0" else None)
    for key in ("SESSION_COOKIE_HTTPONLY", "SERVER_SERVLET_SESSION_COOKIE_HTTP_ONLY"):
        setting = values.get(key)
        if setting is not None and (config.true_value(setting.value) or config.false_value(setting.value)):
            results.record("APP-08", path, setting.line,
                           "Application configuration explicitly sets HttpOnly to false for a session cookie."
                           if config.false_value(setting.value) else None)
    all_origins = values.get("CORS_ALLOW_ALL_ORIGINS", values.get("CORS_ORIGIN_ALLOW_ALL"))
    credentials = values.get("CORS_ALLOW_CREDENTIALS")
    if all_origins is not None and credentials is not None:
        interpreted = all(config.true_value(setting.value) or config.false_value(setting.value)
                          for setting in (all_origins, credentials))
        if interpreted:
            results.record("APP-10", path, credentials.line,
                           "The application's authored CORS policy permits all origins with credentials."
                           if config.true_value(all_origins.value) and config.true_value(credentials.value) else None)
    csrf = values.get("WTF_CSRF_ENABLED")
    if csrf is not None and (config.true_value(csrf.value) or config.false_value(csrf.value)):
        results.record("APP-11", path, csrf.line,
                       "Flask-WTF's explicit configuration disables CSRF protection."
                       if config.false_value(csrf.value) else None)


def check_application(path, content, documents, policy, results):
    file = PurePosixPath(path)
    if "fixtures" in file.parts or config.path_selected(path, config.config_list(policy, "fixture_paths")):
        return
    if file.suffix == ".py":
        check_allowed_hosts(path, content, results)
    for settings in config.config_settings(path, content, documents):
        check_settings(path, settings, results)


def check(text_inputs, har, policy, advisories):
    """Return all supported rule IDs with sanitized matches and applicability."""
    results = Results()
    for path, content in text_inputs.items():
        name = PurePosixPath(path).name
        if name == ".npmrc":
            check_npmrc(path, content, results)
        elif name == "package.json":
            check_manifest(path, content, text_inputs, policy, results)
        elif name in npm.LOCK_FILES:
            check_lock(path, content, text_inputs, results)
        documents = config.yaml_documents(content) if name.casefold().endswith((".json", ".yaml", ".yml")) else []
        for document in documents:
            for pod in config.pod_specs(document):
                check_pod(path, pod, policy, results)
        if config.workflow_path(path):
            check_workflows(path, documents, policy, results)
        check_application(path, content, documents, policy, results)
    return results.matches
