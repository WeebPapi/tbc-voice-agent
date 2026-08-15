"""Smoke tests for foundation health endpoints."""

from fastapi.testclient import TestClient

from mock_tbc.app import app as mock_app


def test_mock_health():
    client = TestClient(mock_app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_money_model():
    from tbc_voice_agent.domain import Money

    m = Money(amount="275.4", currency="GEL")
    assert m.amount == "275.40"
