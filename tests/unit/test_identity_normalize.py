"""Identity answer normalization helpers."""

from tbc_voice_agent.orchestrator import _normalize_dob, _normalize_last4


def test_normalize_last4_digits():
    assert _normalize_last4("0001") == "0001"
    assert _normalize_last4("my id ends with 0001") == "0001"


def test_normalize_last4_spoken():
    assert _normalize_last4("zero zero zero one") == "0001"
    assert _normalize_last4("oh oh oh one") == "0001"


def test_normalize_dob_spoken_english():
    assert _normalize_dob("January the 9th") == "01-09"
    assert _normalize_dob("January the 9th.") == "01-09"
    assert _normalize_dob("January the ninth") == "01-09"
    assert _normalize_dob("9th January") == "01-09"
    assert _normalize_dob("the 9th of January") == "01-09"
    assert _normalize_dob("9 January") == "01-09"
    assert _normalize_dob("born on January 9") == "01-09"
    assert _normalize_dob("15 March") == "03-15"


def test_pay_that_on_ordinal_date():
    from tbc_voice_agent.content import EnglishLanguagePack, SlotHints

    pack = EnglishLanguagePack()
    slots = pack.normalize_slots(
        "I can pay that on the 30th of August.",
        SlotHints(expect_amount=True, expect_date=True),
    )
    assert slots.date == "2026-08-30"
    assert slots.amount is None  # amount comes from balance context
    slots2 = pack.normalize_slots(
        "I can pay that on August the 15th",
        SlotHints(expect_amount=True, expect_date=True),
    )
    assert slots2.date == "2026-08-15"


def test_pay_that_tomorrow():
    from datetime import date

    from tbc_voice_agent.content import EnglishLanguagePack, SlotHints

    pack = EnglishLanguagePack()
    as_of = date(2026, 8, 15)
    slots = pack.normalize_slots(
        "I can pay that tomorrow.",
        SlotHints(expect_amount=True, expect_date=True, as_of=as_of),
    )
    assert slots.date == "2026-08-16"
    assert slots.amount is None
    today = pack.normalize_slots(
        "I can pay today",
        SlotHints(expect_amount=True, expect_date=True, as_of=as_of),
    )
    assert today.date == "2026-08-15"
    in_two = pack.normalize_slots(
        "I can pay in 2 days",
        SlotHints(expect_amount=True, expect_date=True, as_of=as_of),
    )
    assert in_two.date == "2026-08-17"
