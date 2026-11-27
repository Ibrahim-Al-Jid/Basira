from datetime import datetime, timedelta, timezone

from . import model_budget as budget, platform_runtime as store
from .platform_db import platform_session
from .test_platform_runtime import artifact, platform, submit  # noqa: F401  (fixture and helper)


def test_daily_limit_sources():
    assert budget.daily_limit("x/y:free", {}) == 50
    assert budget.daily_limit("openai/gpt", {}) is None
    assert budget.daily_limit("openai/gpt", {"BASIRA_MODEL_DAILY_LIMIT": "10"}) == 10
    assert budget.daily_limit("x:free", {"BASIRA_MODEL_DAILY_LIMIT": "0"}) == 0
    assert budget.daily_limit("x:free", {"BASIRA_MODEL_DAILY_LIMIT": "abc"}) == 50
    assert budget.daily_limit(None, {"BASIRA_MODEL_DAILY_LIMIT": "-3"}) is None


def test_decision_refuses_when_remaining_is_too_low():
    assert budget.decide(None, 999)["allowed"]
    assert budget.decide(50, 48)["allowed"]
    low = budget.decide(50, 50)
    assert not low["allowed"] and low["remaining"] == 0
    assert "50" in low["reason_ar"] and "50" in low["reason_en"]
    assert not budget.decide(50, 70)["allowed"] and budget.decide(50, 70)["remaining"] == 0
    assert not budget.decide(5, 3, needed=3)["allowed"]


def test_day_start_is_utc_midnight():
    cairo = timezone(timedelta(hours=2))
    assert budget.utc_day_start(datetime(2026, 11, 28, 1, 30, tzinfo=cairo)) == datetime(2026, 11, 27, tzinfo=timezone.utc)


def test_requests_today_counts_only_started_calls_since_midnight(platform):  # noqa: F811
    owner, _stranger, ctx = platform
    first = submit(owner, ctx, key="budget-key-1").json()["id"]
    second = submit(owner, ctx, data=artifact(name="two.html", content=b"<p>two</p>"), key="budget-key-2").json()["id"]
    assert store.model_requests_today(ctx.org_id, ctx.project_id) == 0
    with platform_session() as db:
        db.execute(store.scans.update().where(store.scans.c.id == first).values(enrichment_started_at=store.now()))
        db.execute(store.scans.update().where(store.scans.c.id == second)
                   .values(enrichment_started_at=store.now() - timedelta(days=2)))
    assert store.model_requests_today(ctx.org_id, ctx.project_id) == 1
    assert store.model_requests_today(ctx.org_id, "no-such-project") == 0


def test_skipped_stage_can_be_recorded(platform):  # noqa: F811
    owner, _stranger, ctx = platform
    scan = submit(owner, ctx, key="budget-key-3").json()["id"]
    claimed = store.claim(ctx.org_id, ctx.project_id, scan)
    assert store.record_stage(ctx.org_id, ctx.project_id, scan, claimed["lease"], "model_skipped", "x")
