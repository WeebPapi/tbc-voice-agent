"""Unit tests for LLM slot normalizer grounding and FakeLLM.normalize."""

from __future__ import annotations

import pytest

from tbc_voice_agent.providers.llm import FakeLLM
from tbc_voice_agent.providers.slot_normalizer import (
    NormalizedTurnSlots,
    ground_slots,
    needs_normalization,
    parse_normalized_payload,
)


def test_ground_slots_rejects_invented_day_despite_month_cue():
    """LLM must not invent Aug 17 when the customer said ოცი (20) აგვისტო."""
    text = "Ოცი აგვისტო."
    out = ground_slots(
        text,
        {"amount": "275.00", "date": "2026-08-17", "currency": "GEL"},
        {"balance_amount": "275.40", "as_of_date": "2026-08-15"},
    )
    assert "date" not in out
    assert "amount" not in out  # 275.00 not grounded without digits/cardinal/balance phrase


def test_ground_slots_accepts_spoken_day_matching_date():
    out = ground_slots(
        "ოცი აგვისტო",
        {"date": "2026-08-20"},
        {"as_of_date": "2026-08-15"},
    )
    assert out.get("date") == "2026-08-20"


def test_ground_slots_accepts_spoken_ka_amount():
    text = "ორას ლარს გადავიხდი 17 აგვისტოს"
    facts = {"as_of_date": "2026-08-15"}
    out = ground_slots(
        text,
        {"amount": "200.00", "currency": "GEL", "date": "2026-08-17"},
        facts,
    )
    assert out["amount"] == "200.00"
    assert out["date"] == "2026-08-17"


def test_ground_slots_drops_offer_id():
    out = ground_slots(
        "გადახდის გეგმა",
        {"offer_id": "offer-invented-999", "amount": "200.00"},
        {"balance_amount": "275.40"},
    )
    assert "offer_id" not in out
    assert "amount" not in out  # 200 not in transcript


def test_parse_normalized_payload_rejects_bad_schema():
    assert parse_normalized_payload({"amount": "not-a-number"}) is None
    ok = parse_normalized_payload({"amount": "200.00", "confidence": 0.9})
    assert ok is not None
    assert ok.amount == "200.00"


def test_needs_normalization_skips_hardship():
    assert not needs_normalization(
        text="მანქანა დამიტეხა, რთული მდგომარეობაა",
        state="confirming_ptp",
        slots={"amount": "200.00", "date": "2026-08-17"},
        confidence=0.2,
    )


def test_needs_normalization_for_messy_ka_money():
    assert needs_normalization(
        text="ორასლარს გადავიხდი",
        state="discussing_options",
        slots={},
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_fake_llm_normalize_spoken_amount():
    llm = FakeLLM("ka-GE")
    facts = {"as_of_date": "2026-08-15"}
    for utterance in ("ორას ლარს", "ორასლარს", "ორასი ლარის"):
        result = await llm.normalize(
            text=utterance,
            state="discussing_options",
            language="ka-GE",
            permitted_facts=facts,
            expect_amount=True,
            expect_date=True,
        )
        assert result.amount == "200.00", utterance


@pytest.mark.asyncio
async def test_fake_llm_normalize_birth_day_month():
    llm = FakeLLM("ka-GE")
    result = await llm.normalize(
        text="ხუთმეტე მარტი",
        state="verifying_identity",
        language="ka-GE",
        permitted_facts={"as_of_date": "2026-08-14"},
        expect_birth_day_month=True,
    )
    assert result.birth_day_month == "03-15"


@pytest.mark.asyncio
async def test_scripted_invented_json_dropped_by_grounding():
    """OpenAI-shaped inventing payload must not survive ground_slots."""
    raw = {
        "intent": "promise_to_pay",
        "amount": "999.99",
        "currency": "GEL",
        "date": "2026-08-28",
        "confidence": 0.99,
    }
    parsed = NormalizedTurnSlots.model_validate(raw)
    grounded = ground_slots(
        "ორას ლარს გადავიხდი 17 აგვისტოს",
        {**parsed.model_dump(), "offer_id": "offer-invented"},
        {"balance_amount": "275.40", "as_of_date": "2026-08-15"},
    )
    assert grounded.get("amount") != "999.99"
    assert "offer_id" not in grounded
    assert grounded.get("amount") != "275.40"
