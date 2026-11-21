"""Versioned, offline project-scan capabilities and evidence provenance."""
from datetime import datetime
from hashlib import sha256
from importlib import import_module
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

ArtifactKind = Literal["html", "repository", "har", "config"]
CoverageStatus = Literal["matched", "clear", "not_applicable", "skipped", "error"]
AgentRole = Literal["orchestrator", "planning", "analysis", "validation", "reporting"]
Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ModelConnection = Literal["openrouter-default"]

PROFILE = "offline-artifact"
TOOL_PROTOCOL_VERSION = "marsad-tool-1"
RAW_RETENTION_MINUTES = 15
ALL_INPUTS = ("html", "repository", "har", "config")
ANALYZER_INPUTS = {
    "html-attributes": ("html", "repository", "config"),
    "browser-controls": ALL_INPUTS,
    "dependency-evidence": ("repository", "config"),
    "deployment-config": ("repository", "config"),
    "browser-controls-extra": ALL_INPUTS,
    "deployment-config-extra": ("repository", "config"),
}
ANALYZER_TITLES = {
    "html-attributes": "HTML attributes",
    "browser-controls": "Browser and response controls",
    "dependency-evidence": "Dependency evidence",
    "deployment-config": "Deployment configuration",
    "browser-controls-extra": "Extended browser and response controls",
    "deployment-config-extra": "Extended dependency and deployment controls",
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
    reason: Literal["adapter_unavailable"] | None = None


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
    source: Literal["project_policy"] = "project_policy"


class SourceSnapshot(BaseModel):
    id: Identifier
    sha256: Digest
    kind: ArtifactKind
    bytes: int = Field(ge=1)
    created_at: datetime
    raw_expires_at: datetime


class ScopeVersion(BaseModel):
    version: int = Field(ge=0)
    sha256: Digest
    asset_id: Identifier | None
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


def analyzer_plan(kind):
    from .artifact_review import ADAPTERS, RULESET_VERSION
    adapters = {entry.id: entry for entry in ADAPTERS}
    return [
        {"id": tool, "version": RULESET_VERSION}
        for tool, inputs in ANALYZER_INPUTS.items()
        if kind in inputs and (tool == "html-attributes" or adapter_available(adapters[tool]))
    ]


def manifests():
    from .artifact_review import ADAPTERS, RULESET_VERSION
    adapters = {entry.id: entry for entry in ADAPTERS}
    tools = [
        ToolManifest(id=tool, version=TOOL_PROTOCOL_VERSION, title_en=names[0], title_ar=names[1],
                     supported_inputs=ALL_INPUTS)
        for tool, names in INTERNAL_TOOL_TITLES.items()
    ]
    for tool, inputs in ANALYZER_INPUTS.items():
        adapter = adapters.get(tool)
        available = not adapter or adapter_available(adapter)
        tools.append(ToolManifest(
            id=tool, version=RULESET_VERSION, title_en=ANALYZER_TITLES[tool],
            title_ar=adapter.title_ar if adapter else "خصائص HTML الأساسية",
            supported_inputs=inputs, status="available" if available else "disabled",
            reason=None if available else "adapter_unavailable",
        ))
    roles = [
        RoleManifest(id=role, tools=allowed, input_contract=ROLE_BOUNDARIES[role][0],
                     output_contract=ROLE_BOUNDARIES[role][1])
        for role, allowed in ROLE_TOOLS.items()
    ]
    return tools, roles
