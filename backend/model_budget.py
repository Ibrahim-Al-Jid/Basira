"""Per-scan model request budget check (P20).

The free OpenRouter tier allows a fixed number of requests per day, shared by every run on the key.
This check counts the model requests that Basira itself started today (UTC) in the project and refuses
to start the model stage when the remaining count is below what one scan needs. The scan still
finishes on the deterministic path. The count covers requests made through this app only: use of the
same key elsewhere is not visible here, which is why the demo runbook keeps a manual quota check.
"""
from datetime import datetime, timezone
import os

from .model_connections import MAX_MODEL_CALLS

FREE_DAILY_REQUESTS = 50


def daily_limit(model, environ=None):
    """The daily request limit that applies, or None when none is known.

    `BASIRA_MODEL_DAILY_LIMIT` wins (0 or more). Otherwise a ":free" model gets the measured free-tier
    limit, and any other model has no limit that Basira knows about."""
    environ = os.environ if environ is None else environ
    raw = environ.get("BASIRA_MODEL_DAILY_LIMIT", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = -1
        if value >= 0:
            return value
    return FREE_DAILY_REQUESTS if str(model or "").endswith(":free") else None


def utc_day_start(moment=None):
    moment = moment or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def decide(limit, used, needed=MAX_MODEL_CALLS):
    """Budget verdict with a reason in Arabic and English. Unknown limit means allowed."""
    if limit is None:
        return {"allowed": True, "limit": None, "used": used, "remaining": None, "needed": needed}
    remaining = max(0, limit - used)
    verdict = {"allowed": remaining >= needed, "limit": limit, "used": used, "remaining": remaining, "needed": needed}
    if not verdict["allowed"]:
        verdict["reason_ar"] = (f"المتبقي من طلبات الموديل اليوم {remaining} من {limit}، والفحص محتاج {needed}. "
                                "كمّلنا بالمسار الحتمي بدون موديل.")
        verdict["reason_en"] = (f"{remaining} of {limit} model requests left today, the scan needs {needed}. "
                                "Continued on the deterministic path without the model.")
    return verdict
