"""Offline checks for explicit CI, deployment and application configuration.

Optional policy keys: snapshot_complete, require_image_digest,
require_s3_public_access_block, hostpath_exemptions, forbidden_capabilities,
tenant_tables, ci_require_pinned_actions, ci_write_permissions,
ci_disable_checkout_credentials, protected_branches, fixture_paths,
production_paths, session_cookie_keys. See the relevant check for input shape.

Branch policy compares complete local `.marsad/branch-protection.json` exports
with policy `protected_branches`; each maps branch names to
`{"required_approvals": 2, "required_checks": ["verify"]}` declarations.
The snapshot stores the observed mapping under `branches` and `complete: true`.
Terraform AWS S3 checks support `.tf.json` modules and static bucket references.
The Postgres RLS check supports explicit static migrations ordered by path.
Neither evaluates templates or infers effective runtime environment settings.
"""

import ast
from base64 import b64decode
from binascii import Error as Base64Error
from collections import deque
from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
from pathlib import PurePosixPath
import re
import shlex
from urllib.parse import unquote, urlsplit
import warnings

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


INF_RULES = tuple(f"INF-{index:02}" for index in range(1, 11))
CI_RULES = tuple(f"CI-{index:02}" for index in range(1, 7))
APP_RULES = tuple(f"APP-{index:02}" for index in range(1, 7))

DESCRIPTIONS = {
    "INF-01": ("high", "Final image runs as root", "صورة الحاوية النهائية تعمل كـroot",
               "Set a dedicated non-root user in the runtime stage.", "حدّد مستخدم تشغيل مخصص بصلاحيات محدودة."),
    "INF-02": ("medium", "Base image has no fixed digest", "صورة الأساس بدون بصمة ثابتة",
               "Pin the image to a verified SHA-256 digest.", "ثبّت صورة الأساس ببصمة SHA-256 متحقق منها."),
    "INF-03": ("high", "Privileged Kubernetes container", "حاوية Kubernetes بوضع privileged",
               "Disable privileged mode and grant only required capabilities.", "عطّل وضع privileged وحدّد القدرات المطلوبة فقط."),
    "INF-04": ("high", "Pod shares the host network", "Pod يشارك شبكة المضيف",
               "Disable host networking unless an approved workload requires it.", "عطّل مشاركة شبكة المضيف للـPod إلا في حالة معتمدة."),
    "INF-05": ("high", "Pod shares the host PID namespace", "Pod يشارك عمليات المضيف",
               "Disable host PID namespace sharing.", "عطّل مشاركة مساحة عمليات المضيف."),
    "INF-06": ("medium", "Pod mounts an unapproved host path", "Pod يركب مسار مضيف غير مصرح",
               "Use a managed volume or review and narrowly approve the required mount.", "استخدم وحدة تخزين مُدارة أو راجع وقيّد المسار المطلوب."),
    "INF-07": ("high", "Pod adds a capability forbidden by policy", "Pod يضيف قدرة محظورة",
               "Drop forbidden capabilities and retain only approved ones.", "احذف القدرات المحظورة واحتفظ بالمعتمدة فقط."),
    "INF-08": ("high", "Container permits privilege escalation", "الحاوية تسمح برفع الصلاحيات",
               "Set allowPrivilegeEscalation to false.", "اضبط allowPrivilegeEscalation على false."),
    "INF-09": ("medium", "Bucket public-access block needs review", "حجب الوصول العام لحاوية S3 محتاج مراجعة",
               "Verify account protection and configure all required bucket-level public access blocks.",
               "تحقّق من حماية الحساب وفعّل إعدادات حجب الوصول العام المطلوبة للحاوية."),
    "INF-10": ("high", "Tenant table row policy needs review", "سياسة الصفوف لجدول المستأجرين تحتاج مراجعة",
               "Enable row-level security and verify the tenant policy under the real application role.",
               "فعّل أمان الصفوف واختبر عزل المستأجرين بصلاحيات التطبيق الفعلية."),
    "CI-01": ("medium", "External action is not pinned to a commit", "Action خارجية بدون commit ثابت",
              "Pin the external action to a trusted full commit hash.", "ثبّت الـAction ببصمة commit كاملة وموثوقة."),
    "CI-02": ("high", "Workflow token has write-all permissions", "توكن Workflow بصلاحيات كتابة عامة",
              "Grant read-only defaults and narrowly scoped writes per job.", "استخدم القراءة افتراضيًا وحدّد الكتابة المطلوبة لكل مهمة."),
    "CI-03": ("high", "Job writes outside its approved scopes", "المهمة تتجاوز صلاحيات الكتابة المعتمدة",
              "Remove excess write scopes or approve the minimum needed by this job.", "احذف الصلاحيات الزائدة أو وافق على أقل صلاحية مطلوبة."),
    "CI-04": ("medium", "Checkout credentials may persist", "اعتماد الـCheckout قد يفضل محفوظًا",
              "Disable persist-credentials where the job does not require authenticated Git operations.",
              "عطّل persist-credentials للمهام اللي مش محتاجة تشغيل Git باعتماد."),
    "CI-05": ("medium", "Branch protection has too few required approvals", "الفرع المحمي يتطلب مراجعات أقل من السياسة",
              "Require the approved number of reviews before merging.", "اضبط عدد الموافقات المطلوب قبل الدمج حسب السياسة."),
    "CI-06": ("medium", "Branch protection omits a required check", "الفرع المحمي ينقصه فحص إلزامي",
              "Restore required CI checks on the protected branch.", "أضف فحوصات CI المطلوبة للفرع المحمي."),
    "APP-01": ("high", "Private-key marker in a submitted file", "علامة مفتاح خاص في ملف مرفوع",
               "Remove the key from the source and rotate it if it was used.", "احذف المفتاح من المصدر ودوّره لو كان مستخدم."),
    "APP-02": ("high", "Provider token signature in a submitted file", "بصمة توكن مزوّد في ملف مرفوع",
               "Remove the value from the file and revoke or rotate any exposed token.", "احذف القيمة وأبطل أو دوّر التوكن المكشوف."),
    "APP-03": ("high", "Connection URL embeds credentials", "رابط الاتصال يحتوي على بيانات اعتماد",
               "Read connection credentials from the deployment's secret store.", "اقرأ بيانات اعتماد الاتصال من مخزن أسرار النشر."),
    "APP-04": ("medium", "Production debug mode is enabled", "وضع Debug مفعّل في إعدادات الإنتاج",
               "Disable debug mode in the production profile.", "عطّل وضع Debug في إعدادات الإنتاج."),
    "APP-05": ("medium", "Cross-site session cookie is missing Secure", "كوكي الجلسة عبر المواقع بدون Secure",
               "Enable Secure and confirm that cross-site cookies are necessary.", "فعّل Secure وتأكد من الحاجة للكوكي عبر المواقع."),
    "APP-06": ("high", "TLS keystore password is stored in clear text", "كلمة مرور مخزن TLS مكتوبة بنص صريح",
               "Use a secret reference and rotate any deployed password that was exposed.", "استخدم مرجع سر ودوّر أي كلمة مرور منشورة اتكشفت."),
}


class Results:
    def __init__(self):
        self.matches = dict.fromkeys(INF_RULES + CI_RULES + APP_RULES)
        self.seen = set()

    def applicable(self, *rules):
        for rule in rules:
            if self.matches[rule] is None:
                self.matches[rule] = []

    def add(self, rule, path, line, evidence, *, review=False):
        self.applicable(rule)
        key = (rule, path, line, evidence)
        if key in self.seen:
            return
        self.seen.add(key)
        severity, title, title_ar, remediation, remediation_ar = DESCRIPTIONS[rule]
        match = {
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "assessment": "review_required" if review else "observed", "confidence": "medium" if review else "high",
        }
        self.matches[rule].append(match)


class BoundedYamlLoader(yaml.SafeLoader):
    """Compose nodes for location metadata without instantiating YAML objects."""

    def __init__(self, stream):
        super().__init__(stream)
        self.depth = 0
        self.nodes = 0

    def compose_node(self, parent, index):
        self.nodes += 1
        self.depth += 1
        try:
            if self.depth > 64 or self.nodes > 100_000:
                raise yaml.YAMLError("Configuration structure exceeds supported limits")
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1


def yaml_documents(text):
    try:
        return list(yaml.compose_all(text, Loader=BoundedYamlLoader))
    except (yaml.YAMLError, RecursionError):
        return []


def members(node, active=None, cache=None):
    if not isinstance(node, MappingNode):
        return {}
    if active is None:
        active, cache = set(), {}
    if id(node) in cache:
        return cache[id(node)]
    if id(node) in active:
        return {}
    active.add(id(node))
    result = {}
    explicit = {}
    for key, value in node.value:
        if not isinstance(key, ScalarNode):
            continue
        if key.tag == "tag:yaml.org,2002:merge":
            inherited = value.value if isinstance(value, SequenceNode) else [value]
            for mapping in reversed(inherited):
                result.update(members(mapping, active, cache))
        else:
            explicit[key.value] = value
    result.update(explicit)
    active.remove(id(node))
    cache[id(node)] = result
    return result


def sequence(node):
    return node.value if isinstance(node, SequenceNode) else ()


def scalar(node):
    return node.value if isinstance(node, ScalarNode) else None


def yaml_true(node):
    return (
        isinstance(node, ScalarNode)
        and node.tag == "tag:yaml.org,2002:bool"
        and node.value.lower() in {"true", "yes", "on"}
    )


def source_line(node):
    return node.start_mark.line + 1


def config_list(policy, key):
    items = policy.get(key)
    return set(item for item in items if isinstance(item, str)) if isinstance(items, list) else set()


def docker_instructions(text):
    command = ""
    number = 0
    escape = "\\"
    heredocs = deque()
    for line, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if heredocs:
            if raw_line == heredocs[0][0] or heredocs[0][1] and raw_line.lstrip("\t") == heredocs[0][0]:
                heredocs.popleft()
            continue
        if stripped.startswith("#"):
            directive = re.fullmatch(r"#\s*escape\s*=\s*([\\`])", stripped, re.I)
            if directive and not number:
                escape = directive[1]
            continue
        if not stripped:
            continue
        if not command:
            number = line
        if stripped.endswith(escape):
            command += stripped[:-1] + " "
            continue
        command += stripped
        parts = command.split(None, 1)
        if len(parts) == 2:
            instruction = parts[0].upper()
            if instruction in {"COPY", "RUN"}:
                heredocs.extend(
                    (marker, bool(strip_tabs))
                    for strip_tabs, _, marker in re.findall(r"""(?<!<)<<(-?)(['"]?)([A-Za-z_][A-Za-z0-9_]*)\2""", parts[1])
                )
            yield instruction, parts[1], number
        command = ""


def check_dockerfile(path, text, policy, results):
    stages = {}
    last_user = None
    has_stage = False
    for instruction, value, line in docker_instructions(text):
        if instruction not in {"FROM", "USER"}:
            continue
        try:
            parts = shlex.split(value)
        except ValueError:
            continue
        if instruction == "USER" and has_stage and len(parts) == 1:
            last_user = (parts[0].split(":", 1)[0], line)
            if current_alias:
                stages[current_alias] = last_user
        elif instruction == "FROM":
            parts = [part for part in parts if not part.startswith("--")]
            if len(parts) not in {1, 3} or len(parts) == 3 and parts[1].lower() != "as":
                continue
            has_stage = True
            image = parts[0]
            base = image.casefold()
            last_user = stages.get(base)
            if base not in stages and base != "scratch" and "$" not in image:
                if policy.get("require_image_digest", True) is True:
                    results.applicable("INF-02")
                    if not re.search(r"@sha256:[a-f0-9]{64}$", image, re.I):
                        results.add("INF-02", path, line, "External FROM image has no fixed SHA-256 digest.")
            current_alias = parts[2].casefold() if len(parts) == 3 else None
            if current_alias:
                stages[current_alias] = last_user
    if last_user:
        user, line = last_user
        if "$" in user:
            return
        results.applicable("INF-01")
        if user == "root" or user and set(user) == {"0"}:
            results.add("INF-01", path, line, "Final image has an explicit root user.")


WORKLOADS = {"Deployment", "DaemonSet", "Job", "ReplicaSet", "ReplicationController", "StatefulSet"}


def pod_specs(document):
    roots = [(document, 0)]
    visited = set()
    while roots:
        current, depth = roots.pop()
        if id(current) in visited or depth > 32:
            continue
        visited.add(id(current))
        doc = members(current)
        kind = scalar(doc.get("kind"))
        if not scalar(doc.get("apiVersion")):
            continue
        spec = doc.get("spec")
        if kind == "List":
            roots.extend((item, depth + 1) for item in reversed(sequence(doc.get("items"))))
        elif kind == "Pod":
            yield spec
        elif kind in WORKLOADS:
            yield members(members(spec).get("template")).get("spec")
        elif kind == "CronJob":
            job = members(members(spec).get("jobTemplate")).get("spec")
            yield members(members(job).get("template")).get("spec")


def check_kubernetes(path, documents, policy, results):
    allowed_mounts = config_list(policy, "hostpath_exemptions")
    forbidden = {value.upper().removeprefix("CAP_") for value in config_list(policy, "forbidden_capabilities")}
    for document in documents:
        for pod in pod_specs(document):
            spec = members(pod)
            containers = [
                members(item) for collection in ("containers", "initContainers", "ephemeralContainers")
                for item in sequence(spec.get(collection)) if isinstance(item, MappingNode)
            ]
            if not containers:
                continue
            results.applicable("INF-03", "INF-04", "INF-05", "INF-06", "INF-08")
            if forbidden:
                results.applicable("INF-07")
            for field, rule in (("hostNetwork", "INF-04"), ("hostPID", "INF-05")):
                setting = spec.get(field)
                if yaml_true(setting):
                    results.add(rule, path, source_line(setting), f"Pod explicitly enables {field}.")
            for volume in sequence(spec.get("volumes")):
                host_path = members(members(volume).get("hostPath")).get("path")
                value = scalar(host_path)
                if value and value not in allowed_mounts:
                    results.add("INF-06", path, source_line(host_path), "Pod declares a hostPath without a listed exemption.", review=True)
            for container in containers:
                security = members(container.get("securityContext"))
                privileged = security.get("privileged")
                escalation = security.get("allowPrivilegeEscalation")
                if yaml_true(privileged):
                    results.add("INF-03", path, source_line(privileged), "Container explicitly sets privileged mode.")
                elif yaml_true(escalation):
                    results.add("INF-08", path, source_line(escalation), "Container explicitly allows privilege escalation.")
                capabilities = members(security.get("capabilities"))
                for item in sequence(capabilities.get("add")):
                    if (scalar(item) or "").upper().removeprefix("CAP_") in forbidden:
                        results.add("INF-07", path, source_line(item), "Container adds a Linux capability forbidden by policy.")


def json_map(text):
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def json_lines(text):
    lines = {}
    for line, value in enumerate(text.splitlines(), 1):
        for token in re.finditer(r'("(?:[^"\\]|\\.)*")\s*:', value):
            try:
                name = json.loads(token[1])
            except ValueError:
                continue
            lines.setdefault(name, line)
    return lines


S3_FLAGS = (
    "block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets",
)


def check_terraform(inputs, policy, results):
    """Native Terraform JSON files in each directory form one static module."""
    if policy.get("snapshot_complete") is not True or policy.get("require_s3_public_access_block", True) is not True:
        return
    modules = {}
    unresolved = set()
    for path, text in inputs.items():
        directory = str(PurePosixPath(path).parent)
        if path.lower().endswith(".tf"):
            unresolved.add(directory)
        if not path.lower().endswith(".tf.json"):
            continue
        document = json_map(text)
        if document is None:
            unresolved.add(directory)
            continue
        resources = document.get("resource")
        blocks = resources if isinstance(resources, list) else [resources]
        if resources is None:
            continue
        if not all(isinstance(block, dict) for block in blocks):
            unresolved.add(directory)
            continue
        module = modules.setdefault(directory, [])
        lines = json_lines(text)
        for block in blocks:
            for kind in ("aws_s3_bucket", "aws_s3_bucket_public_access_block"):
                named = block.get(kind)
                if not isinstance(named, dict):
                    continue
                for name, settings in named.items():
                    if isinstance(settings, dict) and settings.get("count", 1) != 0:
                        module.append((kind, name, settings, path, lines.get(name, 1)))
    for directory, resources in modules.items():
        if directory in unresolved:
            continue
        blocks = [settings for kind, _, settings, _, _ in resources if kind == "aws_s3_bucket_public_access_block"]
        for kind, name, settings, path, line in resources:
            if kind != "aws_s3_bucket" or "for_each" in settings or "count" in settings:
                continue
            results.applicable("INF-09")
            references = {f"${{aws_s3_bucket.{name}.{field}}}" for field in ("id", "bucket")}
            bucket = settings.get("bucket")
            if isinstance(bucket, str) and bucket and "$" not in bucket:
                references.add(bucket)
            matching = [
                block for block in blocks
                if isinstance(block.get("bucket"), str) and block["bucket"] in references
            ]
            if not any("for_each" not in block and "count" not in block
                       and all(block.get(flag) is True for flag in S3_FLAGS) for block in matching):
                results.add("INF-09", path, line, "Bucket has no verified full public-access block in the supplied Terraform module.", review=True)


SQL_TOKEN = re.compile(
    r"""(?P<comment>--[^\n]*)|(?P<block>/\*)|(?P<dollar>(?<![\w$])\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)|"""
    r"""(?P<escaped>(?<![\w$])[Ee]')|(?P<string>')|(?P<identifier>")|(?P<end>;)""",
)
COMMENT_MARKER = re.compile(r"/\*|\*/")
SQL_IDENTIFIER = r'(?:"(?:""|[^"])+"|[A-Za-z_][A-Za-z0-9_$]*)'
SQL_RELATION = rf"{SQL_IDENTIFIER}(?:\s*\.\s*{SQL_IDENTIFIER})?"


def quoted_end(text, cursor, quote, *, escapes=False):
    marker = re.compile(r"['\\]" if escapes else re.escape(quote))
    while (match := marker.search(text, cursor)) is not None:
        cursor = match.end()
        if match[0] == "\\" or text[cursor:cursor + 1] == quote:
            cursor += 1
        else:
            return cursor
    return len(text)


def sql_statements(text):
    """Return static statement text while keeping comments and literal bodies inert."""
    pieces = []
    start = 0
    start_line = 1
    cursor = 0
    while (token := SQL_TOKEN.search(text, cursor)) is not None:
        pieces.append(text[cursor:token.start()])
        cursor = token.end()
        if token.lastgroup == "end":
            statement = "".join(pieces)
            if statement.strip():
                line = start_line + statement.count("\n", 0, len(statement) - len(statement.lstrip()))
                yield statement.lstrip(), line
            pieces.clear()
            start_line += text.count("\n", start, token.end())
            start = token.end()
        else:
            kind = token.lastgroup
            if kind == "block":
                depth = 1
                for mark in COMMENT_MARKER.finditer(text, cursor):
                    depth += 1 if mark[0] == "/*" else -1
                    if depth == 0:
                        cursor = mark.end()
                        break
                else:
                    cursor = len(text)
            elif kind == "dollar":
                end = text.find(token[0], cursor)
                cursor = len(text) if end == -1 else end + len(token[0])
            elif kind in {"string", "escaped", "identifier"}:
                cursor = quoted_end(text, cursor, token[0][-1], escapes=kind == "escaped")
            chunk = text[token.start():cursor]
            pieces.append(chunk if kind == "identifier" else re.sub(r"[^\n]", " ", chunk))
    pieces.append(text[cursor:])
    statement = "".join(pieces)
    if statement.strip():
        line = start_line + statement.count("\n", 0, len(statement) - len(statement.lstrip()))
        yield statement.lstrip(), line


def sql_name(value):
    return value[1:-1].replace('""', '"') if value.startswith('"') else value.lower()


def relation_key(value):
    parts = tuple(sql_name(part) for part in re.findall(SQL_IDENTIFIER, value))
    return parts if len(parts) > 1 else ("public", *parts)


def check_sql(inputs, policy, results):
    """Assess supported static Postgres migrations in lexically sorted path order."""
    tenant_tables = {
        relation_key(value) for value in config_list(policy, "tenant_tables")
        if re.fullmatch(SQL_RELATION, value)
    }
    if policy.get("snapshot_complete") is not True or not tenant_tables:
        return
    changes = {
        "create": re.compile(rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({SQL_RELATION})(?=\s|\()", re.I),
        "drop": re.compile(rf"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?({SQL_RELATION})\s*(?:CASCADE|RESTRICT)?\s*$", re.I),
        "rls": re.compile(rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?({SQL_RELATION})\s+(ENABLE|DISABLE)\s+ROW\s+LEVEL\s+SECURITY\s*$", re.I),
        "policy": re.compile(rf"(CREATE|DROP)\s+POLICY\s+(?:IF\s+EXISTS\s+)?({SQL_IDENTIFIER})\s+ON\s+({SQL_RELATION})(?=\s|$)", re.I),
    }
    tables = {}
    for path, text in sorted(inputs.items()):
        if not path.lower().endswith(".sql"):
            continue
        for statement, line in sql_statements(text):
            create = changes["create"].match(statement)
            if create:
                table = relation_key(create[1])
                if table in tenant_tables:
                    tables.setdefault(table, (path, line, False, set()))
                continue
            drop = changes["drop"].match(statement)
            if drop:
                tables.pop(relation_key(drop[1]), None)
                continue
            rls = changes["rls"].match(statement)
            if rls and (table := relation_key(rls[1])) in tables:
                at, number, _, policies = tables[table]
                tables[table] = at, number, rls[2].upper() == "ENABLE", policies
                continue
            rule = changes["policy"].match(statement)
            if rule and (table := relation_key(rule[3])) in tables:
                policies = tables[table][3]
                name = sql_name(rule[2])
                if rule[1].upper() == "DROP":
                    policies.discard(name)
                elif re.search(r"\b(?:USING|WITH\s+CHECK)\s*\((?!\s*TRUE\s*\))", statement[rule.end():], re.I):
                    policies.add(name)
    for path, line, enabled, policies in tables.values():
        results.applicable("INF-10")
        if not enabled or not policies:
            results.add("INF-10", path, line, "Tenant table has no fully declared RLS and predicate policy in the supplied migrations.", review=True)


def workflow_path(path):
    parts = PurePosixPath(path.casefold()).parts
    return len(parts) >= 3 and parts[-3:-1] == (".github", "workflows")


def external_action(reference):
    # Container actions and local workflow paths have different pinning contracts.
    return bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^@]+)?@", reference))


def check_workflow(path, documents, policy, results):
    if not workflow_path(path):
        return
    write_policy = policy.get("ci_write_permissions")
    for item in documents:
        workflow = members(item)
        jobs = members(workflow.get("jobs"))
        if not jobs:
            continue
        results.applicable("CI-02")
        global_permissions = workflow.get("permissions")
        if scalar(global_permissions) == "write-all":
            results.add("CI-02", path, source_line(global_permissions), "Workflow grants write access to every permission scope.")
        for job_id, job_node in jobs.items():
            job = members(job_node)
            permissions = job.get("permissions")
            if scalar(permissions) == "write-all":
                results.add("CI-02", path, source_line(permissions), "Workflow job grants write access to every permission scope.")
            effective = permissions if permissions is not None else global_permissions
            if isinstance(write_policy, dict):
                allowed = write_policy.get(job_id, write_policy.get("*"))
                if isinstance(allowed, list):
                    results.applicable("CI-03")
                    for scope, level in members(effective).items():
                        if scalar(level) == "write" and scope not in allowed:
                            results.add("CI-03", path, source_line(level), "A job's effective write permission exceeds the selected allowlist.")
            steps = [job] + [members(step) for step in sequence(job.get("steps"))]
            for step in steps:
                uses = step.get("uses")
                reference = scalar(uses) or ""
                if not external_action(reference):
                    continue
                if policy.get("ci_require_pinned_actions", True) is True:
                    results.applicable("CI-01")
                    if not re.fullmatch(r"[a-f0-9]{40}", reference.rsplit("@", 1)[-1], re.I):
                        results.add("CI-01", path, source_line(uses), "External action or reusable workflow has no full commit hash.")
                if (policy.get("ci_disable_checkout_credentials") is True
                        and reference.casefold().startswith("actions/checkout@")):
                    results.applicable("CI-04")
                    persisted = members(step.get("with")).get("persist-credentials")
                    if persisted is None or (scalar(persisted) or "").lower() != "false":
                        results.add("CI-04", path, source_line(persisted if persisted is not None else uses),
                                    "Checkout credentials are not explicitly disabled as required.", review=True)


def check_branch_protection(inputs, policy, results):
    """Analyze .marsad/branch-protection.json with complete branch settings."""
    desired = policy.get("protected_branches")
    if not isinstance(desired, dict):
        return
    for path, text in inputs.items():
        if tuple(PurePosixPath(path).parts[-2:]) != (".marsad", "branch-protection.json"):
            continue
        document = json_map(text)
        if document is None:
            continue
        branches = document.get("branches")
        if document.get("complete") is not True or not isinstance(branches, dict):
            continue
        lines = json_lines(text)
        for branch, expected in desired.items():
            actual = branches.get(branch)
            if not isinstance(actual, dict) or not isinstance(expected, dict):
                continue
            expected_count, actual_count = expected.get("required_approvals"), actual.get("required_approvals")
            if (type(expected_count) is int and expected_count > 0
                    and type(actual_count) is int and actual_count >= 0):
                results.applicable("CI-05")
                if actual_count < expected_count:
                    results.add("CI-05", path, lines.get(branch, 1), "Protected branch allows fewer approvals than the project policy.")
            expected_checks, actual_checks = expected.get("required_checks"), actual.get("required_checks")
            if (isinstance(expected_checks, list) and expected_checks and isinstance(actual_checks, list)
                    and all(isinstance(value, str) for value in expected_checks + actual_checks)):
                results.applicable("CI-06")
                if set(expected_checks) - set(actual_checks):
                    results.add("CI-06", path, lines.get(branch, 1), "Protected branch is missing at least one required CI check.")


PEM_PRIVATE_KEY = re.compile(r"-----BEGIN (?P<label>(?:[A-Z0-9]+ ){0,4}PRIVATE KEY)-----$")
PEM_ESCAPED_LINE = re.compile(r"\\r\\n|\\[rn]")
PEM_PAYLOAD = re.compile(r"[A-Za-z0-9+/]+={0,2}")
PEM_MAX_PAYLOAD = 64 * 1024
TOKEN_SIGNATURES = {
    "GitHub": re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{70,110})(?![A-Za-z0-9_])"),
    "OpenRouter": re.compile(r"(?<![A-Za-z0-9_-])sk-or-v1-[a-fA-F0-9]{64}(?![A-Za-z0-9_-])"),
    "Slack": re.compile(r"(?<![A-Za-z0-9_-])xoxb-[0-9]{8,15}-[0-9]{8,15}-[A-Za-z0-9]{20,35}(?![A-Za-z0-9_-])"),
}
SOURCE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".htm", ".vue",
    ".go", ".rs", ".rb", ".php", ".java", ".kt", ".kts", ".cs", ".ps1", ".sh", ".bash",
    ".sql", ".tf", ".toml", ".yml", ".yaml", ".json", ".xml", ".conf", ".config",
    ".ini", ".properties", ".txt", ".pem", ".key", ".dockerfile", ".env",
}
DSN_FIELDS = {"DATABASE_URL", "DATABASE_DSN", "DB_URL", "DB_DSN", "MONGODB_URI", "MONGO_URL", "REDIS_URL", "SQLALCHEMY_DATABASE_URI"}
DSN_SCHEMES = {"postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "redis", "rediss", "amqp", "amqps", "mssql"}
DEBUG_FIELDS = {"DEBUG", "FLASK_DEBUG", "APP_DEBUG", "DJANGO_DEBUG"}
KEYSTORE_FIELDS = {"SERVER_SSL_KEY_STORE_PASSWORD", "SSL_KEY_STORE_PASSWORD", "TLS_KEYSTORE_PASSWORD", "KEYSTORE_PASSWORD"}
COOKIE_FIELDS = (
    ("SESSION_COOKIE_SAMESITE", "SESSION_COOKIE_SECURE", "SESSION_COOKIE_NAME"),
    ("SERVER_SERVLET_SESSION_COOKIE_SAME_SITE", "SERVER_SERVLET_SESSION_COOKIE_SECURE", "SERVER_SERVLET_SESSION_COOKIE_NAME"),
)
PRODUCTION_PATH = re.compile(r"(?:^|[/_.-])(?:prod|production)(?=$|[/_.-])", re.I)
ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][\w.-]*)\s*[=:]\s*(.*?)\s*$")


@dataclass(frozen=True)
class Setting:
    value: object
    line: int


def setting_key(value):
    return re.sub(r"[.-]", "_", value).upper()


def path_selected(path, patterns):
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def python_settings(text):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            root = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    settings = {}
    for item in root.body:
        if isinstance(item, ast.Assign):
            names = item.targets
        elif isinstance(item, ast.AnnAssign):
            names = [item.target]
        else:
            continue
        value = item.value
        for name in names:
            if isinstance(name, ast.Name):
                field = name.id
            elif (isinstance(name, ast.Subscript) and isinstance(name.slice, ast.Constant)
                  and isinstance(name.slice.value, str)
                  and (isinstance(name.value, ast.Attribute) and name.value.attr == "config"
                       or isinstance(name.value, ast.Name) and name.value.id == "config")):
                field = name.slice.value
            else:
                continue
            if isinstance(value, ast.Constant):
                # Preserve explicit Python constants without evaluating expressions or importing modules.
                settings[setting_key(field)] = Setting(value.value, item.lineno)
            else:
                settings.pop(setting_key(field), None)
    return settings


def flat_settings(text):
    settings = {}
    for line, value in enumerate(text.splitlines(), 1):
        match = ENV_ASSIGNMENT.match(value)
        if not match:
            continue
        field, raw = match.groups()
        if raw and raw[0] in "'\"":
            quoted = re.match(r"""^(['"])(.*?)\1\s*(?:#.*)?$""", raw)
            if not quoted:
                continue
            raw = quoted[2]
        else:
            raw = re.split(r"\s+#", raw, maxsplit=1)[0]
        settings[setting_key(field)] = Setting(raw, line)
    return settings


def structured_settings(root):
    settings = {}
    pending = [(root, (), frozenset())]
    remaining = 100_000
    while pending and remaining:
        remaining -= 1
        node, trail, active = pending.pop()
        if id(node) in active or len(trail) > 32:
            continue
        if isinstance(node, ScalarNode):
            if node.tag != "tag:yaml.org,2002:null":
                settings[setting_key(".".join(trail))] = Setting(node.value, source_line(node))
            continue
        for name, value in members(node).items():
            pending.append((value, trail + (name,), active | {id(node)}))
    return settings if remaining else {}


def config_settings(path, text, documents):
    filename = PurePosixPath(path.casefold()).name
    extension = PurePosixPath(filename).suffix
    if filename == ".env" or filename.startswith(".env.") or extension in {".properties", ".ini", ".env"}:
        return [flat_settings(text)]
    if extension == ".py":
        values = python_settings(text)
        return [values] if values is not None else []
    if extension in {".yaml", ".yml", ".json"} and not workflow_path(path):
        return [structured_settings(doc) for doc in documents]
    return []


def is_placeholder(value):
    if not isinstance(value, str):
        return True
    token = value.strip()
    return (
        not token
        or token.casefold() in {"changeme", "change-me", "replace-me", "your_password", "your-password", "redacted", "[redacted]"}
        or bool(re.fullmatch(r"(?:\$\{[^}]+\}|\$[A-Za-z_][\w]*|%[A-Za-z_][\w]*%|\{\{.*}}|<[^>]+>|[*]+)", token))
    )


def literal_dsn(value):
    if not isinstance(value, str):
        return False
    try:
        target = urlsplit(value)
        user = unquote(target.username or "")
        password = unquote(target.password or "")
    except ValueError:
        return False
    return (
        (target.scheme in DSN_SCHEMES or target.scheme.split("+", 1)[0] in DSN_SCHEMES)
        and bool(target.hostname)
        and not is_placeholder(user)
        and not is_placeholder(password)
    )


def true_value(value):
    return value is True or type(value) is int and value == 1 or isinstance(value, str) and value.casefold() in {"true", "1", "on", "yes"}


def false_value(value):
    return value is False or type(value) is int and value == 0 or isinstance(value, str) and value.casefold() in {"false", "0", "off", "no"}


def matching_settings(settings, fields):
    for key, setting in settings.items():
        if key in fields:
            yield setting


def check_app_settings(path, settings, policy, results):
    production = path_selected(path, config_list(policy, "production_paths")) or bool(PRODUCTION_PATH.search(path))
    for setting in matching_settings(settings, DSN_FIELDS):
        results.applicable("APP-03")
        if literal_dsn(setting.value):
            results.add("APP-03", path, setting.line, "A supported connection setting contains literal credentials.")
    if production:
        for setting in matching_settings(settings, DEBUG_FIELDS):
            results.applicable("APP-04")
            if true_value(setting.value):
                results.add("APP-04", path, setting.line, "A supported production debug setting is enabled.")
    cookie_names = config_list(policy, "session_cookie_keys")
    for same_site, secure, name in COOKIE_FIELDS:
        same_setting = settings.get(same_site)
        secure_setting = settings.get(secure)
        name_setting = settings.get(name)
        if same_setting is None or secure_setting is None:
            continue
        if cookie_names and (name_setting is None or not isinstance(name_setting.value, str)
                             or name_setting.value not in cookie_names):
            continue
        results.applicable("APP-05")
        if (isinstance(same_setting.value, str) and same_setting.value.casefold() == "none"
                and false_value(secure_setting.value)):
            results.add("APP-05", path, secure_setting.line, "Session cookie specifies SameSite=None with Secure disabled.")
    for setting in matching_settings(settings, KEYSTORE_FIELDS):
        results.applicable("APP-06")
        if not is_placeholder(setting.value):
            results.add("APP-06", path, setting.line, "A TLS keystore password field contains a literal value.")


def pem_key_lines(lines):
    """Return PEM marker locations without parsing keys or including their contents in evidence."""
    closing = None
    for line_number, line in enumerate(lines, 1):
        for segment in PEM_ESCAPED_LINE.split(line):
            value = segment.strip()
            opening = PEM_PRIVATE_KEY.search(value)
            if opening:
                closing = f"-----END {opening['label']}-----"
                start_line, size, payload = line_number, 0, []
            elif closing and value.startswith(closing):
                if size >= 32:
                    try:
                        b64decode("".join(payload), validate=True)
                    except Base64Error:
                        pass
                    else:
                        yield start_line
                closing = None
            elif closing and value:
                if not payload and value.startswith(("Proc-Type:", "DEK-Info:")):
                    continue
                size += len(value)
                if size > PEM_MAX_PAYLOAD or not PEM_PAYLOAD.fullmatch(value):
                    closing = None
                else:
                    payload.append(value)


def check_app(path, text, documents, policy, results):
    parts = PurePosixPath(path.casefold()).parts
    if "fixtures" in parts or path_selected(path, config_list(policy, "fixture_paths")):
        return
    filename = parts[-1] if parts else ""
    suffix = PurePosixPath(filename).suffix
    if suffix in SOURCE_SUFFIXES or filename.startswith((".env", "dockerfile")):
        results.applicable("APP-01", "APP-02")
        lines = text.splitlines()
        if "PRIVATE KEY-----" in text:
            for line in pem_key_lines(lines):
                results.add("APP-01", path, line, "PEM private-key marker is present.")
        for line, value in enumerate(lines, 1):
            for provider, expression in TOKEN_SIGNATURES.items():
                if expression.search(value):
                    results.add("APP-02", path, line, f"{provider} token signature is present.")
    for settings in config_settings(path, text, documents):
        check_app_settings(path, settings, policy, results)


def check(text_inputs, har, policy, advisories):
    """Return the supported rule IDs and their sanitized source evidence."""
    results = Results()
    for path, text in text_inputs.items():
        filename = PurePosixPath(path).name.casefold()
        if filename == "dockerfile" or filename.startswith("dockerfile.") or filename.endswith(".dockerfile"):
            check_dockerfile(path, text, policy, results)
        documents = yaml_documents(text) if filename.endswith((".yaml", ".yml", ".json")) else []
        if documents:
            check_kubernetes(path, documents, policy, results)
            check_workflow(path, documents, policy, results)
        check_app(path, text, documents, policy, results)
    check_terraform(text_inputs, policy, results)
    check_sql(text_inputs, policy, results)
    check_branch_protection(text_inputs, policy, results)
    return results.matches
