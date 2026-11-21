"""Versioned review contracts shared by storage, streaming, and report downloads."""
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .phase9_contracts import ArtifactKind, CoverageStatus

MAX_SOURCE_BYTES = 1_000_000
MAX_SOURCE_CHARS = 250_000
SourceKind = Literal["sample", "paste", "file"]
Severity = Literal["high", "medium", "low"]
Enrichment = Literal["model", "fallback", "disabled"]
DecisionSource = Literal["model", "system"]


class SourceInput(BaseModel):
    kind: SourceKind
    name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_file(self):
        if self.kind == "file":
            name = self.name or ""
            if (not name.lower().endswith((".html", ".htm")) or
                    any(char in "/\\:" or ord(char) < 32 or ord(char) == 127 for char in name)):
                raise ValueError("Expected an HTML file name")
        elif self.name is not None:
            raise ValueError("A file name requires a file source")
        return self


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS, description="Untrusted HTML text")
    source_info: SourceInput | None = None
    profile: Literal["baseline", "extended"] = "baseline"

    @field_validator("source")
    @classmethod
    def validate_source(cls, value):
        if (not value.strip() or re.search(r"[\x00-\x08\x0b\x0e-\x1f]", value) or
                len(value.encode("utf-8")) > MAX_SOURCE_BYTES):
            raise ValueError("Invalid source content or length")
        if ">" not in value or not re.search(r"<[A-Za-z][^<>\s/]*(?:[\s/>])", value):
            raise ValueError("Source must include an HTML element")
        return value

class SourceInfo(SourceInput):
    bytes: int = Field(ge=1, le=MAX_SOURCE_BYTES)
    lines: int = Field(ge=1)
    encoding: Literal["utf-8"] = "utf-8"


class FindingOrigin(BaseModel):
    tool: str = Field(max_length=64)
    version: str = Field(max_length=64)
    rule: str = Field(max_length=80)


class AdvisoryEvidence(BaseModel):
    id: str = Field(max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    ecosystem: Literal["PyPI"]
    package: str = Field(max_length=150)
    version: str = Field(max_length=100)
    database_date: date


class Finding(BaseModel):
    rule: str
    severity: Severity
    line: int = Field(ge=1)
    evidence: str
    title: str
    title_ar: str | None = None
    remediation: str
    remediation_ar: str | None = None
    domain: str | None = None
    confidence: str | None = None
    assessment: Literal["observed", "review_required"] | None = None
    path: str | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    origins: list[FindingOrigin] = Field(default_factory=list)
    advisory: AdvisoryEvidence | None = None


class RuleCoverage(BaseModel):
    rule: str
    domain: str
    status: CoverageStatus
    match_count: int = Field(ge=0)
    reason: str | None = None


class ArtifactInfo(BaseModel):
    kind: ArtifactKind
    name: str
    bytes: int = Field(ge=1)


class Benchmark(BaseModel):
    matched: int
    expected: int
    unexpected: int
    passed: bool


class Metrics(BaseModel):
    checksRun: int | None = None
    findingsCount: int | None = None
    validatedCount: int | None = None
    modelCalls: int | None = None
    durationMs: int | None = None
    inputTokens: int | None = None
    outputTokens: int | None = None
    benchmark: Benchmark | None = None


class Step(BaseModel):
    node: str
    role: str | None = None
    status: Literal["start", "done"]
    parents: list[str]
    detail: str
    detail_en: str | None = None
    source: DecisionSource | None = None
    occurred_at: str | None = None
    scan_id: str | None = None


class TaskRun(BaseModel):
    id: str
    agent: str
    tool: str
    status: Literal["done", "partial", "error", "not_applicable"]
    checks: int = Field(ge=0)
    matched: int = Field(ge=0)
    coverage: list[str] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)
    version: str | None = None
    database_date: date | None = None
    reason: str | None = None


class APIInventory(BaseModel):
    version: str
    operations: int = Field(ge=0)
    declared_auth: int = Field(ge=0)
    anonymous_operations: int = Field(ge=0)
    local_references: int = Field(ge=0)
    unresolved_references: int = Field(ge=0)
    security_schemes: dict[Literal["apiKey", "http", "oauth2", "openIdConnect", "mutualTLS", "unresolved"],
                           Annotated[int, Field(ge=0)]] | None = None
    unresolved_security_requirements: int | None = Field(default=None, ge=0)


class InputManifestEntry(BaseModel):
    path: str = Field(max_length=240)
    status: Literal["included", "skipped"]
    reason: Literal["unsupported_extension"] | None = None


class ImportedEvidence(BaseModel):
    source: Literal["zap-passive-report"]
    status: Literal["imported"]
    accepted_alerts: int = Field(ge=0, le=500)
    skipped_alerts: int = Field(ge=0, le=500)


class Report(BaseModel):
    schema_version: Literal[1, 2] = 1
    id: str
    created_at: str
    model: str | None
    status: Literal["completed", "partial"] = "completed"
    source: SourceInfo | None = None
    input_artifact: ArtifactInfo | None = None
    api_inventory: APIInventory | None = None
    policy_version: int | None = None
    ruleset_version: str | None = None
    priority: list[str] | None = None
    input_paths: list[str] | None = None
    input_manifest: list[InputManifestEntry] | None = Field(default=None, max_length=200)
    imported_evidence: ImportedEvidence | None = None
    task_runs: list[TaskRun] = Field(default_factory=list)
    enrichment: Enrichment | None = None
    summary_source: DecisionSource | None = None
    summary_ar: str
    summary_en: str
    findings: list[Finding]
    coverage: list[RuleCoverage] | None = None
    steps: list[Step] = Field(default_factory=list)
    metrics: Metrics


class HistoryItem(BaseModel):
    id: str
    created_at: str
    model: str | None
    finding_count: int
    unique_count: int
    source: SourceInfo | None
    input_artifact: ArtifactInfo | None = None
    status: Literal["completed", "partial"]
    enrichment: Enrichment | None
    domains: list[str]
    severities: list[Severity]


class History(BaseModel):
    reports: list[HistoryItem]


def history_item(report: Report):
    return HistoryItem(
        id=report.id, created_at=report.created_at, model=report.model, source=report.source,
        status=report.status, enrichment=report.enrichment, finding_count=len(report.findings),
        input_artifact=report.input_artifact,
        unique_count=len({finding.rule for finding in report.findings}),
        domains=sorted({item.domain for item in report.coverage or []} |
                       {finding.domain for finding in report.findings if finding.domain}),
        severities=sorted({finding.severity for finding in report.findings}),
    )


class StepEvent(Step):
    type: Literal["step"] = "step"


class CompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    report: Report


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    scan_id: str
    status: Literal["failed"] = "failed"
    message: str


RunEvent = Annotated[StepEvent | CompleteEvent | ErrorEvent, Field(discriminator="type")]
