"""Shared pytest fixtures for the backend suite."""
import pytest

from . import run_guard


@pytest.fixture(autouse=True)
def reset_lab_run_guard():
    # The lab run guard keeps process-global counters; isolate every test from them.
    run_guard.reset()
    yield
    run_guard.reset()
