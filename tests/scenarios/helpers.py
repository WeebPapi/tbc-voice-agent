"""Scenario test helpers using in-process ASGI transport for mock TBC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from mock_tbc.app import app as mock_app
from tbc_voice_agent.domain import CreateSessionRequest
from tbc_voice_agent.integrations.tbc_client import TBCClient
from tbc_voice_agent.orchestrator import Orchestrator


class ASGITBCClient(TBCClient):
    """TBC client that talks to the mock app in-process."""

    def __init__(self, bearer_token: str = "dev-mock-tbc-token") -> None:
        super().__init__("http://mock", bearer_token)
        self._transport = httpx.ASGITransport(app=mock_app)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, base_url="http://mock", timeout=5.0)

    async def health(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/health")
            r.raise_for_status()
            return r.json()

    async def list_campaigns(self, correlation_id: str) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/v1/campaigns", headers=self._headers(correlation_id))
            r.raise_for_status()
            return r.json()

    async def pre_call(self, customer_ref: str, correlation_id: str) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get(
                f"/v1/customers/{customer_ref}/pre_call",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id),
            )
            r.raise_for_status()
            return r.json()

    async def verify_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/identity/verifications",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def collections_context(
        self, customer_ref, session_id, verification_token, correlation_id
    ):
        async with self._client() as client:
            r = await client.get(
                f"/v1/customers/{customer_ref}/collections-context",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id, verification_token, session_id),
            )
            return r.json()

    async def eligible_offers(self, customer_ref, session_id, verification_token, correlation_id):
        async with self._client() as client:
            r = await client.get(
                f"/v1/customers/{customer_ref}/eligible-offers",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id, verification_token, session_id),
            )
            return r.json()

    async def write_outcome(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/outcomes",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def payment_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/payment-link-requests",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/transfers",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def suppress(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/suppressions",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def admin_failures(self, mode: str, session_id: str | None = None) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/v1/admin/failures",
                json={
                    "mode": mode,
                    "scope": "session" if session_id else "global",
                    "session_id": session_id,
                },
                headers=self._headers("cor_fail"),
            )
            r.raise_for_status()
            return r.json()

    async def clear_failures(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.request(
                "DELETE", "/v1/admin/failures", headers=self._headers("cor_fail")
            )
            r.raise_for_status()
            return r.json()

    async def list_failures(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/v1/admin/failures", headers=self._headers("cor_admin"))
            r.raise_for_status()
            return r.json()

    async def list_outcomes(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/v1/admin/outcomes", headers=self._headers("cor_admin"))
            r.raise_for_status()
            return r.json()

    async def list_transfers(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/v1/admin/transfers", headers=self._headers("cor_admin"))
            r.raise_for_status()
            return r.json()


PROTECTED_MARKERS = [
    "275.40",
    "overdue",
    "due on",
    "balance",
    "payment plan",
    "offer-001",
]


async def verify_customer(orch: Orchestrator, customer_ref: str, dob: str, last4: str):
    session = await orch.create_session(
        CreateSessionRequest(customer_ref=customer_ref, transport="text")
    )
    start = await orch.start_session(session.session_id)
    assert "balance" not in start.assistant_text.lower()
    await orch.handle_text_turn(session.session_id, "Yes, this is me")
    await orch.handle_text_turn(session.session_id, dob)
    result = await orch.handle_text_turn(session.session_id, last4)
    return session, result


def assert_no_forbidden(text: str) -> None:
    lowered = text.lower()
    for marker in ("275.40", "overdue balance", "due on"):
        assert marker not in lowered


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
