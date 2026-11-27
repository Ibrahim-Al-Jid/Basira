"""Compare eligible project reports, preserve review history and export SARIF."""
import hashlib
import json
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
import sqlalchemy as sa

from .artifact_review import InputError, safe_path
from .contracts import Report
from .identity import member_name
from .platform_db import User
from . import platform_runtime as store

metadata = store.metadata


def scoped_columns(*, pk):
    return [sa.Column("org_id", sa.String(32), nullable=False, primary_key=pk),
            sa.Column("project_id", sa.String(32), nullable=False, primary_key=pk),
            sa.Column("fingerprint", sa.String(64), nullable=False, primary_key=pk)]


reviews = sa.Table(
    "finding_reviews", metadata, *scoped_columns(pk=True),
    sa.Column("status", sa.String(16), nullable=False),
    sa.ForeignKeyConstraint(("org_id", "project_id"), ("projects.org_id", "projects.id")),
    sa.CheckConstraint("status IN ('open','triaged','resolved','accepted')", name="ck_finding_reviews_status"),
)
activities = sa.Table(
    "finding_review_activity", metadata, *scoped_columns(pk=False),
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("author_id", sa.String(32), nullable=False),
    sa.Column("author", sa.String(200), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("action", sa.String(12), nullable=False),
    sa.Column("status", sa.String(16)),
    sa.Column("previous", sa.String(16)),
    sa.Column("body", sa.String(2000)),
    sa.ForeignKeyConstraint(("org_id", "project_id", "fingerprint"),
                            ("finding_reviews.org_id", "finding_reviews.project_id", "finding_reviews.fingerprint"),
                            ondelete="CASCADE"),
    sa.Index("ix_review_activity_timeline", "org_id", "project_id", "fingerprint", "created_at"),
)
STATUS = Literal["open", "triaged", "resolved", "accepted"]


class ReviewAction(BaseModel):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["comment", "status"]
    body: str | None = Field(default=None, max_length=2000)
    status: STATUS | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "comment":
            if not (self.body or "").strip() or self.status is not None or self.reason is not None:
                raise ValueError("A comment requires text")
        elif self.body is not None or not self.status or not (self.reason or "").strip():
            raise ValueError("A status change requires a status and reason")
        return self


def scope_key(report, policy):
    if report.input_artifact:
        artifact = report.input_artifact
        return (artifact.kind, artifact.name, policy.get("base_url"))
    return None


def points(report, policy):
    groups = {}
    target = scope_key(report, policy) or ("legacy", report.id)
    for finding in report.findings:
        values = (target, finding.rule, finding.path)
        identifier = hashlib.sha256(json.dumps(values, ensure_ascii=True).encode()).hexdigest()
        if identifier not in groups:
            groups[identifier] = {"fingerprint": identifier, "rule": finding.rule, "path": finding.path, "count": 0}
        groups[identifier]["count"] += 1
    return groups


def compare(current, baseline, current_policy, baseline_policy):
    data = {"baseline": baseline.id, "current": current.id, "comparable": False, "reason": None, "changes": []}
    if current.coverage is None or baseline.coverage is None or not (
        scope_key(current, current_policy) and scope_key(baseline, baseline_policy)
    ):
        return {**data, "reason": "coverage_unavailable"}
    if {current.input_artifact.kind, baseline.input_artifact.kind} & {"har", "zap"}:
        return {**data, "reason": "coverage_unavailable"}
    if scope_key(current, current_policy) != scope_key(baseline, baseline_policy):
        return {**data, "reason": "incompatible_scope"}
    if current.policy_version != baseline.policy_version:
        return {**data, "reason": "incompatible_policy"}
    if current.ruleset_version != baseline.ruleset_version:
        return {**data, "reason": "incompatible_ruleset"}
    before, after = points(baseline, baseline_policy), points(current, current_policy)
    previous_status = {rule.rule: rule.status for rule in baseline.coverage}
    current_status = {rule.rule: rule.status for rule in current.coverage}
    evaluated = {"clear", "matched"}
    def source_observed(report, path):
        if not path:
            return True
        if report.input_paths is not None:
            # Aggregate coverage cannot prove a rule ran on one particular file in a bundle.
            return report.input_paths == [path] and report.input_artifact.kind == "html"
        return report.input_artifact.kind == "html" and report.input_artifact.name == path
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        point = new or old
        rule = point["rule"]
        prior_count, count = old["count"] if old else 0, new["count"] if new else 0
        if previous_status.get(rule) not in evaluated or current_status.get(rule) not in evaluated:
            change = "coverage_changed"
        elif point["path"] and (
            (not prior_count and not source_observed(baseline, point["path"]))
            or (not count and not source_observed(current, point["path"]))
        ):
            change = "coverage_changed"
        elif not prior_count:
            change = "new"
        elif not count:
            change = "resolved"
        else:
            change = "unchanged"
        data["changes"].append({"fingerprint": key, "rule": rule, "path": point["path"], "change": change,
                                "before": prior_count, "after": count})
    return {**data, "comparable": True}


def read_report(ctx, report_id):
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        row = db.execute(sa.select(store.scans.c.report, store.scans.c.policy).where(
            store.scope(store.scans, ctx.org_id, ctx.project_id), store.scans.c.id == report_id,
        )).mappings().first()
        if row and row["report"]:
            return Report.model_validate(row["report"]), row["policy"]
        legacy = db.execute(sa.select(store.legacy.c.report).where(
            store.scope(store.legacy, ctx.org_id, ctx.project_id), store.legacy.c.legacy_id == report_id,
        )).scalar_one_or_none()
        if legacy:
            return Report.model_validate(legacy), {}
    raise HTTPException(404, "التقرير غير متاح في المشروع ده.")


def review_scope(table, ctx):
    return store.scope(table, ctx.org_id, ctx.project_id)


def review_items(db, ctx, fingerprints):
    entries = {key: {"fingerprint": key, "rule": point["rule"], "path": point["path"], "status": "open",
                     "comments": [], "history": []} for key, point in fingerprints.items()}
    if not entries:
        return entries
    for row in db.execute(sa.select(reviews).where(review_scope(reviews, ctx),
                                                  reviews.c.fingerprint.in_(entries))).mappings():
        entries[row["fingerprint"]]["status"] = row["status"]
    activity = db.execute(sa.select(activities).where(review_scope(activities, ctx),
                                                       activities.c.fingerprint.in_(entries))
                          .order_by(activities.c.created_at.desc(), activities.c.id.desc())).mappings()
    for row in activity:
        payload = {"id": row["id"], "author": member_name(row["author"]), "created_at": store.timestamp(row["created_at"])}
        entry = entries[row["fingerprint"]]
        if row["action"] == "comment":
            entry["comments"].append({**payload, "body": row["body"]})
        else:
            entry["history"].append({**payload, "status": row["status"], "previous": row["previous"],
                                     "reason": row["body"]})
    return entries


def get_review(ctx, report_id):
    report, policy = read_report(ctx, report_id)
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        return {"items": list(review_items(db, ctx, points(report, policy)).values()),
                "can_edit": ctx.role in {"owner", "admin", "analyst"}}


def change_review(ctx, report_id, action):
    report, policy = read_report(ctx, report_id)
    point = points(report, policy).get(action.fingerprint)
    if not point:
        raise HTTPException(404, "النتيجة غير متاحة في التقرير ده.")
    with store.platform_session() as db:
        store.bind_project_context(db, ctx)
        projects = metadata.tables["projects"]
        db.execute(sa.select(projects.c.id).where(projects.c.org_id == ctx.org_id,
                                                  projects.c.id == ctx.project_id).with_for_update()).one()
        who = db.get(User, ctx.user_id)
        scoped = {"org_id": ctx.org_id, "project_id": ctx.project_id, "fingerprint": action.fingerprint}
        condition = sa.and_(review_scope(reviews, ctx), reviews.c.fingerprint == action.fingerprint)
        status = db.execute(sa.select(reviews.c.status).where(condition)).scalar_one_or_none()
        if not status:
            status = "open"
            db.execute(reviews.insert().values(**scoped, status=status))
        if action.action == "status" and action.status == status:
            raise HTTPException(409, "النتيجة بالفعل في الحالة دي.")
        count = db.execute(sa.select(sa.func.count()).select_from(activities).where(
            review_scope(activities, ctx), activities.c.fingerprint == action.fingerprint,
        )).scalar_one()
        if count >= 200:
            raise HTTPException(409, "وصل سجل النتيجة للحد الأقصى.")
        if action.action == "status":
            db.execute(reviews.update().where(condition).values(status=action.status))
        db.execute(activities.insert().values(**scoped, id=uuid4().hex, author_id=ctx.user_id,
                   author=member_name(who.display_name), created_at=store.now(), action=action.action,
                   status=action.status, previous=status if action.status else None,
                   body=(action.body if action.action == "comment" else action.reason).strip()))
        return review_items(db, ctx, {action.fingerprint: point})[action.fingerprint]


SARIF_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"


def sarif(report, lang):
    rules = {}
    results = []
    for item in report.findings:
        if not item.path or (report.input_artifact and report.input_artifact.kind == "har"):
            continue
        try:
            location = quote(safe_path(item.path), safe="/")
        except InputError:
            continue
        title = (item.title_ar or item.title) if lang == "ar" else item.title
        remediation = (item.remediation_ar or item.remediation) if lang == "ar" else item.remediation
        rules.setdefault(item.rule, {"id": item.rule, "shortDescription": {"text": title},
                                     "help": {"text": remediation}})
        level = {"high": "error", "medium": "warning", "low": "note"}[item.severity]
        properties = {"assessment": item.assessment} if item.assessment else {}
        if item.origins:
            properties["observedBy"] = [origin.model_dump(mode="json") for origin in item.origins]
        if item.advisory:
            properties["advisory"] = item.advisory.model_dump(mode="json")
        physical = {"artifactLocation": {"uri": location}}
        if item.domain != "api" and not (report.input_artifact and report.input_artifact.kind == "zap"):
            physical["region"] = {"startLine": item.line}
        results.append({"ruleId": item.rule, "level": level, "message": {"text": title + " · " + item.evidence},
                        "locations": [{"physicalLocation": physical}],
                        **({"properties": properties} if properties else {}),
                        **({"partialFingerprints": {"basiraEvidence/v1": item.fingerprint}} if item.fingerprint else {})})
    return {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "Basira", "version": report.ruleset_version or "legacy",
                             "rules": list(rules.values())}},
        "language": lang, "results": results, "properties": {"reportId": report.id},
    }]}
