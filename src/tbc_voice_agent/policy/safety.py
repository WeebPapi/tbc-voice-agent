"""Deterministic safety-intent overlay.

The LLM may miss hardship, dispute, or stop-contact phrasing. Code must still
classify those turns before policy runs, in every post-verification state.
"""

from __future__ import annotations

from tbc_voice_agent.domain import Intent

HARDSHIP_PHRASES = (
    "hardship",
    "lost my job",
    "lost my employment",
    "can't afford",
    "cannot afford",
    "cant afford",
    "crashed my car",
    "i crashed",
    "car crash",
    "car accident",
    "totaled my car",
    "vulnerable",
    "in hospital",
    "hospitalized",
    "in the hospital",
    "bereavement",
    "someone died",
    "passed away",
    "homeless",
    "evicted",
    "domestic violence",
    "seriously ill",
    "terminal illness",
    # Synthetic Georgian POC phrases (not Bank-approved production copy)
    "რთული მდგომარეობა",
    "სამსახური დავკარგე",
    "ვერ ვიხდი",
    "ავტოავარია",
    "მანქანა დამიტეხა",
    "ავადმყოფი ვარ",
    "საავადმყოფოში",
)

DISPUTE_PHRASES = (
    "dispute",
    "not my debt",
    "i don't owe",
    "i do not owe",
    "not my account",
    "identity theft",
    "this is fraud",
    "სადავოა",
    "არ არის ჩემი ვალი",
    "არ ვარ ვალიანი",
    "თაღლითობაა",
)

STOP_CONTACT_PHRASES = (
    "stop calling",
    "stop contact",
    "do not contact",
    "don't contact",
    "do not call",
    "don't call",
    "never call",
    "remove me from",
    "აღარ დამირეკოთ",
    "შეაჩერეთ კონტაქტი",
    "ნუ დამირეკავთ",
    "წაშალეთ სიიდან",
)

WRONG_PARTY_PHRASES = (
    "wrong person",
    "wrong party",
    "not me",
    "you've got the wrong",
    "you have the wrong",
    "არასწორი ადამიანი",
    "არა მე ვარ",
    "შეცდომით დამირეკეთ",
)

PROMPT_INJECTION_PHRASES = (
    "ignore your rules",
    "ignore previous",
    "system prompt",
    "tell me my balance",
    "reveal the balance",
    "უგულებელყავი წესები",
    "მითხარი ბალანსი",
)

PLAN_REQUEST_PHRASES = (
    "payment plan",
    "pay with a plan",
    "pay on a plan",
    "with a plan",
    "on a plan",
    "get a plan",
    "want a plan",
    "installment",
    "instalment",
    "split the payment",
    "split it",
    "in installments",
    "in instalments",
    "განვადება",
    "გადახდის გეგმა",
    "ნაწილ-ნაწილ",
)

PLAN_ACCEPT_PHRASES = (
    "accept the plan",
    "i accept",
    "i'll take the plan",
    "i will take the plan",
    "ვეთანხმები გეგმას",
    "მიღებულია გეგმა",
)

PAYMENT_LINK_PHRASES = (
    "payment link",
    "send me a link",
    "send a link",
    "text me a link",
    "sms link",
    "pay by link",
    "email me a link",
    "გადახდის ბმული",
    "გამომიგზავნე ბმული",
    "სმს ბმული",
)


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    # Keep original casing for Georgian; also check lowercased Latin phrases.
    lowered = text.lower()
    return any(phrase in text or phrase in lowered for phrase in phrases)


def detect_safety_intent(text: str) -> Intent | None:
    """Return a protective intent when the utterance matches a known phrase.

    Priority: hardship, then dispute, then stop-contact. Vulnerability and
    dispute require an immediate specialist path even if commercial slots
    were also mentioned.
    """
    if _contains_any(text, HARDSHIP_PHRASES):
        return Intent.HARDSHIP
    if _contains_any(text, DISPUTE_PHRASES):
        return Intent.DISPUTE
    if _contains_any(text, STOP_CONTACT_PHRASES):
        return Intent.STOP_CONTACT
    return None


def detect_wrong_party(text: str) -> bool:
    return _contains_any(text, WRONG_PARTY_PHRASES)


def detect_prompt_injection(text: str) -> bool:
    return _contains_any(text, PROMPT_INJECTION_PHRASES)


def detect_explicit_plan_accept(text: str) -> bool:
    return _contains_any(text, PLAN_ACCEPT_PHRASES)


def detect_plan_request(text: str) -> bool:
    """True for installment/plan requests, not 'I plan to pay …'."""
    lowered = text.lower()
    if "plan to pay" in lowered or "planning to pay" in lowered:
        return False
    if detect_explicit_plan_accept(text):
        return True
    return _contains_any(text, PLAN_REQUEST_PHRASES)


def detect_payment_link_request(text: str) -> bool:
    return _contains_any(text, PAYMENT_LINK_PHRASES)
