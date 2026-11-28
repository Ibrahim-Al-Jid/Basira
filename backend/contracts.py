"""Versioned review contracts shared by storage, streaming, and report downloads."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .analysis_mode import AnalysisMode
from .scan_contracts import ArtifactKind, CoverageStatus, Digest, GitHubSnapshotRef, Identifier, TargetProfile, ToolSelection

MAX_SOURCE_BYTES = 1_000_000
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
    ecosystem: Literal["PyPI", "npm"]
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


class AgentFinding(BaseModel):
    """A place the Hunter pointed at that the Auditor re-read in the snapshot. Never a rules finding."""
    source: Literal["agent"] = "agent"
    assessment: Literal["review_required"] = "review_required"
    rule: str = Field(max_length=80)
    path: str = Field(max_length=240)
    line: int = Field(ge=1)
    quote: str = Field(max_length=300)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentPhase(BaseModel):
    """One role's part in an agent run. Maestro, Scout, the Hunter (with the Auditor inside) and Scribe each get one."""
    role: Literal["maestro", "scout", "hunter", "scribe"]
    status: Literal["completed", "fell_back", "skipped"]
    reason_code: Literal["model_error", "invalid_output", "budget_steps", "budget_tool_calls", "budget_tokens",
                         "budget_time", "not_planned", "empty"] | None = Field(
        default=None, exclude_if=lambda value: value is None)


class AgentRun(BaseModel):
    """How the Hunter's run ended for this scan. Absent when the agent path never ran."""
    status: Literal["completed", "fell_back"]
    reason_code: Literal["model_unavailable", "model_error", "invalid_output", "budget_steps", "budget_tool_calls",
                         "budget_tokens", "budget_time"] | None = Field(default=None, exclude_if=lambda value: value is None)
    phases: list[AgentPhase] = Field(default_factory=list, max_length=4, exclude_if=lambda value: not value)


class AgentSummary(BaseModel):
    """Scribe's model-written summary. It sits beside summary_en and summary_ar and never replaces them."""
    source: Literal["agent"] = "agent"
    summary_en: str = Field(min_length=1, max_length=800)
    summary_ar: str = Field(min_length=1, max_length=800)
    cited: list[str] = Field(default_factory=list, max_length=200)


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
    github: GitHubSnapshotRef | None = Field(default=None, exclude_if=lambda value: value is None)
    profile: TargetProfile | None = Field(default=None, exclude_if=lambda value: value is None)
    # Reports made before run modes existed were rules-only scans, so the defaults are correct for them.
    analysis_mode: AnalysisMode = "rules"
    mode_effective: AnalysisMode = "rules"
    fallback_reason: Literal["agent_path_unavailable"] | None = Field(default=None, exclude_if=lambda value: value is None)


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
    contract: Literal["basira-tool-result-1"] | None = Field(default=None, exclude_if=lambda value: value is None)
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
    reason: Literal["unsupported_extension", "build_artifact"] | None = None


class ImportedEvidence(BaseModel):
    source: Literal["zap-passive-report"]
    status: Literal["imported"]
    accepted_alerts: int = Field(ge=0, le=500)
    skipped_alerts: int = Field(ge=0, le=500)


class AgentExecution(BaseModel):
    contract: Literal["basira-agent-workflow-1"] = "basira-agent-workflow-1"
    trace_id: Identifier
    input_kind: ArtifactKind
    source_sha256: Digest
    inventory_sha256: Digest
    plan_sha256: Digest
    evidence_sha256: Digest
    files_read: int = Field(ge=0, le=200)
    validated_locations: int = Field(ge=0, le=5000)


class PlanningAdvice(BaseModel):
    tool: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    label: Literal["review_tool_coverage", "review_tool_findings"]


class ValidationAdvice(BaseModel):
    fingerprint: Digest
    label: Literal["review_evidence", "review_context"]


class ExplanationAdvice(BaseModel):
    fingerprint: Digest
    label: Literal["read_remediation", "confirm_scope"]


class AgentAdvisory(BaseModel):
    version: Literal["basira-advisor-1"]
    planning: list[PlanningAdvice] = Field(max_length=12)
    validation: list[ValidationAdvice] = Field(max_length=12)
    explanation: list[ExplanationAdvice] = Field(max_length=12)


class ReviewContext(BaseModel):
    fingerprint: Digest
    prior_scan_id: Identifier
    status: Literal["triaged", "resolved", "accepted"]


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
    tool_selection: list[ToolSelection] = Field(default_factory=list, exclude_if=lambda value: not value)
    execution: AgentExecution | None = Field(default=None, exclude_if=lambda value: value is None)
    agent_advisory: AgentAdvisory | None = Field(default=None, exclude_if=lambda value: value is None)
    review_context: list[ReviewContext] = Field(default_factory=list, max_length=20, exclude_if=lambda value: not value)
    enrichment: Enrichment | None = None
    summary_source: DecisionSource | None = None
    summary_ar: str
    summary_en: str
    findings: list[Finding]
    agent_run: AgentRun | None = Field(default=None, exclude_if=lambda value: value is None)
    agent_findings: list[AgentFinding] = Field(default_factory=list, max_length=50, exclude_if=lambda value: not value)
    agent_summary: AgentSummary | None = Field(default=None, exclude_if=lambda value: value is None)
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
