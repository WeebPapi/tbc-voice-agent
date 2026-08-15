"""Georgian text-mode scenario subset for /ka (no ElevenLabs credentials)."""

from __future__ import annotations

import pytest

from tbc_voice_agent.domain import CreateSessionRequest, Disposition
from tbc_voice_agent.providers import FakeLLM
from tests.scenarios.helpers import assert_no_forbidden


async def _verify_ka(orch, customer_ref: str, dob: str, last4: str):
    session = await orch.create_session(
        CreateSessionRequest(
            customer_ref=customer_ref,
            transport="text",
            language="ka-GE",
        )
    )
    start = await orch.start_session(session.session_id)
    assert "275.40" not in start.assistant_text
    assert "ბალანსი" not in start.assistant_text or "ვადაგადაცილებული" not in start.assistant_text
    # Greeting must not disclose balance
    assert "overdue" not in start.assistant_text.lower()
    await orch.handle_text_turn(session.session_id, "კი")
    await orch.handle_text_turn(session.session_id, dob)
    result = await orch.handle_text_turn(session.session_id, last4)
    return session, result


@pytest.mark.asyncio
async def test_ka_identity_ptp_happy_path(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, result = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    assert "275.40" in result.assistant_text
    ptp = await orch.handle_text_turn(
        session.session_id, "გადავიხდი 275.40 ლარი 28 აგვისტო"
    )
    assert "275.40" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_date_only_ptp_asks_for_amount(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ask = await orch.handle_text_turn(session.session_id, "გადავიხდი 28 აგვისტოს")
    assert "დასადასტურებლად" not in ask.assistant_text
    assert "ფასდაკლებას" not in ask.assistant_text
    # Should ask for the amount, not read back a guessed balance yet.
    assert "თანხ" in ask.assistant_text or "ლარში" in ask.assistant_text
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.pending_ptp is not None
    assert rec.pending_ptp.get("date") == "2026-08-28"
    assert rec.pending_ptp.get("amount") is None
    ptp = await orch.handle_text_turn(session.session_id, "275.40 ლარი")
    assert "275.40" in ptp.assistant_text
    assert "დასადასტურებლად" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_spoken_amount_words_complete_ptp(harness):
    """STT often returns ორასი ლარი instead of 200."""
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    await orch.handle_text_turn(session.session_id, "გადავიხდი 28 აგვისტოს")
    ptp = await orch.handle_text_turn(session.session_id, "ორასი ლარი")
    assert "200.00" in ptp.assistant_text
    assert "დასადასტურებლად" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_spoken_amount_with_date_same_turn(harness):
    """STT forms like 'ორას ლარს … 17 აგვისტოს' must capture both slots."""
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ptp = await orch.handle_text_turn(
        session.session_id, "ორას ლარს გადავიხდი 17 აგვისტოს"
    )
    assert "200.00" in ptp.assistant_text
    assert "2026-08-17" in ptp.assistant_text
    assert "დასადასტურებლად" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_spoken_amount_compound_lars(harness):
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ptp = await orch.handle_text_turn(
        session.session_id, "ორასლარს გადავიხდი 17 აგვისტოს"
    )
    assert "200.00" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_past_date_ptp_asks_for_new_date(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ask = await orch.handle_text_turn(session.session_id, "გადავიხდი 13 აგვისტოს")
    assert "ფასდაკლებას" not in ask.assistant_text
    assert "დამტკიცებული გეგმა" not in ask.assistant_text
    assert "თარიღ" in ask.assistant_text or "ფარგლ" in ask.assistant_text
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.state.value == "discussing_options"
    # Unusable past date must not stick as pending PTP date.
    assert not (rec.pending_ptp or {}).get("date")


@pytest.mark.asyncio
async def test_ka_cust001_can_still_accept_plan_after_failed_ptp(harness):
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    await orch.handle_text_turn(session.session_id, "გადავიხდი 13 აგვისტოს")
    plan = await orch.handle_text_turn(session.session_id, "გადახდის გეგმა")
    assert "offer" in plan.assistant_text.lower() or "გეგმაზე" in plan.assistant_text
    accept = await orch.handle_text_turn(session.session_id, "კი")
    assert accept.disposition == Disposition.PLAN_ACCEPTED


@pytest.mark.asyncio
async def test_ka_identity_spoken_digit_words(harness):
    """STT often returns ნული/ერთი instead of 0/1 for last4."""
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session = await orch.create_session(
        CreateSessionRequest(
            customer_ref="cust-001",
            transport="text",
            language="ka-GE",
        )
    )
    await orch.start_session(session.session_id)
    await orch.handle_text_turn(session.session_id, "კი")
    await orch.handle_text_turn(session.session_id, "ხუთმეტი მარტი")
    result = await orch.handle_text_turn(
        session.session_id, "ნული, ნული, ნული, ერთი."
    )
    assert "275.40" in result.assistant_text
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.identity.status.value == "verified"


@pytest.mark.asyncio
async def test_ka_identity_accepts_georgian_name_stt(harness):
    """Georgian STT often returns Mkhedruli spellings of Latin demo names."""
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session = await orch.create_session(
        CreateSessionRequest(
            customer_ref="cust-001",
            transport="text",
            language="ka-GE",
        )
    )
    await orch.start_session(session.session_id)
    result = await orch.handle_text_turn(
        session.session_id, "სოფრობთ ალექს მორგენთან."
    )
    assert "დაბადების" in result.assistant_text
    assert "დაადასტუროთ, რომ ვსაუბრობ" not in result.assistant_text


@pytest.mark.asyncio
async def test_ka_hardship_transfer(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, result = await _verify_ka(orch, "cust-004", "9 იანვარი", "0004")
    assert "320.75" in result.assistant_text
    hardship = await orch.handle_text_turn(
        session.session_id, "მანქანა დამიტეხა, რთული მდგომარეობაა"
    )
    assert hardship.disposition in {
        Disposition.VULNERABILITY_ESCALATED,
        Disposition.HUMAN_TRANSFERRED,
    }
    assert_no_forbidden(hardship.assistant_text)
    # Should transfer, not continue PTP negotiation with invented amounts
    assert "999.99" not in hardship.assistant_text


@pytest.mark.asyncio
async def test_ka_spoken_amount_date_readback_as_of_pinned(harness):
    """ორას ლარს … 17 აგვისტოს → 200.00 + date with policy as_of year."""
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ptp = await orch.handle_text_turn(
        session.session_id, "ორას ლარს გადავიხდი 17 აგვისტოს"
    )
    assert "200.00" in ptp.assistant_text
    assert "2026-08-17" in ptp.assistant_text
    assert "დასადასტურებლად" in ptp.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_past_date_uses_ptp_out_of_range_template(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ask = await orch.handle_text_turn(
        session.session_id, "ორას ლარს გადავიხდი 13 აგვისტოს"
    )
    assert "ფასდაკლებას" not in ask.assistant_text
    assert "დამტკიცებული გეგმა" not in ask.assistant_text
    assert "ფარგლ" in ask.assistant_text or "თარიღ" in ask.assistant_text
    events = store.events_after(session.session_id, 0)
    policy = [e for e in events if e.type == "policy.decided"]
    assert any(e.payload.get("reason_code") == "PTP_OUT_OF_RANGE" for e in policy)


@pytest.mark.asyncio
async def test_ka_hardship_during_confirming_ptp(harness):
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    await orch.handle_text_turn(
        session.session_id, "ორას ლარს გადავიხდი 17 აგვისტოს"
    )
    hardship = await orch.handle_text_turn(
        session.session_id, "მანქანა დამიტეხა, რთული მდგომარეობაა"
    )
    assert hardship.disposition in {
        Disposition.VULNERABILITY_ESCALATED,
        Disposition.HUMAN_TRANSFERRED,
    }
    assert "დასადასტურებლად" not in hardship.assistant_text or "სპეციალისტ" in hardship.assistant_text


@pytest.mark.asyncio
async def test_ka_identity_khutmete_uses_normalizer(harness):
    """ხუთმეტე მარტი is repaired via slot normalizer (not only deterministic alias)."""
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session = await orch.create_session(
        CreateSessionRequest(
            customer_ref="cust-001",
            transport="text",
            language="ka-GE",
        )
    )
    await orch.start_session(session.session_id)
    await orch.handle_text_turn(session.session_id, "კი")
    await orch.handle_text_turn(session.session_id, "ხუთმეტე მარტი")
    events = store.events_after(session.session_id, 0)
    norm = [e for e in events if e.type == "slots.normalized"]
    assert norm, "expected slots.normalized for identity DOB repair"
    assert norm[-1].redaction.get("contains_pii") is True
    assert "birth_day_month" not in (norm[-1].payload or {})
    assert "birth_day_month" in (norm[-1].payload.get("fields") or [])
    result = await orch.handle_text_turn(session.session_id, "0001")
    assert "275.40" in result.assistant_text
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.identity.status.value == "verified"


@pytest.mark.asyncio
async def test_ka_normalizer_event_when_classify_slots_empty(harness):
    """Force empty classify slots; enrich/normalizer still completes PTP and may emit event."""
    orch, store, _ = harness
    llm = FakeLLM("ka-GE")
    llm.force_empty_classify_slots = True
    orch.llm = llm
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ptp = await orch.handle_text_turn(
        session.session_id, "ორას ლარს გადავიხდი 17 აგვისტოს"
    )
    assert "200.00" in ptp.assistant_text
    assert "2026-08-17" in ptp.assistant_text
    # Deterministic enrich usually fills first; if normalizer also ran, event is present.
    # Identity path above covers mandatory slots.normalized. Here we assert flow still works.
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_spoken_otsi_agvisto_full_balance(harness):
    """მთლიანად + ოც აგვისტოს → balance amount + 2026-08-20 readback."""
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    ptp = await orch.handle_text_turn(
        session.session_id, "შემიძლია მთლიანად დავფარო ოც აგვისტოს"
    )
    assert "275.40" in ptp.assistant_text
    assert "2026-08-20" in ptp.assistant_text
    assert "დასადასტურებლად" in ptp.assistant_text


@pytest.mark.asyncio
async def test_ka_confirm_no_corrects_to_spoken_august_20(harness):
    """After wrong readback, 'არა, ოც აგვისტოს' must revise to Aug 20, not loop Aug 17."""
    orch, store, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    # Seed a wrong pending PTP date (simulates LLM inventing Aug 17).
    await orch.handle_text_turn(session.session_id, "გადავიხდი 275 ლარი 17 აგვისტოს")
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.state.value == "confirming_ptp"
    assert rec.pending_ptp and rec.pending_ptp.get("date") == "2026-08-17"
    corrected = await orch.handle_text_turn(
        session.session_id, "არა, ოც აგვისტოს გადავიხდი"
    )
    assert "2026-08-20" in corrected.assistant_text
    assert "2026-08-17" not in corrected.assistant_text
    assert "275" in corrected.assistant_text
    confirm = await orch.handle_text_turn(session.session_id, "კი")
    assert confirm.disposition == Disposition.PTP_CAPTURED


@pytest.mark.asyncio
async def test_ka_date_only_spoken_otsi_with_pending_amount(harness):
    orch, _, _ = harness
    orch.llm = FakeLLM("ka-GE")
    session, _ = await _verify_ka(orch, "cust-001", "15 მარტი", "0001")
    await orch.handle_text_turn(session.session_id, "გადავიხდი 275.40 ლარი")
    ptp = await orch.handle_text_turn(session.session_id, "ოცი აგვისტო")
    assert "275.40" in ptp.assistant_text
    assert "2026-08-20" in ptp.assistant_text
