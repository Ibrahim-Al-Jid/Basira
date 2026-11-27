"""Project dashboard (P10 slice e, P20 presentation view).

Every number carries the scan it came from and that scan's timestamp, so it can be traced back to a
report. Nothing here is estimated: counts are read from the stored reports, and "new" and "resolved"
come from the existing report comparison (finding fingerprints), only when two scans are comparable.
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from . import advanced_reporting as advanced
from . import platform_runtime as store
from .contracts import Report

SCAN_LIMIT = 12
EVALUATED = {"clear", "matched"}
SEVERITIES = ("high", "medium", "low")


def scan_point(report):
    severity = {name: 0 for name in SEVERITIES}
    for finding in report.findings:
        severity[finding.severity] = severity.get(finding.severity, 0) + 1
    coverage = report.coverage or []
    return {
        "scan_id": report.id, "created_at": report.created_at, "status": report.status,
        "findings": len(report.findings), "unique_findings": len({finding.rule for finding in report.findings}),
        "severity": severity,
        "coverage": {"ran": sum(1 for item in coverage if item.status in EVALUATED), "total": len(coverage)} if coverage else None,
        "name": report.input_artifact.name if report.input_artifact else None,
    }


def change_summary(current, baseline, current_policy, baseline_policy):
    """New and resolved findings of `current` against `baseline`, or why they cannot be compared."""
    result = advanced.compare(current, baseline, current_policy, baseline_policy)
    summary = {"baseline_scan_id": baseline.id, "comparable": result["comparable"], "reason": result["reason"]}
    if result["comparable"]:
        counts = {"new": 0, "resolved": 0, "unchanged": 0, "coverage_changed": 0}
        for item in result["changes"]:
            counts[item["change"]] += 1
        summary.update(counts)
    return summary


def build(entries, now=None):
    """`entries` is a list of (Report, policy), newest first. Returns the dashboard, oldest scan first."""
    now = now or datetime.now(timezone.utc)
    ordered = list(entries)[:SCAN_LIMIT]
    scans = []
    for index, (report, policy) in enumerate(ordered):
        point = scan_point(report)
        previous = ordered[index + 1] if index + 1 < len(ordered) else None
        point["change"] = change_summary(report, previous[0], policy, previous[1]) if previous else None
        scans.append(point)
    scans.reverse()
    return {"as_of": now.isoformat().replace("+00:00", "Z"), "scan_limit": SCAN_LIMIT, "scans": scans,
            "latest": scans[-1] if scans else None}


def read(ctx):
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        rows = db.execute(sa.select(store.scans.c.id, store.scans.c.report, store.scans.c.policy).where(
            store.scope(store.scans, ctx.org_id, ctx.project_id), store.scans.c.state.in_(["completed", "partial"]),
            store.scans.c.report.is_not(None),
        ).order_by(store.scans.c.updated_at.desc()).limit(SCAN_LIMIT)).mappings().all()
        entries = [(Report.model_validate(row["report"]), row["policy"] or {}) for row in rows]
    return build(entries)
