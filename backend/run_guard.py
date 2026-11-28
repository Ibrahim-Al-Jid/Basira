"""Rate and concurrency guard for the anonymous lab run intake (taxonomy D11.3).

The platform scan path checks a per-project daily model budget before it starts the model
stage. The lab path (POST /api/run) never got an equivalent guard, so any unauthenticated
client could start runs without limit: each run holds a worker up to 300 seconds, can spend
shared model quota, and stores session and report rows. This guard caps runs per client IP
per fixed 15-minute window and caps concurrent in-flight runs, per process. Both limits are
env-tunable; a value of 0 or less turns that limit off. State is in-memory: the lab can run
without the platform database, so there is no shared store here, and a multi-worker deploy
gets the limit per worker rather than globally.
"""
import os
import time

from fastapi import HTTPException, Request

WINDOW_SECONDS = 900
DEFAULT_RUN_LIMIT = 30
DEFAULT_CONCURRENCY = 8

_counts = {}
_active = 0


def _env_int(name, default, environ=None):
    environ = os.environ if environ is None else environ
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def lab_run_limit(environ=None):
    """Runs allowed per client IP per window; 0 or less disables the limit."""
    return _env_int("BASIRA_LAB_RUN_LIMIT", DEFAULT_RUN_LIMIT, environ)


def lab_run_concurrency(environ=None):
    """Concurrent in-flight lab runs per process; 0 or less disables the cap."""
    return _env_int("BASIRA_LAB_RUN_CONCURRENCY", DEFAULT_CONCURRENCY, environ)


def reserve_run(request: Request):
    """Count one lab run start or raise 429. Pair every success with release_run()."""
    global _active
    peer = request.client.host if request.client else "unknown"
    window = int(time.time()) // WINDOW_SECONDS
    limit = lab_run_limit()
    if limit > 0:
        for key in [key for key in _counts if key[1] < window - 1]:
            del _counts[key]
        key = (peer, window)
        used = _counts.get(key, 0)
        if used >= limit:
            raise HTTPException(429, "وصلت لحد عدد الفحوصات المجانية. حاول بعد شوية.",
                                headers={"Retry-After": str(WINDOW_SECONDS)})
        _counts[key] = used + 1
    cap = lab_run_concurrency()
    if cap > 0 and _active >= cap:
        raise HTTPException(429, "في فحوصات كتير شغالة دلوقتي. حاول بعد شوية.",
                            headers={"Retry-After": "60"})
    _active += 1


def release_run():
    global _active
    _active = max(0, _active - 1)


def reset():
    """Test hook: drop all limiter state."""
    global _active
    _counts.clear()
    _active = 0
