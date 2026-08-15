"""Policy engine unit tests."""

from datetime import date

from tbc_voice_agent.domain import (
    ConversationState,
    Disposition,
    IdentityState,
    IdentityStatus,
    Intent,
    PolicyRequest,
)
from tbc_voice_agent.policy import PolicyEngine


def _verified(**kwargs):
    return PolicyRequest(
        session_id="s1",
        policy_version="poc-v1",
        identity=IdentityState(status=IdentityStatus.VERIFIED),
        **kwargs,
    )


def test_wrong_party_closes():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        PolicyRequest(
            session_id="s1",
            policy_version="poc-v1",
            state=ConversationState.VERIFYING_IDENTITY,
            identity=IdentityState(),
            intent=Intent.WRONG_PARTY,
        )
    )
    assert d.disposition == Disposition.WRONG_PARTY
    assert d.next_state == ConversationState.TERMINATED


def test_ptp_requires_valid_range():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.PROMISE_TO_PAY,
            slots={"amount": "275.40", "currency": "GEL", "date": "2026-08-28"},
            context={
                "ptp_policy": {"minimum_amount": "25.00", "maximum_date": "2026-09-13"},
                "eligible_offer_ids": [],
            },
        )
    )
    assert d.allowed is True
    assert d.next_state == ConversationState.CONFIRMING_PTP


def test_ptp_past_date_out_of_range_even_without_amount():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.PROMISE_TO_PAY,
            slots={"currency": "GEL", "date": "2026-08-13"},
            context={
                "ptp_policy": {"minimum_amount": "25.00", "maximum_date": "2026-09-13"},
                "eligible_offer_ids": ["offer-001"],
            },
        )
    )
    assert d.allowed is False
    assert d.reason_code == "PTP_OUT_OF_RANGE"
    assert d.template_key == "ptp_out_of_range"
    assert d.template_key != "unsupported_discount"


def test_ptp_valid_date_needs_amount():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.PROMISE_TO_PAY,
            slots={"currency": "GEL", "date": "2026-08-28"},
            context={
                "ptp_policy": {"minimum_amount": "25.00", "maximum_date": "2026-09-13"},
            },
        )
    )
    assert d.allowed is False
    assert d.reason_code == "PTP_INCOMPLETE"
    assert d.template_key == "ptp_need_amount"


def test_ptp_amount_needs_date():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.PROMISE_TO_PAY,
            slots={"amount": "275.40", "currency": "GEL"},
            context={
                "ptp_policy": {"minimum_amount": "25.00", "maximum_date": "2026-09-13"},
            },
        )
    )
    assert d.allowed is False
    assert d.reason_code == "PTP_INCOMPLETE"
    assert d.template_key == "ptp_need_date"


def test_crm_unavailable_fail_closed():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.PROMISE_TO_PAY,
            dependency_health={"crm": "unavailable", "policy": "available"},
        )
    )
    assert d.disposition == Disposition.TECHNICAL_FAILURE
    assert d.safe_close is True


def test_hardship_escalates():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.HARDSHIP,
        )
    )
    assert d.disposition == Disposition.VULNERABILITY_ESCALATED


def test_hardship_overrides_ptp_confirmation_state():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.CONFIRMING_PTP,
            intent=Intent.HARDSHIP,
        )
    )
    assert d.action == "hardship_transfer"
    assert d.disposition == Disposition.VULNERABILITY_ESCALATED


def test_unknown_does_not_present_plan():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.UNKNOWN,
            context={"eligible_offer_ids": ["offer-001"]},
        )
    )
    assert d.action == "await_customer"
    assert d.template_key == "discuss_options_prompt"


def test_yes_accepts_pending_plan():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.CONFIRM_YES,
            context={
                "eligible_offer_ids": ["offer-002"],
                "pending_offer_id": "offer-002",
            },
        )
    )
    assert d.action == "accept_plan"
    assert d.disposition == Disposition.PLAN_ACCEPTED


def test_accept_plan_without_confirmation_presents():
    engine = PolicyEngine(as_of=date(2026, 8, 14))
    d = engine.decide(
        _verified(
            state=ConversationState.DISCUSSING_OPTIONS,
            intent=Intent.ACCEPT_PLAN,
            slots={"offer_id": "offer-002"},
            context={"eligible_offer_ids": ["offer-002"]},
        )
    )
    assert d.action == "present_plan"
