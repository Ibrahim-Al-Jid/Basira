import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .observability import install_observability


def client():
    app = FastAPI()
    install_observability(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_a_clean_request_id_is_kept_and_echoed():
    response = client().get("/ping", headers={"x-request-id": "trace-123.abc_9"})
    assert response.headers["x-request-id"] == "trace-123.abc_9"


def test_a_request_id_that_could_forge_log_fields_is_replaced(caplog):
    forged = "x status=200 path=/admin duration_ms=0.1 " + "a" * 500
    with caplog.at_level(logging.INFO, logger="basira.access"):
        response = client().get("/ping", headers={"x-request-id": forged})
    echoed = response.headers["x-request-id"]
    assert echoed != forged and len(echoed) == 32 and echoed.isalnum()
    assert "path=/admin" not in caplog.text
    assert echoed in caplog.text
