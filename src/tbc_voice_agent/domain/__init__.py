"""Shared domain types for the voice agent POC."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class ConversationState(StrEnum):
    CREATED = "created"
    VERIFYING_IDENTITY = "verifying_identity"
    VERIFIED = "verified"
    REMINDER = "reminder"
    DISCUSSING_OPTIONS = "discussing_options"
    CONFIRMING_PTP = "confirming_ptp"
    REQUESTING_PAYMENT_LINK = "requesting_payment_link"
    ESCALATING = "escalating"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class Intent(StrEnum):
    GREETING = "greeting"
    IDENTITY_ANSWER = "identity_answer"
    WRONG_PARTY = "wrong_party"
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    PROMISE_TO_PAY = "promise_to_pay"
    CORRECT_PTP = "correct_ptp"
    ACCEPT_PLAN = "accept_plan"
    REQUEST_PAYMENT_LINK = "request_payment_link"
    ALREADY_PAID = "already_paid"
    DISPUTE = "dispute"
    HARDSHIP = "hardship"
    STOP_CONTACT = "stop_contact"
    REQUEST_DISCOUNT = "request_discount"
    END_CALL = "end_call"
    PROMPT_INJECTION = "prompt_injection"
    LOW_CONFIDENCE = "low_confidence"
    UNKNOWN = "unknown"
    REMINDER_ACK = "reminder_ack"


class Disposition(StrEnum):
    VERIFIED_REMINDER = "VERIFIED_REMINDER"
    ID_FAILED = "ID_FAILED"
    WRONG_PARTY = "WRONG_PARTY"
    NO_ANSWER = "NO_ANSWER"
    ALREADY_PAID_CLAIMED = "ALREADY_PAID_CLAIMED"
    PTP_CAPTURED = "PTP_CAPTURED"
    PLAN_ACCEPTED = "PLAN_ACCEPTED"
    PAYMENT_LINK_REQUESTED = "PAYMENT_LINK_REQUESTED"
    DISPUTE_ESCALATED = "DISPUTE_ESCALATED"
    VULNERABILITY_ESCALATED = "VULNERABILITY_ESCALATED"
    STOP_CONTACT = "STOP_CONTACT"
    LEGAL_ESCALATION = "LEGAL_ESCALATION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HUMAN_TRANSFERRED = "HUMAN_TRANSFERRED"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    CUSTOMER_ENDED = "CUSTOMER_ENDED"


class Money(BaseModel):
    amount: str
    currency: str = "GEL"

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        try:
            parsed = Decimal(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("amount must be a decimal string") from exc
        if parsed <= 0:
            raise ValueError("amount must be positive")
        return f"{parsed.quantize(Decimal('0.01'))}"

    def as_decimal(self) -> Decimal:
        return Decimal(self.amount)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    session_id: str
    correlation_id: str
    sequence: int
    type: str
    occurred_at: datetime = Field(default_factory=utc_now)
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    redaction: dict[str, Any] = Field(
        default_factory=lambda: {"contains_pii": False, "fields_removed": []}
    )


class ApiErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    safe_action: str | None = None


class ApiError(BaseModel):
    error: ApiErrorBody
    correlation_id: str


class IdentityStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    LOCKED = "locked"


class IdentityState(BaseModel):
    status: IdentityStatus = IdentityStatus.UNVERIFIED
    evidence_ref: str | None = None
    verification_token: str | None = None
    attempts: int = 0
    step: int = 0  # 0=confirm name, 1=dob, 2=last4


class PolicyRequest(BaseModel):
    session_id: str
    policy_version: str
    state: ConversationState
    identity: IdentityState
    intent: Intent
    slots: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] | None = None
    dependency_health: dict[str, str] = Field(
        default_factory=lambda: {"crm": "available", "policy": "available"}
    )
    pending_ptp: dict[str, Any] | None = None


class PolicyDecision(BaseModel):
    allowed: bool
    action: str
    next_state: ConversationState
    reason_code: str
    permitted_facts: list[str] = Field(default_factory=list)
    permitted_offer_ids: list[str] = Field(default_factory=list)
    required_confirmation: bool = False
    template_key: str | None = None
    disposition: Disposition | None = None
    safe_close: bool = False


class LLMResult(BaseModel):
    intent: Intent
    slots: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    response_text: str = ""
    requested_action: str | None = None


class CreateSessionRequest(BaseModel):
    campaign_id: str = "campaign-en-001"
    customer_ref: str
    transport: str = "text"
    language: str = "en-US"


class CreateSessionResponse(BaseModel):
    session_id: str
    correlation_id: str
    state: ConversationState
    events_url: str


class TextTurnRequest(BaseModel):
    text: str
    client_turn_id: str | None = None


class TurnResponse(BaseModel):
    session_id: str
    state: ConversationState
    user_text: str
    assistant_text: str
    disposition: Disposition | None = None
    events: list[EventEnvelope] = Field(default_factory=list)


class SessionView(BaseModel):
    session_id: str
    correlation_id: str
    campaign_id: str
    customer_ref: str
    language: str
    transport: str
    state: ConversationState
    disposition: Disposition | None = None
    identity_status: IdentityStatus
    write_back_status: str | None = None
    created_at: datetime
    ended_at: datetime | None = None


class PreCallContext(BaseModel):
    customer_ref: str
    display_name: str
    preferred_language: str
    contact_allowed: bool
    campaign_id: str
    policy_version: str


class CollectionsContext(BaseModel):
    customer_ref: str
    account_ref: str
    balance: Money
    due_date: date
    days_past_due: int
    ptp_policy: dict[str, Any]
    offer_refs: list[str] = Field(default_factory=list)
    context_version: str


class Offer(BaseModel):
    offer_id: str
    display_text: str
    installments: int
    installment_amount: Money
    valid_until: date
    expired: bool = False


class OutcomeRecord(BaseModel):
    outcome_id: str
    customer_ref: str
    session_id: str
    disposition: Disposition
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    created_at: datetime = Field(default_factory=utc_now)
