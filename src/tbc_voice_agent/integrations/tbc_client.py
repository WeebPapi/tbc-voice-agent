"""Typed client for mock TBC."""

from __future__ import annotations

from typing import Any

import httpx


class TBCClient:
    def __init__(self, base_url: str, bearer_token: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout

    def _headers(
        self,
        correlation_id: str,
        verification_token: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "X-Correlation-Id": correlation_id,
        }
        if verification_token:
            headers["X-Verification-Token"] = verification_token
        if session_id:
            headers["X-Session-Id"] = session_id
        return headers

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    async def list_campaigns(self, correlation_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/campaigns",
                headers=self._headers(correlation_id),
            )
            r.raise_for_status()
            return r.json()

    async def pre_call(self, customer_ref: str, correlation_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/customers/{customer_ref}/pre_call",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id),
            )
            r.raise_for_status()
            return r.json()

    async def verify_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/identity/verifications",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            if r.status_code >= 400:
                return r.json()
            return r.json()

    async def collections_context(
        self,
        customer_ref: str,
        session_id: str,
        verification_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/customers/{customer_ref}/collections-context",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id, verification_token, session_id),
            )
            return r.json()

    async def eligible_offers(
        self,
        customer_ref: str,
        session_id: str,
        verification_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/customers/{customer_ref}/eligible-offers",
                params={"correlation_id": correlation_id},
                headers=self._headers(correlation_id, verification_token, session_id),
            )
            return r.json()

    async def write_outcome(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/outcomes",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json() if r.content else {"error": {"code": "EMPTY", "retryable": True}}

    async def payment_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/payment-link-requests",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/transfers",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def suppress(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/suppressions",
                json=payload,
                headers=self._headers(payload["correlation_id"]),
            )
            return r.json()

    async def admin_reset(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/reset",
                headers=self._headers("cor_reset"),
            )
            r.raise_for_status()
            return r.json()

    async def admin_failures(self, mode: str, session_id: str | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/v1/admin/failures",
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.request(
                "DELETE",
                f"{self.base_url}/v1/admin/failures",
                headers=self._headers("cor_fail"),
            )
            r.raise_for_status()
            return r.json()

    async def list_outcomes(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/outcomes",
                headers=self._headers("cor_admin"),
            )
            r.raise_for_status()
            return r.json()

    async def list_transfers(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/transfers",
                headers=self._headers("cor_admin"),
            )
            r.raise_for_status()
            return r.json()

    async def list_failures(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/admin/failures",
                headers=self._headers("cor_admin"),
            )
            r.raise_for_status()
            return r.json()
