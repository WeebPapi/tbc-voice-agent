"""Mock TBC FastAPI application."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from mock_tbc.store import MockStore

BEARER = os.getenv("MOCK_TBC_BEARER_TOKEN", "dev-mock-tbc-token")
DB_PATH = os.getenv("MOCK_DB_PATH", "data/mock_tbc.sqlite")

store = MockStore(db_path=DB_PATH)
app = FastAPI(title="Mock TBC API", version="0.1.0")


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not authorization or authorization != f"Bearer {BEARER}":
        raise HTTPException(status_code=401, detail="Unauthorized")


class IdentityRequest(BaseModel):
    session_id: str
    customer_ref: str
    answers: dict[str, str]
    correlation_id: str


class OutcomeRequest(BaseModel):
    session_id: str
    customer_ref: str
    disposition: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    idempotency_key: str


class PaymentLinkRequest(BaseModel):
    session_id: str
    customer_ref: str
    offer_or_payment_ref: str
    correlation_id: str
    idempotency_key: str


class TransferRequest(BaseModel):
    session_id: str
    customer_ref: str
    route: str
    reason: str
    priority: str
    verified: bool
    summary: dict[str, Any]
    correlation_id: str
    idempotency_key: str


class FailureRequest(BaseModel):
    mode: str
    scope: str = "global"
    session_id: str | None = None


class SuppressionRequest(BaseModel):
    session_id: str
    customer_ref: str
    correlation_id: str
    idempotency_key: str


def error_body(code: str, message: str, retryable: bool, correlation_id: str, safe_action: str | None = None):
    return JSONResponse(
        status_code=503 if retryable else 400,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "safe_action": safe_action,
            },
            "correlation_id": correlation_id,
        },
    )


async def maybe_fail(session_id: str | None, operation: str, correlation_id: str):
    mode = store.active_failure(session_id)
    if not mode:
        return None
    if mode == "high_latency":
        await asyncio.sleep(1.5)
        return None
    if mode == "identity_timeout" and operation == "identity":
        await asyncio.sleep(0.05)
        return error_body(
            "MOCK_IDENTITY_TIMEOUT",
            "Identity service timed out.",
            True,
            correlation_id,
            "close_without_disclosure",
        )
    if mode in {"context_timeout", "context_500"} and operation == "context":
        code = "MOCK_CRM_UNAVAILABLE" if mode == "context_500" else "MOCK_CONTEXT_TIMEOUT"
        return error_body(
            code,
            "Customer context is temporarily unavailable.",
            True,
            correlation_id,
            "close_without_disclosure",
        )
    if mode == "offers_timeout" and operation == "offers":
        return error_body(
            "MOCK_OFFERS_TIMEOUT",
            "Eligible offers are temporarily unavailable.",
            True,
            correlation_id,
            "close_without_disclosure",
        )
    if mode == "outcome_fail_once" and operation == "outcome":
        key = session_id or "global"
        if key not in store.outcome_fail_once_used:
            store.outcome_fail_once_used.add(key)
            return error_body(
                "MOCK_OUTCOME_TRANSIENT",
                "Outcome write failed transiently.",
                True,
                correlation_id,
                None,
            )
    if mode == "outcome_permanent_failure" and operation == "outcome":
        return error_body(
            "MOCK_OUTCOME_PERMANENT",
            "Outcome write permanently failed.",
            False,
            correlation_id,
            "show_exception",
        )
    if mode == "payment_link_rejected" and operation == "payment_link":
        return error_body(
            "MOCK_PAYMENT_LINK_REJECTED",
            "Payment link request rejected.",
            False,
            correlation_id,
            "offer_transfer",
        )
    if mode == "transfer_queue_unavailable" and operation == "transfer":
        return error_body(
            "MOCK_TRANSFER_UNAVAILABLE",
            "Human queue unavailable.",
            True,
            correlation_id,
            "callback_created",
        )
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock_tbc"}


@app.get("/v1/campaigns", dependencies=[Depends(require_auth)])
def list_campaigns() -> dict[str, Any]:
    return {"campaigns": [store.campaign]}


@app.get("/v1/customers/{customer_ref}/pre_call", dependencies=[Depends(require_auth)])
def pre_call(customer_ref: str, correlation_id: str = "cor_unknown") -> dict[str, Any]:
    customer = store.customers.get(customer_ref)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {
        "customer_ref": customer["customer_ref"],
        "display_name": customer["display_name"],
        "preferred_language": customer["preferred_language"],
        "contact_allowed": customer["contact_allowed"],
        "campaign_id": customer["campaign_id"],
        "policy_version": customer["policy_version"],
    }


@app.post("/v1/identity/verifications", dependencies=[Depends(require_auth)])
async def verify_identity(body: IdentityRequest) -> Any:
    failed = await maybe_fail(body.session_id, "identity", body.correlation_id)
    if failed:
        return failed
    customer = store.customers.get(body.customer_ref)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    expected = customer["identity"]
    answers = {k: str(v).strip().lower() for k, v in body.answers.items()}
    if answers.get("wrong_party") in {"true", "yes", "1"}:
        return {
            "status": "failed",
            "reason": "wrong_party",
            "evidence_ref": None,
            "verification_token": None,
            "expires_at": None,
        }
    ok = (
        answers.get("birth_day_month", "").replace("/", "-") == expected["birth_day_month"]
        and answers.get("id_last4", "") == expected["id_last4"].lower()
        and answers.get("name_confirmed", "true") in {"true", "yes", "1"}
    )
    if not ok:
        return {
            "status": "failed",
            "reason": "mismatch",
            "evidence_ref": None,
            "verification_token": None,
            "expires_at": None,
        }
    token = store.create_token(body.session_id, body.customer_ref)
    return {
        "status": "verified",
        "evidence_ref": token.evidence_ref,
        "verification_token": token.token,
        "expires_at": token.expires_at.isoformat(),
    }


def _auth_token(
    x_verification_token: str | None,
    x_session_id: str | None,
    customer_ref: str,
) -> None:
    if not x_session_id:
        raise HTTPException(status_code=400, detail="X-Session-Id required")
    try:
        store.validate_token(x_verification_token, x_session_id, customer_ref)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/v1/customers/{customer_ref}/collections-context", dependencies=[Depends(require_auth)])
async def collections_context(
    customer_ref: str,
    correlation_id: str = "cor_unknown",
    x_verification_token: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None),
) -> Any:
    failed = await maybe_fail(x_session_id, "context", correlation_id)
    if failed:
        return failed
    customer = store.customers.get(customer_ref)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.get("force_context_failure"):
        return error_body(
            "MOCK_CRM_UNAVAILABLE",
            "Customer context is temporarily unavailable.",
            True,
            correlation_id,
            "close_without_disclosure",
        )
    _auth_token(x_verification_token, x_session_id, customer_ref)
    return {
        "customer_ref": customer["customer_ref"],
        "account_ref": customer["account_ref"],
        "balance": customer["balance"],
        "due_date": customer["due_date"],
        "days_past_due": customer["days_past_due"],
        "ptp_policy": customer["ptp_policy"],
        "offer_refs": customer["offer_refs"],
        "context_version": customer["context_version"],
    }


@app.get("/v1/customers/{customer_ref}/eligible-offers", dependencies=[Depends(require_auth)])
async def eligible_offers(
    customer_ref: str,
    correlation_id: str = "cor_unknown",
    x_verification_token: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None),
) -> Any:
    failed = await maybe_fail(x_session_id, "offers", correlation_id)
    if failed:
        return failed
    customer = store.customers.get(customer_ref)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    _auth_token(x_verification_token, x_session_id, customer_ref)
    offers = []
    for offer_id in customer["offer_refs"]:
        offer = store.offers.get(offer_id)
        if offer:
            offers.append(offer)
    return {"offers": offers}


@app.post("/v1/outcomes", dependencies=[Depends(require_auth)])
async def write_outcome(body: OutcomeRequest) -> Any:
    failed = await maybe_fail(body.session_id, "outcome", body.correlation_id)
    if failed:
        return failed
    payload = {
        "customer_ref": body.customer_ref,
        "session_id": body.session_id,
        "disposition": body.disposition,
        "payload": body.payload,
        "idempotency_key": body.idempotency_key,
        "correlation_id": body.correlation_id,
    }
    try:
        record, created = store.store_outcome(body.idempotency_key, payload)
    except ValueError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "Idempotency key reused with different payload.",
                    "retryable": False,
                },
                "correlation_id": body.correlation_id,
            },
        )
    return {"outcome": record, "created": created}


@app.post("/v1/payment-link-requests", dependencies=[Depends(require_auth)])
async def payment_link(body: PaymentLinkRequest) -> Any:
    failed = await maybe_fail(body.session_id, "payment_link", body.correlation_id)
    if failed:
        return failed
    record = {
        "request_id": f"plink_{body.idempotency_key[-8:]}",
        "customer_ref": body.customer_ref,
        "session_id": body.session_id,
        "offer_or_payment_ref": body.offer_or_payment_ref,
        "status": "queued",
        "display_url": f"https://payments.invalid/demo/{body.customer_ref}",
        "created_at": datetime.now(UTC).isoformat(),
    }
    store.payment_links.append(record)
    return record


@app.post("/v1/transfers", dependencies=[Depends(require_auth)])
async def transfer(body: TransferRequest) -> Any:
    failed = await maybe_fail(body.session_id, "transfer", body.correlation_id)
    if failed:
        # Convert unavailable into callback_created for demo visibility when configured
        mode = store.active_failure(body.session_id)
        if mode == "transfer_queue_unavailable":
            record = {
                "transfer_id": f"tr_{body.idempotency_key[-8:]}",
                "status": "callback_created",
                "route": body.route,
                "reason": body.reason,
                "priority": body.priority,
                "verified": body.verified,
                "summary": body.summary,
            }
            store.transfers.append(record)
            return record
        return failed
    record = {
        "transfer_id": f"tr_{body.idempotency_key[-8:]}",
        "status": "accepted",
        "route": body.route,
        "reason": body.reason,
        "priority": body.priority,
        "verified": body.verified,
        "summary": body.summary,
    }
    store.transfers.append(record)
    return record


@app.post("/v1/suppressions", dependencies=[Depends(require_auth)])
def suppress(body: SuppressionRequest) -> dict[str, Any]:
    record = {
        "suppression_id": f"sup_{body.idempotency_key[-8:]}",
        "customer_ref": body.customer_ref,
        "session_id": body.session_id,
        "status": "recorded",
    }
    store.suppressions.append(record)
    return record


@app.get("/v1/admin/outcomes", dependencies=[Depends(require_auth)])
def list_outcomes() -> dict[str, Any]:
    return {"outcomes": list(store.outcomes.values())}


@app.get("/v1/admin/transfers", dependencies=[Depends(require_auth)])
def list_transfers() -> dict[str, Any]:
    return {"transfers": store.transfers}


@app.get("/v1/admin/failures", dependencies=[Depends(require_auth)])
def list_failures() -> dict[str, Any]:
    return {"failures": store.failures}


@app.post("/v1/admin/failures", dependencies=[Depends(require_auth)])
def inject_failure(body: FailureRequest) -> dict[str, str]:
    store.set_failure(body.mode, body.scope, body.session_id)
    return {"status": "ok", "mode": body.mode}


@app.delete("/v1/admin/failures", dependencies=[Depends(require_auth)])
def clear_failures() -> dict[str, str]:
    store.clear_failures()
    return {"status": "cleared"}


@app.post("/v1/admin/reset", dependencies=[Depends(require_auth)])
def reset() -> dict[str, str]:
    # Local-only safeguard: refuse if bound publicly (checked by caller env)
    bind_host = os.getenv("BIND_HOST", "127.0.0.1")
    if bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="Reset only allowed on localhost")
    store.reset()
    return {"status": "reset"}


@app.middleware("http")
async def bind_hint(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Mock-TBC"] = "synthetic"
    return response
