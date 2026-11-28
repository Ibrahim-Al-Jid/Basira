"""Lab run guard: per-IP window limit and concurrency cap on POST /api/run."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from . import main, run_guard


class EnvTests(unittest.TestCase):
    def setUp(self):
        run_guard.reset()

    def test_defaults_apply_without_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BASIRA_LAB_RUN_LIMIT", None)
            os.environ.pop("BASIRA_LAB_RUN_CONCURRENCY", None)
            assert run_guard.lab_run_limit({}) == 30
            assert run_guard.lab_run_concurrency({}) == 8

    def test_env_overrides_and_zero_disables(self):
        env = {"BASIRA_LAB_RUN_LIMIT": "5", "BASIRA_LAB_RUN_CONCURRENCY": "2"}
        assert run_guard.lab_run_limit(env) == 5
        assert run_guard.lab_run_concurrency(env) == 2
        off = {"BASIRA_LAB_RUN_LIMIT": "0", "BASIRA_LAB_RUN_CONCURRENCY": "-1"}
        assert run_guard.lab_run_limit(off) == 0
        assert run_guard.lab_run_concurrency(off) == -1

    def test_invalid_env_falls_back_to_default(self):
        bad = {"BASIRA_LAB_RUN_LIMIT": "soon", "BASIRA_LAB_RUN_CONCURRENCY": "many"}
        assert run_guard.lab_run_limit(bad) == 30
        assert run_guard.lab_run_concurrency(bad) == 8


class ReserveTests(unittest.TestCase):
    def setUp(self):
        run_guard.reset()

    def request(self, host="203.0.113.10"):
        scope = {"type": "http", "method": "POST", "path": "/api/run", "headers": [],
                 "client": (host, 12345), "query_string": b""}
        return main.Request(scope)

    def test_window_limit_blocks_after_env_cap(self):
        env = {"BASIRA_LAB_RUN_LIMIT": "2", "BASIRA_LAB_RUN_CONCURRENCY": "0"}
        with patch.dict(os.environ, env, clear=False):
            run_guard.reserve_run(self.request())
            run_guard.release_run()
            run_guard.reserve_run(self.request())
            run_guard.release_run()
            with self.assertRaises(HTTPException) as caught:
                run_guard.reserve_run(self.request())
        assert caught.exception.status_code == 429
        assert caught.exception.headers["Retry-After"] == str(run_guard.WINDOW_SECONDS)

    def test_limit_is_per_peer(self):
        env = {"BASIRA_LAB_RUN_LIMIT": "1", "BASIRA_LAB_RUN_CONCURRENCY": "0"}
        with patch.dict(os.environ, env, clear=False):
            run_guard.reserve_run(self.request("203.0.113.10"))
            run_guard.release_run()
            run_guard.reserve_run(self.request("203.0.113.11"))
            run_guard.release_run()
            with self.assertRaises(HTTPException):
                run_guard.reserve_run(self.request("203.0.113.10"))

    def test_concurrency_cap_blocks_until_release(self):
        env = {"BASIRA_LAB_RUN_LIMIT": "0", "BASIRA_LAB_RUN_CONCURRENCY": "1"}
        with patch.dict(os.environ, env, clear=False):
            run_guard.reserve_run(self.request())
            with self.assertRaises(HTTPException) as caught:
                run_guard.reserve_run(self.request("198.51.100.9"))
            assert caught.exception.status_code == 429
            run_guard.release_run()
            run_guard.reserve_run(self.request("198.51.100.9"))
            run_guard.release_run()


class EndpointTests(unittest.TestCase):
    def setUp(self):
        run_guard.reset()
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {
            "BASIRA_DB_PATH": str(Path(tmp) / "test.sqlite3"),
            "BASIRA_LAB_RUN_LIMIT": "1",
            "BASIRA_LAB_RUN_CONCURRENCY": "0",
        }))
        self.client = self.enterContext(TestClient(main.app))

    def test_run_endpoint_returns_429_with_retry_after_after_limit(self):
        payload = {"source": "<p>demo</p>"}
        first = self.client.post("/api/run", json=payload)
        assert first.status_code == 200, first.text
        second = self.client.post("/api/run", json=payload)
        assert second.status_code == 429
        assert second.headers["retry-after"] == str(run_guard.WINDOW_SECONDS)
        assert second.headers["cache-control"] == "no-store"


if __name__ == "__main__":
    unittest.main()
