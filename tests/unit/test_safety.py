"""Deterministic safety phrase tests."""

from tbc_voice_agent.content import EnglishLanguagePack
from tbc_voice_agent.domain import Intent
from tbc_voice_agent.policy.safety import detect_safety_intent


def test_car_crash_is_hardship():
    assert detect_safety_intent("Oh, I crashed my car") == Intent.HARDSHIP
    assert detect_safety_intent("I crashed my car.") == Intent.HARDSHIP


def test_job_loss_is_hardship():
    assert detect_safety_intent("I lost my job and this is a hardship") == Intent.HARDSHIP


def test_dispute_and_stop_contact():
    assert detect_safety_intent("I dispute this debt") == Intent.DISPUTE
    assert detect_safety_intent("Please stop contact") == Intent.STOP_CONTACT


def test_unrelated_is_none():
    assert detect_safety_intent("I can pay that on the 15th of August") is None


def test_pay_with_a_plan_is_plan_not_link():
    from tbc_voice_agent.policy.safety import (
        detect_payment_link_request,
        detect_plan_request,
    )

    assert detect_plan_request("Can I pay with a plan?") is True
    assert detect_payment_link_request("Can I pay with a plan?") is False
    assert detect_plan_request("I want a payment plan") is True
    assert detect_plan_request("I plan to pay tomorrow") is False
    assert detect_payment_link_request("Please send me a payment link") is True


def test_confirmation_does_not_treat_not_as_no():
    pack = EnglishLanguagePack()
    assert pack.classify_confirmation("not my debt").value != "no"
    assert pack.classify_confirmation("Yes, I can do that").value == "yes"
    assert pack.classify_confirmation("No.").value == "no"
