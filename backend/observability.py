"""One access-log line per request, with a correlation id.

The image starts uvicorn with ``--no-access-log`` so nothing recorded requests
at all. This middleware logs the method, the path without its query string
(query strings can carry tokens), the status, the duration and a request id the
person reporting a problem can quote. Static assets are skipped: they are not
what an incident report is about.

``BASIRA_LOG_LEVEL`` sets the level (DEBUG, INFO, WARNING or ERROR; INFO by
default). A bad value falls back to INFO instead of stopping the app.
"""

import logging
import os
import time
import traceback
from pathlib import Path
from uuid import uuid4

LOGGER = logging.getLogger("basira.access")
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
WORKER_LOGGER = logging.getLogger("basira.worker")
STATIC_PREFIXES = ("/assets/", "/favicon.ico", "/mark.svg", "/basira-network-globe.webp")


def install_observability(app):
    """Register the access log on ``app`` and configure the root logger once."""
    level_name = os.environ.get("BASIRA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name) if level_name in LEVELS else logging.INFO
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    LOGGER.setLevel(level)

    @app.middleware("http")
    async def access_log(request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("request_failed id=%s method=%s path=%s", request_id,
                             request.method, request.url.path)
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        if not request.url.path.startswith(STATIC_PREFIXES):
            LOGGER.log(level, "request id=%s method=%s path=%s status=%s duration_ms=%.1f",
                       request_id, request.method, request.url.path, response.status_code, duration_ms)
        response.headers["X-Request-ID"] = request_id
        return response

    return app


def log_failure(event, error):
    """Record that background work failed: the exception class and where it was raised, never its message or
    arguments, which can carry submitted file names or values."""
    frames = traceback.extract_tb(error.__traceback__)
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "unknown"
    WORKER_LOGGER.error("%s error=%s at=%s", event, type(error).__name__, where)
