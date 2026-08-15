"""Session orchestrator coordinating turns, policy, and integrations."""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from tbc_voice_agent.config import Settings
from tbc_voice_agent.content import SlotHints, get_language_pack
from tbc_voice_agent.domain import (
    ConversationState,
    CreateSessionRequest,
    Disposition,
    IdentityStatus,
    Intent,
    PolicyRequest,
    TurnResponse,
    new_id,
    utc_now,
)
from tbc_voice_agent.integrations.tbc_client import TBCClient
from tbc_voice_agent.orchestrator.store import EventStore, SessionRecord
from tbc_voice_agent.policy import PolicyEngine
from tbc_voice_agent.policy.safety import (
    detect_explicit_plan_accept,
    detect_payment_link_request,
    detect_plan_request,
    detect_prompt_injection,
    detect_safety_intent,
    detect_wrong_party,
)
from tbc_voice_agent.providers import (
    FakeLLM,
    FakeSTT,
    FakeTTS,
    LanguageModel,
    OpenAILLM,
    OpenAISTT,
    OpenAITTS,
    SpeechToText,
    TextToSpeech,
    validate_llm_response,
)


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        store: EventStore,
        tbc: TBCClient,
        llm: LanguageModel | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.tbc = tbc
        raw_as_of = (self.settings.policy_as_of_date or "").strip()
        self.as_of = date.fromisoformat(raw_as_of) if raw_as_of else date.today()
        self.policy = PolicyEngine(as_of=self.as_of)
        self.llm = llm or self._build_llm()
        self.stt = stt or self._build_stt()
        self.tts = tts or self._build_tts()
        self._locks: dict[str, asyncio.Lock] = {}

    def _build_llm(self) -> LanguageModel:
        if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
            return OpenAILLM(self.settings.openai_api_key, self.settings.openai_llm_model)
        return FakeLLM(self.settings.voice_language)

    def _build_stt(self) -> SpeechToText:
        if self.settings.stt_provider == "openai" and self.settings.openai_api_key:
            return OpenAISTT(self.settings.openai_api_key, self.settings.openai_stt_model)
        return FakeSTT()

    def _build_tts(self) -> TextToSpeech:
        if self.settings.tts_provider == "openai" and self.settings.openai_api_key:
            return OpenAITTS(
                self.settings.openai_api_key,
                self.settings.openai_tts_model,
                self.settings.openai_tts_voice,
            )
        return FakeTTS()

    def _lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def create_session(self, req: CreateSessionRequest) -> SessionRecord:
        session = SessionRecord(
            session_id=new_id("ses"),
            correlation_id=new_id("cor"),
            campaign_id=req.campaign_id,
            customer_ref=req.customer_ref,
            language=req.language,
            transport=req.transport,
        )
        pre = await self.tbc.pre_call(req.customer_ref, session.correlation_id)
        session.display_name = pre["display_name"]
        self.store.create(session)
        self.store.append_event(
            session,
            "session.created",
            "orchestrator",
            {
                "campaign_id": req.campaign_id,
                "customer_ref": req.customer_ref,
                "language": req.language,
                "transport": req.transport,
            },
        )
        return session

    async def start_session(self, session_id: str) -> TurnResponse:
        session = self._require(session_id)
        async with self._lock(session_id):
            session.state = ConversationState.VERIFYING_IDENTITY
            self.store.append_event(
                session,
                "session.started",
                "orchestrator",
                {
                    "policy_version": self.settings.policy_version,
                    "content_version": self.settings.content_version,
                },
            )
            self.store.append_event(
                session,
                "state.changed",
                "orchestrator",
                {
                    "previous": ConversationState.CREATED.value,
                    "next": session.state.value,
                    "trigger": "start",
                },
            )
            pack = get_language_pack(session.language)
            text = pack.render_template(
                "greeting_neutral", {"display_name": session.display_name}
            )
            self.store.append_event(
                session,
                "assistant.response_approved",
                "orchestrator",
                {"text": text, "template": "greeting_neutral"},
            )
            self.store.append_event(
                session,
                "identity.requested",
                "orchestrator",
                {"question_set_version": "idq-poc-v1", "attempt": 1},
            )
            return TurnResponse(
                session_id=session.session_id,
                state=session.state,
                user_text="",
                assistant_text=text,
                events=self.store.events_after(session_id, 0),
            )

    async def handle_text_turn(
        self,
        session_id: str,
        text: str,
        client_turn_id: str | None = None,
    ) -> TurnResponse:
        session = self._require(session_id)
        async with self._lock(session_id):
            if client_turn_id and client_turn_id in session.seen_turn_ids:
                return TurnResponse(
                    session_id=session.session_id,
                    state=session.state,
                    user_text=text,
                    assistant_text="",
                    disposition=session.disposition,
                    events=[],
                )
            if client_turn_id:
                session.seen_turn_ids.add(client_turn_id)

            if session.state in {ConversationState.COMPLETED, ConversationState.TERMINATED}:
                return TurnResponse(
                    session_id=session.session_id,
                    state=session.state,
                    user_text=text,
                    assistant_text="",
                    disposition=session.disposition,
                    events=[],
                )

            before = session.sequence
            if session.state == ConversationState.VERIFYING_IDENTITY:
                self.store.append_event(
                    session,
                    "transcript.final",
                    "transport",
                    {
                        "speaker": "customer",
                        "text": "[redacted identity answer]",
                        "confidence": 1.0,
                    },
                    redaction={"contains_pii": True, "fields_removed": ["text"]},
                )
            else:
                self.store.append_event(
                    session,
                    "transcript.final",
                    "transport",
                    {"speaker": "customer", "text": text, "confidence": 1.0},
                )

            assistant_text = await self._process_turn(session, text)
            return TurnResponse(
                session_id=session.session_id,
                state=session.state,
                user_text=text,
                assistant_text=assistant_text,
                disposition=session.disposition,
                events=self.store.events_after(session_id, before),
            )

    async def _process_turn(self, session: SessionRecord, text: str) -> str:
        pack = get_language_pack(session.language)
        if session.state == ConversationState.VERIFYING_IDENTITY:
            return await self._handle_identity_turn(session, text, pack)

        permitted_facts = self._permitted_fact_map(session)
        llm = await self.llm.classify(
            text=text,
            state=session.state.value,
            allowed_intents=[i.value for i in Intent],
            permitted_facts=permitted_facts,
            language=session.language,
        )
        self.store.append_event(
            session,
            "intent.classified",
            "llm",
            {
                "intent": llm.intent.value,
                "slots": llm.slots,
                "confidence": llm.confidence,
                "adapter": type(self.llm).__name__,
            },
        )

        original_intent = llm.intent
        llm = self._enrich_ptp_slots(session, text, llm)
        llm = self._apply_deterministic_intents(session, text, llm)
        if llm.intent != original_intent:
            self.store.append_event(
                session,
                "intent.classified",
                "orchestrator",
                {
                    "intent": llm.intent.value,
                    "replaced": original_intent.value,
                    "adapter": "deterministic_overlay",
                    "confidence": llm.confidence,
                },
            )

        if llm.confidence < 0.45 and session.state in {
            ConversationState.DISCUSSING_OPTIONS,
            ConversationState.CONFIRMING_PTP,
            ConversationState.REMINDER,
        } and llm.intent not in {
            Intent.HARDSHIP,
            Intent.DISPUTE,
            Intent.STOP_CONTACT,
        }:
            llm.intent = Intent.LOW_CONFIDENCE

        dependency_health = {"crm": "available", "policy": "available"}
        decision = self.policy.decide(
            PolicyRequest(
                session_id=session.session_id,
                policy_version=self.settings.policy_version,
                state=session.state,
                identity=session.identity,
                intent=llm.intent,
                slots=llm.slots,
                context=self._policy_context(session),
                dependency_health=dependency_health,
                pending_ptp=session.pending_ptp,
            )
        )
        self.store.append_event(
            session,
            "policy.decided",
            "policy_engine",
            {
                "input_state": session.state.value,
                "allowed": decision.allowed,
                "action": decision.action,
                "next_state": decision.next_state.value,
                "reason_code": decision.reason_code,
            },
        )

        ok, reason = validate_llm_response(
            llm,
            permitted_facts,
            decision.permitted_offer_ids,
        )
        if not ok:
            self.store.append_event(
                session,
                "error.occurred",
                "validator",
                {
                    "component": "llm_validator",
                    "code": reason,
                    "retryable": False,
                    "safe_action": "use_template",
                },
            )
            if decision.template_key:
                pass
            else:
                decision.template_key = "unsupported_discount"

        previous = session.state
        session.state = decision.next_state
        if previous != session.state:
            self.store.append_event(
                session,
                "state.changed",
                "orchestrator",
                {
                    "previous": previous.value,
                    "next": session.state.value,
                    "trigger": decision.action,
                },
            )

        # Side effects
        assistant_text = await self._execute_action(session, decision, llm, pack, text)
        if decision.disposition and session.state in {
            ConversationState.COMPLETED,
            ConversationState.TERMINATED,
            ConversationState.ESCALATING,
        }:
            # Escalating still needs transfer then complete. Do not overwrite a
            # disposition already committed by an integration side-effect (e.g. failed write-back).
            if session.disposition is None:
                session.disposition = decision.disposition
            if session.state == ConversationState.ESCALATING:
                session.state = ConversationState.COMPLETED
            if session.ended_at is None and session.state in {
                ConversationState.COMPLETED,
                ConversationState.TERMINATED,
            }:
                session.ended_at = utc_now()
                self.store.append_event(
                    session,
                    "session.ended",
                    "orchestrator",
                    {
                        "disposition": session.disposition.value if session.disposition else None,
                        "write_back_status": session.write_back_status,
                    },
                )
        return assistant_text

    async def _handle_identity_turn(self, session: SessionRecord, text: str, pack: Any) -> str:
        if detect_wrong_party(text):
            intent = Intent.WRONG_PARTY
        elif detect_prompt_injection(text):
            intent = Intent.PROMPT_INJECTION
        else:
            intent = Intent.IDENTITY_ANSWER
        self.store.append_event(
            session,
            "intent.classified",
            "orchestrator",
            {
                "intent": intent.value,
                "confidence": 1.0,
                "adapter": "deterministic",
            },
        )
        if intent == Intent.PROMPT_INJECTION:
            text_out = pack.render_template(
                "prompt_injection_ignore", {"display_name": session.display_name}
            )
            self._approve(session, text_out, "prompt_injection_ignore")
            return text_out
        return await self._handle_identity(session, text, intent)

    def _apply_deterministic_intents(self, session: SessionRecord, text: str, llm: Any) -> Any:
        if session.identity.status == IdentityStatus.VERIFIED:
            safety = detect_safety_intent(text)
            if safety:
                llm.intent = safety
                llm.confidence = max(float(llm.confidence or 0), 0.95)
                return llm
            if detect_plan_request(text):
                llm.intent = Intent.ACCEPT_PLAN
                llm.confidence = max(float(llm.confidence or 0), 0.95)
                slots = dict(llm.slots or {})
                if detect_explicit_plan_accept(text):
                    slots["confirmation"] = "yes"
                else:
                    slots.pop("confirmation", None)
                llm.slots = slots
                return llm
            if detect_payment_link_request(text):
                llm.intent = Intent.REQUEST_PAYMENT_LINK
                llm.confidence = max(float(llm.confidence or 0), 0.95)
                return llm
        pack = get_language_pack(session.language)
        conf = pack.classify_confirmation(text)
        if session.state == ConversationState.CONFIRMING_PTP and llm.intent in {
            Intent.UNKNOWN,
            Intent.LOW_CONFIDENCE,
            Intent.GREETING,
            Intent.REMINDER_ACK,
        }:
            if conf.value == "yes":
                llm.intent = Intent.CONFIRM_YES
            elif conf.value == "no":
                llm.intent = Intent.CONFIRM_NO
            else:
                llm.intent = Intent.UNKNOWN
                llm.slots = {**(llm.slots or {}), "confirmation": "ambiguous"}
            return llm
        if (
            session.state == ConversationState.DISCUSSING_OPTIONS
            and session.pending_offer_id
            and llm.intent
            in {
                Intent.UNKNOWN,
                Intent.LOW_CONFIDENCE,
                Intent.GREETING,
                Intent.REMINDER_ACK,
                Intent.ACCEPT_PLAN,
            }
        ):
            if conf.value == "yes":
                llm.intent = Intent.CONFIRM_YES
            elif conf.value == "no":
                llm.intent = Intent.CONFIRM_NO
        return llm

    async def _handle_identity(self, session: SessionRecord, text: str, intent: Intent) -> str:
        pack = get_language_pack(session.language)
        lowered = text.lower().strip()
        step = session.identity.step

        if intent == Intent.WRONG_PARTY or detect_wrong_party(text):
            decision = self.policy.decide(
                PolicyRequest(
                    session_id=session.session_id,
                    policy_version=self.settings.policy_version,
                    state=session.state,
                    identity=session.identity,
                    intent=Intent.WRONG_PARTY,
                )
            )
            self.store.append_event(
                session,
                "policy.decided",
                "policy_engine",
                {
                    "allowed": True,
                    "action": decision.action,
                    "next_state": decision.next_state.value,
                    "reason_code": decision.reason_code,
                },
            )
            session.state = ConversationState.TERMINATED
            session.disposition = Disposition.WRONG_PARTY
            session.ended_at = utc_now()
            text_out = pack.render_template("wrong_party_close", {})
            await self._write_outcome(session, Disposition.WRONG_PARTY, {})
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {"disposition": "WRONG_PARTY", "write_back_status": session.write_back_status},
            )
            return text_out

        if step == 0:
            pack_conf = pack.classify_confirmation(text)
            name = (session.display_name or "").strip().lower()
            name_mentioned = bool(name) and name in lowered
            if pack_conf.value != "yes" and not name_mentioned:
                return pack.render_template(
                    "identity_confirm_name", {"display_name": session.display_name}
                )
            session.identity.step = 1
            self.store.append_event(
                session,
                "identity.requested",
                "orchestrator",
                {"question_set_version": "idq-poc-v1", "attempt": session.identity.attempts + 1},
            )
            return pack.render_template("identity_question_birth_day_month", {})

        if step == 1:
            session.identity.step = 2
            session.pending_dob = _normalize_dob(text)
            return pack.render_template("identity_question_customer_id_last4", {})

        # step == 2: submit to mock identity
        dob = session.pending_dob or ""
        last4 = _normalize_last4(text)
        self.store.append_event(
            session,
            "identity.requested",
            "orchestrator",
            {"question_set_version": "idq-poc-v1", "attempt": session.identity.attempts + 1},
        )
        self.store.append_event(
            session,
            "integration.requested",
            "tbc_client",
            {"integration": "identity", "operation": "verify"},
        )
        result = await self.tbc.verify_identity(
            {
                "session_id": session.session_id,
                "customer_ref": session.customer_ref,
                "answers": {
                    "name_confirmed": "true",
                    "birth_day_month": dob,
                    "id_last4": last4,
                },
                "correlation_id": session.correlation_id,
            }
        )
        if "error" in result:
            session.state = ConversationState.TERMINATED
            session.disposition = Disposition.TECHNICAL_FAILURE
            session.ended_at = utc_now()
            await self._write_outcome(session, Disposition.TECHNICAL_FAILURE, {"reason": "identity_timeout"})
            return pack.render_template("technical_failure_close", {})

        status = result.get("status")
        self.store.append_event(
            session,
            "identity.decided",
            "mock_tbc",
            {
                "verified": status == "verified",
                "reason": result.get("reason"),
                "evidence_ref": result.get("evidence_ref"),
            },
            redaction={"contains_pii": False, "fields_removed": ["answers"]},
        )
        self.store.append_event(
            session,
            "integration.completed",
            "tbc_client",
            {"integration": "identity", "status": status, "retry_count": 0},
        )

        if status == "verified":
            session.identity.status = IdentityStatus.VERIFIED
            session.identity.evidence_ref = result.get("evidence_ref")
            session.identity.verification_token = result.get("verification_token")
            # Load protected context
            loaded = await self._load_protected_context(session)
            if not loaded:
                session.state = ConversationState.TERMINATED
                session.disposition = Disposition.TECHNICAL_FAILURE
                session.ended_at = utc_now()
                await self._write_outcome(
                    session, Disposition.TECHNICAL_FAILURE, {"reason": "context_unavailable"}
                )
                self.store.append_event(
                    session,
                    "session.ended",
                    "orchestrator",
                    {
                        "disposition": "TECHNICAL_FAILURE",
                        "write_back_status": session.write_back_status,
                    },
                )
                return pack.render_template("technical_failure_close", {})
            session.state = ConversationState.VERIFIED
            self.store.append_event(
                session,
                "state.changed",
                "orchestrator",
                {
                    "previous": ConversationState.VERIFYING_IDENTITY.value,
                    "next": ConversationState.VERIFIED.value,
                    "trigger": "identity_verified",
                },
            )
            # Deliver reminder immediately
            session.state = ConversationState.REMINDER
            self.store.append_event(
                session,
                "policy.decided",
                "policy_engine",
                {
                    "allowed": True,
                    "action": "deliver_reminder",
                    "next_state": "reminder",
                    "reason_code": "REMINDER_ALLOWED",
                },
            )
            self.store.append_event(
                session,
                "state.changed",
                "orchestrator",
                {
                    "previous": ConversationState.VERIFIED.value,
                    "next": ConversationState.REMINDER.value,
                    "trigger": "deliver_reminder",
                },
            )
            ctx = session.context or {}
            text_out = pack.render_template(
                "reminder_verified",
                {
                    "balance_amount": ctx["balance"]["amount"],
                    "currency": ctx["balance"]["currency"],
                    "due_date": ctx["due_date"],
                },
            )
            self.store.append_event(
                session,
                "assistant.response_approved",
                "orchestrator",
                {
                    "text": text_out,
                    "template": "reminder_verified",
                    "permitted_facts": ["balance", "due_date", "currency"],
                },
            )
            session.state = ConversationState.DISCUSSING_OPTIONS
            self.store.append_event(
                session,
                "state.changed",
                "orchestrator",
                {
                    "previous": ConversationState.REMINDER.value,
                    "next": ConversationState.DISCUSSING_OPTIONS.value,
                    "trigger": "reminder_delivered",
                },
            )
            session.pending_dob = None
            return text_out

        # failed identity
        session.identity.attempts += 1
        session.identity.step = 1
        if session.identity.attempts >= 2:
            session.state = ConversationState.TERMINATED
            session.disposition = Disposition.ID_FAILED
            session.ended_at = utc_now()
            text_out = pack.render_template("identity_failed_close", {})
            await self._write_outcome(session, Disposition.ID_FAILED, {})
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {"disposition": "ID_FAILED", "write_back_status": session.write_back_status},
            )
            return text_out
        return pack.render_template("identity_failed_retry", {})

    async def _load_protected_context(self, session: SessionRecord) -> bool:
        assert session.identity.verification_token
        self.store.append_event(
            session,
            "integration.requested",
            "tbc_client",
            {"integration": "crm", "operation": "collections-context"},
        )
        ctx = await self.tbc.collections_context(
            session.customer_ref,
            session.session_id,
            session.identity.verification_token,
            session.correlation_id,
        )
        if "error" in ctx:
            self.store.append_event(
                session,
                "integration.completed",
                "tbc_client",
                {"integration": "crm", "status": "error", "retry_count": 0},
            )
            self.store.append_event(
                session,
                "error.occurred",
                "tbc_client",
                {
                    "component": "crm",
                    "code": ctx["error"]["code"],
                    "retryable": ctx["error"].get("retryable", True),
                    "safe_action": "close_without_disclosure",
                },
            )
            return False
        offers_resp = await self.tbc.eligible_offers(
            session.customer_ref,
            session.session_id,
            session.identity.verification_token,
            session.correlation_id,
        )
        session.context = ctx
        session.offers = [
            o for o in offers_resp.get("offers", []) if not o.get("expired")
        ]
        self.store.append_event(
            session,
            "integration.completed",
            "tbc_client",
            {"integration": "crm", "status": "ok", "retry_count": 0},
        )
        return True

    async def _execute_action(
        self,
        session: SessionRecord,
        decision: Any,
        llm: Any,
        pack: Any,
        user_text: str,
    ) -> str:
        values = self._template_values(session, llm)

        if decision.action == "continue_identity" and decision.template_key == "prompt_injection_ignore":
            text = pack.render_template(decision.template_key, values)
            self._approve(session, text, decision.template_key)
            return text

        if decision.action == "request_ptp_confirmation":
            session.pending_ptp = {
                "amount": llm.slots.get("amount"),
                "currency": llm.slots.get("currency", "GEL"),
                "date": llm.slots.get("date"),
            }
            values.update(
                {
                    "amount": session.pending_ptp["amount"],
                    "currency": session.pending_ptp["currency"],
                    "date": session.pending_ptp["date"],
                }
            )
            text = pack.render_template("ptp_readback", values)
            self._approve(session, text, "ptp_readback")
            return text

        if decision.action == "revise_ptp":
            session.pending_ptp = None
            slots = dict(llm.slots or {})
            if not slots.get("amount") or not slots.get("date"):
                parsed = pack.normalize_slots(
                    user_text,
                    SlotHints(expect_amount=True, expect_date=True, as_of=self.as_of),
                )
                if parsed.amount:
                    slots["amount"] = parsed.amount
                    slots["currency"] = parsed.currency or "GEL"
                if parsed.date:
                    slots["date"] = parsed.date
            if slots.get("amount") and slots.get("date"):
                session.pending_ptp = {
                    "amount": slots["amount"],
                    "currency": slots.get("currency", "GEL"),
                    "date": slots["date"],
                }
                session.state = ConversationState.CONFIRMING_PTP
                values.update(session.pending_ptp)
                text = pack.render_template("ptp_readback", values)
                self._approve(session, text, "ptp_readback")
                return text
            text = "Understood. Please share the updated amount and date."
            self._approve(session, text, None)
            return text

        if decision.action == "clarify_ptp":
            text = pack.render_template("ptp_ambiguous", values)
            self._approve(session, text, "ptp_ambiguous")
            return text

        if decision.action == "capture_ptp":
            ptp = session.pending_ptp or {}
            self.store.append_event(
                session,
                "ptp.confirmed",
                "orchestrator",
                {
                    "amount": ptp.get("amount"),
                    "currency": ptp.get("currency", "GEL"),
                    "date": ptp.get("date"),
                },
            )
            ok = await self._write_outcome(
                session,
                Disposition.PTP_CAPTURED,
                {"ptp": ptp},
                idempotency_key=f"ptp:{session.session_id}",
                retries=2,
            )
            if not ok:
                session.disposition = Disposition.TECHNICAL_FAILURE
                session.state = ConversationState.TERMINATED
                text = pack.render_template("outcome_failed", values)
                self._approve(session, text, "outcome_failed")
                return text
            values.update(
                {
                    "amount": ptp.get("amount"),
                    "currency": ptp.get("currency", "GEL"),
                    "date": ptp.get("date"),
                }
            )
            text = pack.render_template("ptp_captured", values)
            self._approve(session, text, "ptp_captured")
            session.disposition = Disposition.PTP_CAPTURED
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": "PTP_CAPTURED",
                    "write_back_status": session.write_back_status,
                },
            )
            return text

        if decision.action == "request_payment_link":
            await self._request_payment_link(session)
            text = pack.render_template("payment_link_acknowledged", values)
            self._approve(session, text, "payment_link_acknowledged")
            await self._write_outcome(session, Disposition.PAYMENT_LINK_REQUESTED, {})
            session.disposition = Disposition.PAYMENT_LINK_REQUESTED
            session.state = ConversationState.COMPLETED
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": "PAYMENT_LINK_REQUESTED",
                    "write_back_status": session.write_back_status,
                },
            )
            return text

        if decision.action in {"hardship_transfer", "dispute_transfer"}:
            template = decision.template_key or "hardship_transfer"
            text = pack.render_template(template, values)
            self._approve(session, text, template)
            disposition = decision.disposition or Disposition.HUMAN_TRANSFERRED
            await self._transfer(
                session,
                reason=decision.action,
                priority="high",
                disposition=disposition,
            )
            session.disposition = disposition
            session.state = ConversationState.COMPLETED
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": disposition.value,
                    "write_back_status": session.write_back_status,
                },
            )
            return text

        if decision.action == "stop_contact":
            text = pack.render_template("stop_contact_close", values)
            self._approve(session, text, "stop_contact_close")
            await self.tbc.suppress(
                {
                    "session_id": session.session_id,
                    "customer_ref": session.customer_ref,
                    "correlation_id": session.correlation_id,
                    "idempotency_key": f"sup:{session.session_id}",
                }
            )
            await self._write_outcome(session, Disposition.STOP_CONTACT, {"suppressed": True})
            session.disposition = Disposition.STOP_CONTACT
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": "STOP_CONTACT",
                    "write_back_status": session.write_back_status,
                },
            )
            return text

        if decision.action == "record_already_paid_claim":
            text = pack.render_template("already_paid_ack", values)
            self._approve(session, text, "already_paid_ack")
            await self._write_outcome(
                session, Disposition.ALREADY_PAID_CLAIMED, {"claim_only": True}
            )
            session.disposition = Disposition.ALREADY_PAID_CLAIMED
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": "ALREADY_PAID_CLAIMED",
                    "write_back_status": session.write_back_status,
                },
            )
            return text

        if decision.action in {"present_plan", "accept_plan", "decline_plan"}:
            if decision.action == "decline_plan":
                session.pending_offer_id = None
                text = pack.render_template("discuss_options_prompt", values)
                self._approve(session, text, "discuss_options_prompt")
                return text
            if decision.action == "accept_plan" and decision.disposition == Disposition.PLAN_ACCEPTED:
                offer_id = (llm.slots or {}).get("offer_id") or session.pending_offer_id
                text = pack.render_template("payment_plan_accepted", values)
                self._approve(session, text, "payment_plan_accepted")
                await self._write_outcome(
                    session,
                    Disposition.PLAN_ACCEPTED,
                    {"offer_id": offer_id},
                )
                session.pending_offer_id = None
                session.disposition = Disposition.PLAN_ACCEPTED
                session.ended_at = utc_now()
                self.store.append_event(
                    session,
                    "session.ended",
                    "orchestrator",
                    {
                        "disposition": "PLAN_ACCEPTED",
                        "write_back_status": session.write_back_status,
                    },
                )
                return text
            offer = next((o for o in session.offers if o["offer_id"] in decision.permitted_offer_ids), None)
            if not offer and session.offers:
                offer = session.offers[0]
            if offer:
                session.pending_offer_id = offer["offer_id"]
                text = pack.render_template(
                    "payment_plan_offer", {"offer_text": offer["display_text"]}
                )
            else:
                text = pack.render_template("unsupported_discount", values)
            self._approve(session, text, "payment_plan_offer")
            return text

        if decision.template_key:
            text = pack.render_template(decision.template_key, values)
            # Prefer template over untrusted LLM prose for safety-critical paths
            self._approve(session, text, decision.template_key)
            if decision.disposition and decision.safe_close:
                await self._write_outcome(session, decision.disposition, {})
                session.disposition = decision.disposition
                session.ended_at = utc_now()
                self.store.append_event(
                    session,
                    "session.ended",
                    "orchestrator",
                    {
                        "disposition": decision.disposition.value,
                        "write_back_status": session.write_back_status,
                    },
                )
            return text

        text = pack.render_template("discuss_options_prompt", values)
        self._approve(session, text, "discuss_options_prompt")
        return text

    def _approve(self, session: SessionRecord, text: str, template: str | None) -> None:
        self.store.append_event(
            session,
            "assistant.response_approved",
            "orchestrator",
            {
                "text": text,
                "template": template,
                "content_version": self.settings.content_version,
            },
        )

    async def _write_outcome(
        self,
        session: SessionRecord,
        disposition: Disposition,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        retries: int = 1,
    ) -> bool:
        key = idempotency_key or f"out:{session.session_id}:{disposition.value}"
        body = {
            "session_id": session.session_id,
            "customer_ref": session.customer_ref,
            "disposition": disposition.value,
            "payload": payload,
            "correlation_id": session.correlation_id,
            "idempotency_key": key,
        }
        attempt = 0
        while attempt <= retries:
            self.store.append_event(
                session,
                "integration.requested",
                "tbc_client",
                {
                    "integration": "crm",
                    "operation": "outcome",
                    "idempotency_key": key,
                },
            )
            result = await self.tbc.write_outcome(body)
            if "error" in result:
                retryable = result["error"].get("retryable", False)
                self.store.append_event(
                    session,
                    "integration.completed",
                    "tbc_client",
                    {
                        "integration": "crm",
                        "status": "error",
                        "retry_count": attempt,
                    },
                )
                if retryable and attempt < retries:
                    attempt += 1
                    await asyncio.sleep(0.05)
                    continue
                session.write_back_status = "failed"
                self.store.append_event(
                    session,
                    "error.occurred",
                    "tbc_client",
                    {
                        "component": "outcome",
                        "code": result["error"]["code"],
                        "retryable": retryable,
                        "safe_action": result["error"].get("safe_action"),
                    },
                )
                return False
            session.write_back_status = "written"
            self.store.append_event(
                session,
                "integration.completed",
                "tbc_client",
                {
                    "integration": "crm",
                    "status": "ok",
                    "external_reference": result.get("outcome", {}).get("outcome_id"),
                    "retry_count": attempt,
                },
            )
            return True
        session.write_back_status = "failed"
        return False

    async def _request_payment_link(self, session: SessionRecord) -> None:
        self.store.append_event(
            session,
            "integration.requested",
            "tbc_client",
            {"integration": "payment_link", "operation": "request"},
        )
        result = await self.tbc.payment_link(
            {
                "session_id": session.session_id,
                "customer_ref": session.customer_ref,
                "offer_or_payment_ref": session.customer_ref,
                "correlation_id": session.correlation_id,
                "idempotency_key": f"plink:{session.session_id}",
            }
        )
        self.store.append_event(
            session,
            "payment_link.requested",
            "tbc_client",
            {
                "request_id": result.get("request_id"),
                "status": result.get("status"),
            },
        )

    async def _transfer(
        self,
        session: SessionRecord,
        reason: str,
        priority: str,
        disposition: Disposition,
    ) -> None:
        summary = {
            "customer_ref": session.customer_ref,
            "verified": session.identity.status == IdentityStatus.VERIFIED,
            "reason": reason,
            "state": session.state.value,
        }
        self.store.append_event(
            session,
            "integration.requested",
            "tbc_client",
            {"integration": "transfer", "operation": "request"},
        )
        result = await self.tbc.transfer(
            {
                "session_id": session.session_id,
                "customer_ref": session.customer_ref,
                "route": "collections_specialist",
                "reason": reason,
                "priority": priority,
                "verified": session.identity.status == IdentityStatus.VERIFIED,
                "summary": summary,
                "correlation_id": session.correlation_id,
                "idempotency_key": f"tr:{session.session_id}",
            }
        )
        self.store.append_event(
            session,
            "transfer.requested",
            "tbc_client",
            {
                "route": "collections_specialist",
                "reason": reason,
                "priority": priority,
                "status": result.get("status"),
            },
        )
        await self._write_outcome(
            session,
            disposition,
            {"transfer": result},
            idempotency_key=f"out:{session.session_id}:{disposition.value}",
        )

    def _policy_context(self, session: SessionRecord) -> dict[str, Any] | None:
        if not session.context:
            return None
        return {
            "eligible_offer_ids": [o["offer_id"] for o in session.offers],
            "account_status": "overdue",
            "ptp_policy": session.context.get("ptp_policy"),
            "balance": session.context.get("balance"),
            "due_date": session.context.get("due_date"),
            "pending_offer_id": session.pending_offer_id,
        }

    def _permitted_fact_map(self, session: SessionRecord) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "display_name": session.display_name,
            "eligible_offer_ids": [o["offer_id"] for o in session.offers],
        }
        if session.identity.status == IdentityStatus.VERIFIED and session.context:
            facts["balance_amount"] = session.context["balance"]["amount"]
            facts["currency"] = session.context["balance"]["currency"]
            facts["due_date"] = session.context["due_date"]
        facts["as_of_date"] = self.as_of.isoformat()
        if session.pending_ptp:
            facts["requested_amount"] = session.pending_ptp.get("amount")
            facts["requested_date"] = session.pending_ptp.get("date")
        return facts

    def _enrich_ptp_slots(self, session: SessionRecord, text: str, llm: Any) -> Any:
        """Fill amount/date from speech when the model leaves slots incomplete."""
        if session.state not in {
            ConversationState.DISCUSSING_OPTIONS,
            ConversationState.CONFIRMING_PTP,
            ConversationState.REMINDER,
        }:
            return llm
        lowered = text.lower()
        if "pay" not in lowered and llm.intent not in {
            Intent.PROMISE_TO_PAY,
            Intent.CORRECT_PTP,
        }:
            return llm
        pack = get_language_pack(session.language)
        parsed = pack.normalize_slots(
            text,
            SlotHints(expect_amount=True, expect_date=True, as_of=self.as_of),
        )
        slots = _canonical_ptp_slots(llm.slots)
        if not slots.get("date") and parsed.date:
            slots["date"] = parsed.date
        if not slots.get("amount") and parsed.amount:
            slots["amount"] = parsed.amount
            slots["currency"] = parsed.currency or "GEL"
        if not slots.get("amount") and any(
            p in lowered for p in ("that", "the balance", "full amount", "all of it")
        ):
            if session.context and session.context.get("balance"):
                slots["amount"] = session.context["balance"]["amount"]
                slots["currency"] = session.context["balance"].get("currency", "GEL")
        if slots.get("amount") and slots.get("date"):
            if llm.intent in {Intent.UNKNOWN, Intent.LOW_CONFIDENCE, Intent.REMINDER_ACK}:
                llm.intent = Intent.PROMISE_TO_PAY
            llm.slots = slots
            if llm.confidence < 0.7:
                llm.confidence = 0.9
        elif slots:
            llm.slots = slots
        return llm

    def _template_values(self, session: SessionRecord, llm: Any) -> dict[str, object]:
        values: dict[str, object] = {"display_name": session.display_name}
        if session.context:
            values["balance_amount"] = session.context["balance"]["amount"]
            values["currency"] = session.context["balance"]["currency"]
            values["due_date"] = session.context["due_date"]
        if session.pending_ptp:
            values.update({k: v for k, v in session.pending_ptp.items() if not k.startswith("_")})
        if llm.slots:
            values.update({k: v for k, v in llm.slots.items() if v is not None})
        return values

    def _require(self, session_id: str) -> SessionRecord:
        session = self.store.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session

    async def end_session(self, session_id: str) -> SessionRecord:
        session = self._require(session_id)
        if session.state not in {ConversationState.COMPLETED, ConversationState.TERMINATED}:
            session.state = ConversationState.TERMINATED
            session.disposition = session.disposition or Disposition.CUSTOMER_ENDED
            if session.write_back_status is None:
                await self._write_outcome(session, session.disposition, {})
            session.ended_at = utc_now()
            self.store.append_event(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": session.disposition.value,
                    "write_back_status": session.write_back_status,
                },
            )
        return session


def _canonical_ptp_slots(slots: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(slots or {})
    if not out.get("date"):
        for key in ("payment_date", "pay_date", "ptp_date"):
            if out.get(key):
                out["date"] = out[key]
                break
    if not out.get("amount"):
        for key in ("payment_amount", "ptp_amount"):
            if out.get(key):
                out["amount"] = out[key]
                break
    return out


_MONTH_ALT = (
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)


def _normalize_dob(text: str) -> str:
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    ordinals = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "eleventh": 11,
        "twelfth": 12,
        "thirteenth": 13,
        "fourteenth": 14,
        "fifteenth": 15,
        "sixteenth": 16,
        "seventeenth": 17,
        "eighteenth": 18,
        "nineteenth": 19,
        "twentieth": 20,
        "twenty first": 21,
        "twenty-first": 21,
        "twenty second": 22,
        "twenty-second": 22,
        "twenty third": 23,
        "twenty-third": 23,
        "twenty fourth": 24,
        "twenty-fourth": 24,
        "twenty fifth": 25,
        "twenty-fifth": 25,
        "twenty sixth": 26,
        "twenty-sixth": 26,
        "twenty seventh": 27,
        "twenty-seventh": 27,
        "twenty eighth": 28,
        "twenty-eighth": 28,
        "twenty ninth": 29,
        "twenty-ninth": 29,
        "thirtieth": 30,
        "thirty first": 31,
        "thirty-first": 31,
    }
    t = text.strip().lower().replace(",", " ")
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", t)
    # Spoken fillers: "January the 9th", "born on the 9th of January"
    t = re.sub(r"\b(the|of|on|my|birthday|birthdate|born)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # "15 March" / "9 January"
    m = re.search(rf"(\d{{1,2}})\s+({_MONTH_ALT})", t)
    if m:
        return f"{months[m.group(2)]}-{int(m.group(1)):02d}"
    # "March 15" / "January 9"
    m = re.search(rf"({_MONTH_ALT})\s+(\d{{1,2}})", t)
    if m:
        return f"{months[m.group(1)]}-{int(m.group(2)):02d}"
    # "fifteenth of March" / "January ninth"
    for phrase, day in sorted(ordinals.items(), key=lambda kv: -len(kv[0])):
        if phrase in t:
            for name, mm in months.items():
                if name in t:
                    return f"{mm}-{day:02d}"
            break
    # MM-DD or M-D
    m = re.search(r"(0?\d|1[0-2])[-/](0?\d|[12]\d|3[01])", t)
    if m:
        return f"{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return t


_WORD_DIGITS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}


def _normalize_last4(text: str) -> str:
    raw = text.strip().lower()
    # Spoken digits: "zero zero zero one", "oh oh oh one"
    words = re.findall(r"[a-z0-9]+", raw)
    spoken = "".join(_WORD_DIGITS.get(w, w if w.isdigit() else "") for w in words)
    spoken_digits = re.sub(r"\D", "", spoken)
    if len(spoken_digits) >= 4:
        return spoken_digits[-4:]
    # Compact alphanumerics already present
    compact = re.sub(r"[^a-z0-9]", "", raw)
    if len(compact) >= 4:
        return compact[-4:]
    digits = re.findall(r"\d", raw)
    if len(digits) >= 4:
        return "".join(digits[-4:])
    return compact[-4:] if compact else raw[-4:]
