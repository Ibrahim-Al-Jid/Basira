"""Versioned, offline project-scan capabilities and evidence provenance."""
from datetime import datetime
from hashlib import sha256
from importlib import import_module
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .source_adapters import SOURCE_KINDS, SOURCE_TOOLS, configured_tools

ArtifactKind = Literal["html", "repository", "har", "config", "openapi", "zap"]
DEFAULT_INPUTS = ("repository", "html", "har", "openapi", "config", "zap")
CoverageStatus = Literal["matched", "clear", "not_applicable", "skipped", "error"]
AgentRole = Literal["orchestrator", "planning", "analysis", "validation", "reporting"]
Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ModelConnection = Literal["openrouter-default"]

PROFILE = "offline-artifact"
TOOL_PROTOCOL_VERSION = "marsad-tool-1"
RAW_RETENTION_MINUTES = 15
ALL_INPUTS = DEFAULT_INPUTS
ANALYZER_INPUTS = {
    "html-attributes": ("html", "repository", "config"),
    "browser-controls": ("html", "repository", "har", "config"),
    "dependency-evidence": ("repository", "config"),
    "deployment-config": ("repository", "config"),
    "browser-controls-extra": ("html", "repository", "har", "config"),
    "deployment-config-extra": ("repository", "config"),
    "openapi-contract": ("openapi",),
    "zap-passive-report": ("zap",),
}
ANALYZER_TITLES = {
    "html-attributes": "HTML attributes",
    "browser-controls": "Browser and response controls",
    "dependency-evidence": "Dependency evidence",
    "deployment-config": "Deployment configuration",
    "browser-controls-extra": "Extended browser and response controls",
    "deployment-config-extra": "Extended dependency and deployment controls",
    "openapi-contract": "Offline API contract",
    "zap-passive-report": "Saved ZAP passive evidence",
}
ANALYZER_TITLES_AR = {
    "html-attributes": "خصائص HTML الأساسية",
    "openapi-contract": "عقد API المحلي",
    "zap-passive-report": "أدلة ZAP السلبية المحفوظة",
}
ROLE_TOOLS = {
    "orchestrator": ("base64-envelope", "artifact-router"),
    "planning": ("artifact-normalizer", "rule-registry"),
    "analysis": tuple(ANALYZER_INPUTS),
    "validation": ("coverage-contract", "evidence-registry"),
    "reporting": ("bilingual-summary", "report-projection"),
}
ROLE_BOUNDARIES = {
    "orchestrator": ("submission", "accepted_artifact"),
    "planning": ("accepted_artifact", "offline_plan"),
    "analysis": ("offline_plan", "finding_observations"),
    "validation": ("finding_observations", "coverage_result"),
    "reporting": ("coverage_result", "redacted_report"),
}
INTERNAL_TOOL_TITLES = {
    "base64-envelope": ("Input envelope", "غلاف المدخل"),
    "artifact-router": ("Input routing", "توجيه المدخل"),
    "artifact-normalizer": ("Input preparation", "تهيئة المدخل"),
    "rule-registry": ("Rule selection", "اختيار القواعد"),
    "coverage-contract": ("Coverage validation", "مطابقة التغطية"),
    "evidence-registry": ("Evidence validation", "التحقق من الأدلة"),
    "bilingual-summary": ("Bilingual summary", "ملخّص باللغتين"),
    "report-projection": ("Report assembly", "تجهيز التقرير"),
}


class ToolPin(BaseModel):
    id: str
    version: str


class ToolManifest(ToolPin):
    title_en: str
    title_ar: str
    supported_inputs: list[ArtifactKind]
    mode: Literal["offline"] = "offline"
    status: Literal["available", "disabled"] = "available"
    reason: Literal["adapter_unavailable", "not_enabled", "shadow_only"] | None = None
    contract: Literal["marsad-tool-2"] = "marsad-tool-2"
    approval: Literal["approved", "shadow"] = "approved"
    runner: Literal["builtin", "isolated_cli", "unregistered"] = "builtin"
    network: Literal[False] = False
    license: str
    capabilities: list[str] = Field(default_factory=list)
    evidence_requires: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(default=None, gt=0)
    limitations: list[str] = Field(default_factory=list)


class ToolSelection(ToolPin):
    status: Literal["selected", "skipped"]
    reason: Literal["eligible", "unsupported_input", "adapter_unavailable", "not_enabled", "shadow_only",
                    "not_in_pinned_plan", "offline_runner_required"]


class RoleManifest(BaseModel):
    id: AgentRole
    tools: list[str]
    input_contract: str
    output_contract: str
    network: Literal[False] = False


class ConnectionInfo(BaseModel):
    id: ModelConnection
    provider: Literal["openrouter"]
    model: str
    max_calls: Literal[1]
    max_output_tokens: int


class ScanProfile(BaseModel):
    profile: Literal["offline-artifact"] = PROFILE
    mode: Literal["offline"] = "offline"
    scope_version: int = Field(ge=0)
    allowed_kinds: list[ArtifactKind]
    max_bytes: int
    raw_retention_minutes: int = RAW_RETENTION_MINUTES
    asset_linked: bool
    enrichment_available: bool
    model_connection: ConnectionInfo | None
    tools_by_input: dict[ArtifactKind, list[ToolPin]]


class TechnicalRegistry(BaseModel):
    scope_version: int = Field(ge=0)
    model_connection: ModelConnection | None
    server_connection: ConnectionInfo | None
    server_ready: bool = False
    permissions: dict[str, list[str]]
    tools: list[ToolManifest]
    roles: list[RoleManifest]


class Asset(BaseModel):
    id: Identifier
    kind: Literal["website_reference"] = "website_reference"
    reference: str
    source: Literal["project_policy", "scan_reference"] = "project_policy"


class GitHubSnapshotRef(BaseModel):
    repository: str = Field(max_length=140, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    connection_id: Identifier
    installation_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    repository_id: str | None = Field(default=None, exclude_if=lambda value: value is None)


class TargetProfile(BaseModel):
    mode: Literal["zip", "github", "website"]
    contract: Literal["marsad-intake-1"] = "marsad-intake-1"
    text_files: int | None = None
    skipped_files: int | None = None
    expanded_text_sha256: Digest | None = None
    expanded_text_bytes: int | None = None
    file_types: list[str] = Field(default_factory=list)
    root_count: int | None = None
    executable_entries: int | None = None
    lockfiles: int | None = None
    config_files: int | None = None
    api_specs: int | None = None
    public_url: str | None = None
    pages: int | None = None
    requests: int | None = None
    forms: int | None = None
    links_observed: int | None = None
    page_bytes: int | None = None
    page_sha256: Digest | None = None
    tls_version: str | None = None


class SourceSnapshot(BaseModel):
    id: Identifier
    sha256: Digest
    kind: ArtifactKind
    bytes: int = Field(ge=1)
    created_at: datetime
    raw_expires_at: datetime
    github: GitHubSnapshotRef | None = None
    profile: TargetProfile | None = Field(default=None, exclude_if=lambda value: value is None)


class ScopeVersion(BaseModel):
    version: int = Field(ge=0)
    sha256: Digest
    asset_id: Identifier | None
    asset_source: Literal["project_policy", "scan_reference"] = "project_policy"
    ruleset_version: str
    profile: Literal["offline-artifact"] = PROFILE
    mode: Literal["offline"] = "offline"


class Evidence(BaseModel):
    line: int = Field(ge=1)
    path: str | None
    evidence_sha256: Digest


class FindingObservation(Evidence):
    ordinal: int = Field(ge=0)
    rule: str


class ScanProvenance(BaseModel):
    snapshot: SourceSnapshot
    scope: ScopeVersion
    asset: Asset | None
    tools: list[ToolPin]
    evidence_count: int = Field(ge=0)


def json_digest(value):
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def adapter_available(adapter):
    try:
        return callable(import_module(".checks." + adapter.module, __package__).check)
    except Exception:
        return False


def analyzer_manifests():
    from .artifact_review import ADAPTERS, RULESET_VERSION
    from .source_adapters import SOURCE_TIMEOUTS
    adapters = {entry.id: entry for entry in ADAPTERS}
    tools = []
    for tool, inputs in ANALYZER_INPUTS.items():
        adapter = adapters.get(tool)
        available = not adapter or adapter_available(adapter)
        tools.append(ToolManifest(
            id=tool, version=RULESET_VERSION, title_en=ANALYZER_TITLES[tool],
            title_ar=adapter.title_ar if adapter else ANALYZER_TITLES_AR[tool],
            supported_inputs=inputs, status="available" if available else "disabled",
            reason=None if available else "adapter_unavailable",
            license="MIT", capabilities=[tool],
            evidence_requires=["saved ZAP Traditional JSON"] if tool == "zap-passive-report" else [],
            limitations=["imported alerts only"] if tool == "zap-passive-report" else [],
        ))
    enabled = configured_tools()
    for tool in SOURCE_TOOLS:
        secret_review = tool.id == "gitleaks"
        tools.append(ToolManifest(
            id=tool.id, version=tool.version, title_en=tool.title_en, title_ar=tool.title_ar,
            supported_inputs=SOURCE_KINDS, status="available" if tool in enabled else "disabled",
            reason=None if tool in enabled else "not_enabled", runner="isolated_cli",
            license="MIT" if secret_review else "Apache-2.0",
            capabilities=["credential-signatures" if secret_review else "dependency-advisories"],
            evidence_requires=["submitted text"] if secret_review else ["supported lockfile or exact PyPI pins"],
            timeout_seconds=SOURCE_TIMEOUTS[tool.id],
            limitations=["snapshot only; no Git history"] if secret_review else ["bundled advisory ecosystems only"],
        ))
    tools.extend(ToolManifest(
        id=tool, version=version, title_en=title, title_ar=title, supported_inputs=SOURCE_KINDS,
        approval="shadow", runner="unregistered", status="disabled", reason="shadow_only",
        license=license_name, capabilities=[capability], limitations=[limitation],
    ) for tool, version, title, license_name, capability, limitation in (
        ("semgrep", "1.186.0", "Semgrep CE", "LGPL-2.1", "source-patterns", "fixture rules only"),
        ("trivy", "0.76.2", "Trivy", "Apache-2.0", "configuration-audit", "overlap with approved configuration and dependency checks"),
    ))
    return tools


def resolve_analyzers(kind, *, pinned=None, external=True):
    """Resolve server-authored pins without granting any new capability to an old job."""
    manifests = analyzer_manifests()
    accepted = [
        tool.model_dump(include={"id", "version"}) for tool in manifests
        if tool.approval == "approved" and kind in tool.supported_inputs
    ]
    if pinned is not None:
        if not isinstance(pinned, list) or not pinned or [
            pin for pin in accepted if pin in pinned
        ] != pinned:
            raise ValueError("Incompatible analyzer plan")
    decisions = []
    for tool in manifests:
        pin = tool.model_dump(include={"id", "version"})
        if tool.approval == "shadow":
            reason = "shadow_only"
        elif kind not in tool.supported_inputs:
            reason = "unsupported_input"
        elif pinned is not None and pin not in pinned:
            reason = "not_in_pinned_plan"
        elif tool.status == "disabled":
            reason = tool.reason
        elif tool.runner == "isolated_cli" and not external:
            reason = "offline_runner_required"
        else:
            reason = "eligible"
        decisions.append(ToolSelection(**pin, status="selected" if reason == "eligible" else "skipped", reason=reason))
    return decisions


def analyzer_plan(kind):
    return [tool.model_dump(include={"id", "version"}) for tool in resolve_analyzers(kind) if tool.status == "selected"]


def manifests():
    tools = [
        ToolManifest(id=tool, version=TOOL_PROTOCOL_VERSION, title_en=names[0], title_ar=names[1],
                     supported_inputs=ALL_INPUTS, license="MIT", capabilities=[tool])
        for tool, names in INTERNAL_TOOL_TITLES.items()
    ]
    tools.extend(analyzer_manifests())
    source_tools = configured_tools()
    roles = [
        RoleManifest(id=role, tools=[*allowed, *(tool.id for tool in source_tools if role == "analysis")],
                     input_contract=ROLE_BOUNDARIES[role][0],
                     output_contract=ROLE_BOUNDARIES[role][1])
        for role, allowed in ROLE_TOOLS.items()
    ]
    return tools, roles
