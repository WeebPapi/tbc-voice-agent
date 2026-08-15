"""Deterministic policy engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tbc_voice_agent.domain import (
    ConversationState,
    Disposition,
    IdentityStatus,
    Intent,
    PolicyDecision,
    PolicyRequest,
)


class PolicyEngine:
    def __init__(self, as_of: date | None = None) -> None:
        self.as_of = as_of or date.today()

    def decide(self, request: PolicyRequest) -> PolicyDecision:
        if request.dependency_health.get("crm") != "available":
            return PolicyDecision(
                allowed=False,
                action="technical_failure_close",
                next_state=ConversationState.TERMINATED,
                reason_code="CRM_UNAVAILABLE",
                template_key="technical_failure_close",
                disposition=Disposition.TECHNICAL_FAILURE,
                safe_close=True,
            )

        if request.intent == Intent.PROMPT_INJECTION and request.state in {
            ConversationState.CREATED,
            ConversationState.VERIFYING_IDENTITY,
        }:
            return PolicyDecision(
                allowed=False,
                action="continue_identity",
                next_state=ConversationState.VERIFYING_IDENTITY,
                reason_code="PROMPT_INJECTION_IGNORED",
                template_key="prompt_injection_ignore",
            )

        if request.intent == Intent.WRONG_PARTY:
            return PolicyDecision(
                allowed=True,
                action="wrong_party_close",
                next_state=ConversationState.TERMINATED,
                reason_code="WRONG_PARTY",
                template_key="wrong_party_close",
                disposition=Disposition.WRONG_PARTY,
            )

        if request.state in {ConversationState.CREATED, ConversationState.VERIFYING_IDENTITY}:
            return self._identity_flow(request)

        if request.identity.status != IdentityStatus.VERIFIED:
            return PolicyDecision(
                allowed=False,
                action="identity_failed_close",
                next_state=ConversationState.TERMINATED,
                reason_code="IDENTITY_REQUIRED",
                template_key="identity_failed_close",
                disposition=Disposition.ID_FAILED,
                safe_close=True,
            )

        # Post-verification paths
        if request.intent == Intent.HARDSHIP:
            return PolicyDecision(
                allowed=True,
                action="hardship_transfer",
                next_state=ConversationState.ESCALATING,
                reason_code="HARDSHIP_ESCALATE",
                template_key="hardship_transfer",
                disposition=Disposition.VULNERABILITY_ESCALATED,
            )
        if request.intent == Intent.DISPUTE:
            return PolicyDecision(
                allowed=True,
                action="dispute_transfer",
                next_state=ConversationState.ESCALATING,
                reason_code="DISPUTE_ESCALATE",
                template_key="dispute_transfer",
                disposition=Disposition.DISPUTE_ESCALATED,
            )
        if request.intent == Intent.STOP_CONTACT:
            return PolicyDecision(
                allowed=True,
                action="stop_contact",
                next_state=ConversationState.TERMINATED,
                reason_code="STOP_CONTACT",
                template_key="stop_contact_close",
                disposition=Disposition.STOP_CONTACT,
            )
        if request.intent == Intent.ALREADY_PAID:
            return PolicyDecision(
                allowed=True,
                action="record_already_paid_claim",
                next_state=ConversationState.COMPLETED,
                reason_code="ALREADY_PAID_CLAIM",
                template_key="already_paid_ack",
                disposition=Disposition.ALREADY_PAID_CLAIMED,
                permitted_facts=[],
            )
        if request.intent == Intent.REQUEST_DISCOUNT:
            return PolicyDecision(
                allowed=False,
                action="unsupported_discount",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="UNSUPPORTED_DISCOUNT",
                template_key="unsupported_discount",
                permitted_offer_ids=list((request.context or {}).get("eligible_offer_ids", [])),
            )
        if request.intent == Intent.REQUEST_PAYMENT_LINK:
            return PolicyDecision(
                allowed=True,
                action="request_payment_link",
                next_state=ConversationState.REQUESTING_PAYMENT_LINK,
                reason_code="PAYMENT_LINK_ALLOWED",
                template_key="payment_link_acknowledged",
                disposition=Disposition.PAYMENT_LINK_REQUESTED,
            )
        if request.intent == Intent.ACCEPT_PLAN:
            return self._plan_decision(request, confirmed=request.slots.get("confirmation") == "yes")

        if request.intent == Intent.CONFIRM_YES and request.state == ConversationState.DISCUSSING_OPTIONS:
            pending_offer = (request.context or {}).get("pending_offer_id")
            offer_ids = list((request.context or {}).get("eligible_offer_ids", []))
            if pending_offer and pending_offer in offer_ids:
                return PolicyDecision(
                    allowed=True,
                    action="accept_plan",
                    next_state=ConversationState.COMPLETED,
                    reason_code="PLAN_ACCEPTED",
                    permitted_offer_ids=[pending_offer],
                    template_key="payment_plan_accepted",
                    disposition=Disposition.PLAN_ACCEPTED,
                )
            return PolicyDecision(
                allowed=True,
                action="await_customer",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="AWAITING_OPTION",
                template_key="discuss_options_prompt",
                permitted_facts=["balance", "due_date"],
            )

        if request.intent == Intent.CONFIRM_NO and request.state == ConversationState.DISCUSSING_OPTIONS:
            return PolicyDecision(
                allowed=True,
                action="decline_plan",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PLAN_DECLINED",
                template_key="discuss_options_prompt",
            )

        if request.intent == Intent.PROMISE_TO_PAY:
            return self._ptp_decision(request)

        if request.state == ConversationState.CONFIRMING_PTP:
            if request.intent == Intent.CONFIRM_YES:
                return PolicyDecision(
                    allowed=True,
                    action="capture_ptp",
                    next_state=ConversationState.COMPLETED,
                    reason_code="PTP_CONFIRMED",
                    permitted_facts=["requested_amount", "requested_date"],
                    required_confirmation=False,
                    template_key="ptp_captured",
                    disposition=Disposition.PTP_CAPTURED,
                )
            if request.intent in {Intent.CONFIRM_NO, Intent.CORRECT_PTP}:
                return PolicyDecision(
                    allowed=True,
                    action="revise_ptp",
                    next_state=ConversationState.DISCUSSING_OPTIONS,
                    reason_code="PTP_CORRECTED",
                    template_key=None,
                )
            if request.intent == Intent.UNKNOWN or request.slots.get("confirmation") == "ambiguous":
                return PolicyDecision(
                    allowed=False,
                    action="clarify_ptp",
                    next_state=ConversationState.CONFIRMING_PTP,
                    reason_code="PTP_AMBIGUOUS_CONFIRMATION",
                    template_key="ptp_ambiguous",
                    required_confirmation=True,
                )

        if request.intent == Intent.LOW_CONFIDENCE:
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=request.state,
                reason_code="LOW_CONFIDENCE",
                template_key="low_confidence_clarify",
            )

        if request.intent == Intent.END_CALL:
            return PolicyDecision(
                allowed=True,
                action="customer_ended",
                next_state=ConversationState.TERMINATED,
                reason_code="CUSTOMER_ENDED",
                template_key="customer_ended",
                disposition=Disposition.CUSTOMER_ENDED,
                safe_close=True,
            )

        if request.state == ConversationState.VERIFIED:
            return PolicyDecision(
                allowed=True,
                action="deliver_reminder",
                next_state=ConversationState.REMINDER,
                reason_code="REMINDER_ALLOWED",
                permitted_facts=["balance", "due_date", "currency"],
                template_key="reminder_verified",
            )

        if request.state == ConversationState.REMINDER:
            return PolicyDecision(
                allowed=True,
                action="discuss_options",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="ENTER_DISCUSSION",
                permitted_facts=["balance", "due_date"],
                permitted_offer_ids=list((request.context or {}).get("eligible_offer_ids", [])),
            )

        if request.state == ConversationState.DISCUSSING_OPTIONS and request.intent in {
            Intent.REMINDER_ACK,
            Intent.UNKNOWN,
            Intent.GREETING,
        }:
            return PolicyDecision(
                allowed=True,
                action="await_customer",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="AWAITING_OPTION",
                permitted_facts=["balance", "due_date"],
                template_key="discuss_options_prompt",
            )

        return PolicyDecision(
            allowed=False,
            action="await_customer",
            next_state=request.state,
            reason_code="NO_MATCHING_RULE",
            template_key="discuss_options_prompt",
        )

    def _plan_decision(self, request: PolicyRequest, *, confirmed: bool) -> PolicyDecision:
        offer_ids = list((request.context or {}).get("eligible_offer_ids", []))
        requested = request.slots.get("offer_id") or (request.context or {}).get("pending_offer_id")
        if requested and requested in offer_ids and confirmed:
            return PolicyDecision(
                allowed=True,
                action="accept_plan",
                next_state=ConversationState.COMPLETED,
                reason_code="PLAN_ACCEPTED",
                permitted_offer_ids=[requested],
                template_key="payment_plan_accepted",
                disposition=Disposition.PLAN_ACCEPTED,
            )
        if offer_ids:
            chosen = requested if requested in offer_ids else offer_ids[0]
            return PolicyDecision(
                allowed=True,
                action="present_plan",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PRESENT_ELIGIBLE_OFFER",
                permitted_offer_ids=[chosen],
                template_key="payment_plan_offer",
            )
        return PolicyDecision(
            allowed=False,
            action="unsupported_discount",
            next_state=ConversationState.DISCUSSING_OPTIONS,
            reason_code="NO_ELIGIBLE_OFFER",
            template_key="unsupported_discount",
        )

    def _identity_flow(self, request: PolicyRequest) -> PolicyDecision:
        if request.identity.attempts >= 2 and request.intent == Intent.IDENTITY_ANSWER:
            return PolicyDecision(
                allowed=False,
                action="identity_failed_close",
                next_state=ConversationState.TERMINATED,
                reason_code="IDENTITY_ATTEMPTS_EXHAUSTED",
                template_key="identity_failed_close",
                disposition=Disposition.ID_FAILED,
            )
        if request.identity.status == IdentityStatus.VERIFIED:
            return PolicyDecision(
                allowed=True,
                action="load_context",
                next_state=ConversationState.VERIFIED,
                reason_code="IDENTITY_VERIFIED",
            )
        return PolicyDecision(
            allowed=True,
            action="continue_identity",
            next_state=ConversationState.VERIFYING_IDENTITY,
            reason_code="IDENTITY_IN_PROGRESS",
            template_key=None,
        )

    def _ptp_decision(self, request: PolicyRequest) -> PolicyDecision:
        context = request.context or {}
        amount = request.slots.get("amount")
        pay_date = request.slots.get("date")
        currency = request.slots.get("currency", "GEL")
        policy = context.get("ptp_policy") or {}
        minimum = Decimal(str(policy.get("minimum_amount", "0.01")))
        max_date = date.fromisoformat(str(policy.get("maximum_date", "2099-12-31")))
        today = self.as_of

        # Reject an unusable date before asking for a missing amount.
        if pay_date and not amount:
            try:
                d = date.fromisoformat(str(pay_date))
            except Exception:  # noqa: BLE001
                return PolicyDecision(
                    allowed=False,
                    action="clarify",
                    next_state=ConversationState.DISCUSSING_OPTIONS,
                    reason_code="PTP_PARSE_ERROR",
                    template_key="ptp_need_date",
                )
            if d < today or d > max_date:
                return PolicyDecision(
                    allowed=False,
                    action="clarify",
                    next_state=ConversationState.DISCUSSING_OPTIONS,
                    reason_code="PTP_OUT_OF_RANGE",
                    template_key="ptp_out_of_range",
                )
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_INCOMPLETE",
                template_key="ptp_need_amount",
            )

        if amount and not pay_date:
            try:
                amt = Decimal(str(amount))
            except Exception:  # noqa: BLE001
                return PolicyDecision(
                    allowed=False,
                    action="clarify",
                    next_state=ConversationState.DISCUSSING_OPTIONS,
                    reason_code="PTP_PARSE_ERROR",
                    template_key="ptp_need_amount",
                )
            if amt < minimum:
                return PolicyDecision(
                    allowed=False,
                    action="clarify",
                    next_state=ConversationState.DISCUSSING_OPTIONS,
                    reason_code="PTP_OUT_OF_RANGE",
                    template_key="ptp_out_of_range",
                )
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_INCOMPLETE",
                template_key="ptp_need_date",
            )

        if not amount or not pay_date:
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_INCOMPLETE",
                template_key="low_confidence_clarify",
            )
        if currency != "GEL":
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_BAD_CURRENCY",
                template_key="ptp_out_of_range",
            )
        try:
            amt = Decimal(str(amount))
            d = date.fromisoformat(str(pay_date))
        except Exception:  # noqa: BLE001
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_PARSE_ERROR",
                template_key="low_confidence_clarify",
            )
        if amt < minimum or d < today or d > max_date:
            return PolicyDecision(
                allowed=False,
                action="clarify",
                next_state=ConversationState.DISCUSSING_OPTIONS,
                reason_code="PTP_OUT_OF_RANGE",
                template_key="ptp_out_of_range",
            )
        return PolicyDecision(
            allowed=True,
            action="request_ptp_confirmation",
            next_state=ConversationState.CONFIRMING_PTP,
            reason_code="PTP_WITHIN_ALLOWED_RANGE",
            permitted_facts=["requested_amount", "requested_date"],
            required_confirmation=True,
            template_key="ptp_readback",
        )
