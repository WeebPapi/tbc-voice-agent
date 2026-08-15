"""Mock TBC contract tests."""

from tests.conftest import AUTH


def test_pre_call_has_no_protected_fields(mock_client):
    r = mock_client.get("/v1/customers/cust-001/pre_call", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    for forbidden in ("balance", "due_date", "offer", "days_past_due", "account_ref"):
        assert forbidden not in body


def test_protected_context_requires_token(mock_client):
    r = mock_client.get(
        "/v1/customers/cust-001/collections-context",
        headers={**AUTH, "X-Session-Id": "ses_1"},
    )
    assert r.status_code == 403


def test_token_bound_to_session_customer(mock_client):
    verify = mock_client.post(
        "/v1/identity/verifications",
        headers=AUTH,
        json={
            "session_id": "ses_a",
            "customer_ref": "cust-001",
            "answers": {
                "name_confirmed": "true",
                "birth_day_month": "03-15",
                "id_last4": "0001",
            },
            "correlation_id": "cor_1",
        },
    )
    token = verify.json()["verification_token"]
    bad = mock_client.get(
        "/v1/customers/cust-001/collections-context",
        headers={
            **AUTH,
            "X-Session-Id": "ses_other",
            "X-Verification-Token": token,
        },
    )
    assert bad.status_code == 403
    good = mock_client.get(
        "/v1/customers/cust-001/collections-context",
        headers={
            **AUTH,
            "X-Session-Id": "ses_a",
            "X-Verification-Token": token,
        },
    )
    assert good.status_code == 200
    assert good.json()["balance"]["amount"] == "275.40"


def test_outcome_idempotent(mock_client):
    payload = {
        "session_id": "ses_1",
        "customer_ref": "cust-001",
        "disposition": "PTP_CAPTURED",
        "payload": {"ptp": {"amount": "275.40"}},
        "correlation_id": "cor_1",
        "idempotency_key": "ptp:ses_1",
    }
    first = mock_client.post("/v1/outcomes", headers=AUTH, json=payload)
    second = mock_client.post("/v1/outcomes", headers=AUTH, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["outcome"]["outcome_id"] == second.json()["outcome"]["outcome_id"]
    conflict = mock_client.post(
        "/v1/outcomes",
        headers=AUTH,
        json={**payload, "payload": {"ptp": {"amount": "100.00"}}},
    )
    assert conflict.status_code == 409


def test_reset_clears_writes(mock_client):
    mock_client.post(
        "/v1/outcomes",
        headers=AUTH,
        json={
            "session_id": "ses_1",
            "customer_ref": "cust-001",
            "disposition": "STOP_CONTACT",
            "payload": {},
            "correlation_id": "cor_1",
            "idempotency_key": "k1",
        },
    )
    mock_client.post("/v1/admin/reset", headers=AUTH)
    outcomes = mock_client.get("/v1/admin/outcomes", headers=AUTH)
    assert outcomes.json()["outcomes"] == []
