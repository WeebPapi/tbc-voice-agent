"""Language pack scaffolding tests."""

from datetime import date

from tbc_voice_agent.content import (
    EnglishLanguagePack,
    GeorgianLanguagePack,
    GeorgianLanguagePackStub,
    SlotHints,
    get_language_pack,
)


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
    assert isinstance(get_language_pack("ka-GE"), GeorgianLanguagePack)
    assert isinstance(get_language_pack("ka-GE"), GeorgianLanguagePackStub)


def test_confirmation_classifier():
    pack = EnglishLanguagePack()
    assert pack.classify_confirmation("Yes").value == "yes"
    assert pack.classify_confirmation("probably").value == "ambiguous"


def test_georgian_confirmation_and_slots():
    pack = GeorgianLanguagePack()
    assert pack.classify_confirmation("კი").value == "yes"
    assert pack.classify_confirmation("დიახ").value == "yes"
    assert pack.classify_confirmation("არა").value == "no"
    assert pack.classify_confirmation("კი, მე ვარ").value == "yes"
    assert pack.classify_confirmation("სოფრობთ ალექს მორგენთან").value == "ambiguous"
    slots = pack.normalize_slots(
        "გადავიხდი 275.40 ლარი 28 აგვისტო",
        SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 14)),
    )
    assert slots.amount == "275.40"
    assert slots.date == "2026-08-28"
    greeting = pack.render_template("greeting_neutral", {"display_name": "Alex Morgan"})
    assert "გამარჯობა" in greeting
    assert "[ka-GE stub" not in greeting


def test_georgian_date_only_does_not_steal_day_as_amount():
    pack = GeorgianLanguagePack()
    slots = pack.normalize_slots(
        "გადავიხდი 13 აგვისტოს",
        SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 14)),
    )
    assert slots.date == "2026-08-13"
    assert slots.amount is None


def test_georgian_spoken_amount_words():
    from tbc_voice_agent.content import parse_georgian_cardinal

    assert parse_georgian_cardinal("ორასი") == 200
    assert parse_georgian_cardinal("ორასის") == 200
    assert parse_georgian_cardinal("ორას") == 200
    pack = GeorgianLanguagePack()
    for utterance in (
        "ორასი ლარი",
        "ორასი",
        "ორასის",
        "გადავიხდი ორასი ლარი",
        "ორას ლარს",
        "ორასლარს",
        "ორასი ლარის",
        "ორას ლარს გადავიხდი 17 აგვისტოს",
        "ორასლარს გადავიხდი 17 აგვისტოს",
    ):
        slots = pack.normalize_slots(
            utterance,
            SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 15)),
        )
        assert slots.amount == "200.00", utterance
    # Combined PTP utterance should also keep the date
    both = pack.normalize_slots(
        "ორას ლარს გადავიხდი 17 აგვისტოს",
        SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 15)),
    )
    assert both.amount == "200.00"
    assert both.date == "2026-08-17"
    # Birthday phrase must not become money
    dob = pack.normalize_slots(
        "თხუთმეტი მარტი",
        SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 14)),
    )
    assert dob.amount is None


def test_georgian_spoken_day_month_date():
    pack = GeorgianLanguagePack()
    as_of = date(2026, 8, 15)
    for utterance, expected in (
        ("ოცი აგვისტო", "2026-08-20"),
        ("ოც აგვისტოს", "2026-08-20"),
        ("Ოცი აგვისტო.", "2026-08-20"),
        ("გადავიხდი ოც აგვისტოს", "2026-08-20"),
        ("და 45 ოც აგვისტოს", "2026-08-20"),
        ("თხუთმეტი მარტი", "2026-03-15"),
    ):
        slots = pack.normalize_slots(
            utterance,
            SlotHints(expect_amount=True, expect_date=True, as_of=as_of),
        )
        assert slots.date == expected, utterance


def test_georgian_full_balance_phrases_do_not_steal_date():
    pack = GeorgianLanguagePack()
    slots = pack.normalize_slots(
        "შემიძლია მთლიანად დავფარო ოც აგვისტოს",
        SlotHints(expect_amount=True, expect_date=True, as_of=date(2026, 8, 15)),
    )
    assert slots.date == "2026-08-20"
    assert slots.amount is None  # balance fill is orchestrator/LLM, not pack


def test_ptp_clarify_templates_exist():
    pack = GeorgianLanguagePack()
    out = pack.render_template(
        "ptp_out_of_range",
        {
            "as_of": "2026-08-14",
            "maximum_date": "2026-09-13",
            "minimum_amount": "25.00",
        },
    )
    assert "ფასდაკლებას" not in out
    assert "გეგმა" not in out
    assert "25.00" in out
    need_amt = pack.render_template("ptp_need_amount", {"date": "2026-08-28"})
    assert "2026-08-28" in need_amt
    need_date = pack.render_template(
        "ptp_need_date", {"amount": "275.40", "currency": "GEL"}
    )
    assert "275.40" in need_date


def test_customer_name_mentioned_latin_and_georgian_stt():
    from tbc_voice_agent.content import customer_name_mentioned

    assert customer_name_mentioned("yes, Alex Morgan speaking", "Alex Morgan")
    assert customer_name_mentioned("სოფრობთ ალექს მორგენთან.", "Alex Morgan")
    assert customer_name_mentioned(
        "Თითქოს ვსოფრობთ დალექს მორგენთან.", "Alex Morgan"
    )
    assert not customer_name_mentioned("გამარჯობა", "Alex Morgan")
    assert not customer_name_mentioned("ალექს მხოლოდ", "Alex Morgan")


def test_prepare_spoken_text_expands_amount_and_date():
    from tbc_voice_agent.content import georgian_cardinal, prepare_spoken_text

    assert georgian_cardinal(15) == "თხუთმეტი"
    assert georgian_cardinal(275) == "ორას სამოცდათხუთმეტი"
    spoken = prepare_spoken_text(
        "ვადაგადაცილებული ბალანსი 275.40 GEL, ვადა 2026-08-10.",
        "ka-GE",
    )
    assert "275.40" not in spoken
    assert "GEL" not in spoken
    assert "2026-08-10" not in spoken
    assert "ორას სამოცდათხუთმეტი ლარი და ორმოცი თეთრი" in spoken
    assert "ათი აგვისტო" in spoken
    assert "ორი ათას ოცდაექვსი" in spoken
    example = prepare_spoken_text("მაგალითად 15 მარტი.", "ka-GE")
    assert "თხუთმეტი მარტი" in example
    assert prepare_spoken_text("275.40 GEL", "en-US") == "275.40 GEL"