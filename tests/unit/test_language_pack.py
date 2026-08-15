"""Language pack scaffolding tests."""

from tbc_voice_agent.content import EnglishLanguagePack, GeorgianLanguagePackStub, SlotHints, get_language_pack


def test_english_amount_date_normalization():
    pack = EnglishLanguagePack()
    slots = pack.normalize_slots(
        "I can pay 275.40 GEL on 28 August",
        SlotHints(expect_amount=True, expect_date=True),
    )
    assert slots.amount == "275.40"
    assert slots.date == "2026-08-28"


def test_language_pack_selection():
    assert get_language_pack("en-US").language_code == "en-US"
    assert isinstance(get_language_pack("ka-GE"), GeorgianLanguagePackStub)


def test_confirmation_classifier():
    pack = EnglishLanguagePack()
    assert pack.classify_confirmation("Yes").value == "yes"
    assert pack.classify_confirmation("probably").value == "ambiguous"
