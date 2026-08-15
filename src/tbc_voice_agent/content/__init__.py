"""Language pack protocol and English content."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


@dataclass
class SlotHints:
    expect_amount: bool = False
    expect_date: bool = False
    expect_confirmation: bool = False
    as_of: date | None = None


@dataclass
class NormalizedSlots:
    amount: str | None = None
    currency: str | None = None
    date: str | None = None
    raw_fragments: dict[str, str] = field(default_factory=dict)


@dataclass
class ConfirmationResult:
    value: str  # yes | no | ambiguous
    confidence: float


class LanguagePack(Protocol):
    language_code: str

    def normalize_slots(self, text: str, hints: SlotHints) -> NormalizedSlots: ...

    def classify_confirmation(self, text: str) -> ConfirmationResult: ...

    def render_template(self, key: str, values: dict[str, object]) -> str: ...


EN_TEMPLATES: dict[str, str] = {
    "greeting_neutral": (
        "Hello, this is the TBC demo assistant calling. May I speak with {display_name}?"
    ),
    "identity_confirm_name": (
        "Please confirm that I am speaking with {display_name}."
    ),
    "identity_question_birth_day_month": (
        "For security, please tell me your birth day and month, for example 6 April."
    ),
    "identity_question_customer_id_last4": (
        "Thank you. Please tell me the last four characters of your customer reference."
    ),
    "identity_failed_retry": (
        "I could not verify those details. Let's try once more. "
        "Please confirm your birth day and month."
    ),
    "identity_failed_close": (
        "I was unable to verify your identity, so I will end this call. Goodbye."
    ),
    "wrong_party_close": (
        "Thank you for letting me know. I will end the call now. Goodbye."
    ),
    "reminder_verified": (
        "Thank you for confirming. Our records show an overdue balance of "
        "{balance_amount} {currency}, due on {due_date}. How would you like to proceed?"
    ),
    "ptp_readback": (
        "To confirm, you plan to pay {amount} {currency} on {date}. Is that correct?"
    ),
    "ptp_captured": (
        "Thank you. I have recorded your promise to pay {amount} {currency} on {date}."
    ),
    "ptp_ambiguous": (
        "I need a clear yes before I can record a promise to pay. Is the amount and date correct?"
    ),
    "payment_plan_offer": (
        "You are eligible for this plan: {offer_text}. Would you like to accept it?"
    ),
    "payment_plan_accepted": "Thank you. I have recorded your acceptance of the payment plan.",
    "unsupported_discount": (
        "I cannot change the terms or create a discount. I can offer an approved plan "
        "or connect you with a specialist."
    ),
    "payment_link_acknowledged": (
        "I have requested a payment link to be sent through the bank's secure channel."
    ),
    "already_paid_ack": (
        "Thank you for letting me know you believe this is already paid. "
        "I will record your claim for reconciliation. I cannot confirm settlement on this call."
    ),
    "dispute_transfer": (
        "I understand you are disputing this. I will stop collection discussion and "
        "transfer you to a specialist."
    ),
    "hardship_transfer": (
        "I am sorry you are going through this. I will not continue payment discussion. "
        "I am transferring you to a specialist who can help."
    ),
    "stop_contact_close": (
        "I understand. I will record your request to stop contact and end this call. Goodbye."
    ),
    "technical_failure_close": (
        "I am unable to continue safely right now. I will end the call without discussing "
        "account details. Goodbye."
    ),
    "low_confidence_clarify": (
        "I did not catch that clearly. Please repeat the amount and date."
    ),
    "prompt_injection_ignore": (
        "I still need to verify your identity before we continue. "
        "May I speak with {display_name}?"
    ),
    "discuss_options_prompt": (
        "You can promise a payment date, ask for a payment plan, request a payment link, "
        "or end the call. How would you like to proceed?"
    ),
    "customer_ended": "Understood. Goodbye.",
    "outcome_failed": (
        "I could not save the outcome securely, so I will not confirm success. A specialist "
        "may follow up."
    ),
}


class EnglishLanguagePack:
    language_code = "en-US"

    def normalize_slots(self, text: str, hints: SlotHints) -> NormalizedSlots:
        slots = NormalizedSlots()
        lowered = text.lower()
        if hints.expect_amount or "gel" in lowered or "pay" in lowered:
            amount = _extract_amount(text)
            if amount:
                slots.amount = amount
                slots.currency = "GEL"
                slots.raw_fragments["amount"] = amount
        if hints.expect_date or any(m in lowered for m in _MONTHS) or _has_relative_date(lowered):
            parsed = _extract_date(text, as_of=hints.as_of)
            if parsed:
                slots.date = parsed
                slots.raw_fragments["date"] = parsed
        return slots

    def classify_confirmation(self, text: str) -> ConfirmationResult:
        t = text.strip().lower()
        ambiguous = {"probably", "maybe", "i think so", "i should be able to", "perhaps"}
        if any(a in t for a in ambiguous) or not t:
            return ConfirmationResult("ambiguous", 0.4)
        # Word boundaries so "not my debt" is not treated as "no".
        if re.search(r"\b(yes|yeah|yep|correct)\b", t) or "that's right" in t or "that is right" in t:
            return ConfirmationResult("yes", 0.95)
        if re.search(r"\b(nope|incorrect)\b", t) or re.search(r"\bno\b", t) or "not right" in t:
            return ConfirmationResult("no", 0.95)
        return ConfirmationResult("ambiguous", 0.5)

    def render_template(self, key: str, values: dict[str, object]) -> str:
        template = EN_TEMPLATES.get(key, "")
        try:
            return template.format(**values)
        except KeyError:
            return template


class GeorgianLanguagePackStub:
    """Scaffold only — not production-ready Georgian content."""

    language_code = "ka-GE"

    def normalize_slots(self, text: str, hints: SlotHints) -> NormalizedSlots:
        # Fall back to English numeric/date extraction for scaffolding.
        return EnglishLanguagePack().normalize_slots(text, hints)

    def classify_confirmation(self, text: str) -> ConfirmationResult:
        t = text.strip().lower()
        if t in {"კი", "diakh", "yes"}:
            return ConfirmationResult("yes", 0.7)
        if t in {"არა", "ara", "no"}:
            return ConfirmationResult("no", 0.7)
        return ConfirmationResult("ambiguous", 0.3)

    def render_template(self, key: str, values: dict[str, object]) -> str:
        return f"[ka-GE stub:{key}] " + EnglishLanguagePack().render_template(key, values)


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _extract_amount(text: str) -> str | None:
    cleaned = text.replace(",", "")
    # Prefer explicit money mentions over day numbers in dates.
    money = re.search(
        r"(\d+(?:\.\d{1,2})?)\s*(?:gel|lari|\$)",
        cleaned,
        re.I,
    )
    if money:
        try:
            value = Decimal(money.group(1))
        except InvalidOperation:
            return None
        if value > 0:
            return f"{value.quantize(Decimal('0.01'))}"
    # "pay 275.40 on ..." — number not immediately before a month name
    for match in re.finditer(r"(\d+(?:\.\d{1,2})?)", cleaned):
        after = cleaned[match.end() : match.end() + 24].lower()
        if re.match(
            r"(?:st|nd|rd|th)?(?:\s+of)?\s+"
            r"(?:january|february|march|april|may|june|july|august|september|"
            r"october|november|december)\b",
            after,
        ):
            continue
        try:
            value = Decimal(match.group(1))
        except InvalidOperation:
            continue
        if value > 0:
            return f"{value.quantize(Decimal('0.01'))}"
    return None


_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _has_relative_date(text: str) -> bool:
    return bool(
        re.search(
            r"\b(today|tonight|tomorrow|yesterday|next week|day after tomorrow|"
            r"in\s+\d+\s+days?|next\s+"
            r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            text,
            re.I,
        )
    )


def _extract_relative_date(text: str, as_of: date) -> date | None:
    t = text.lower()
    if re.search(r"\bday after tomorrow\b", t):
        return as_of + timedelta(days=2)
    if re.search(r"\btomorrow\b", t):
        return as_of + timedelta(days=1)
    if re.search(r"\b(today|tonight)\b", t):
        return as_of
    if re.search(r"\byesterday\b", t):
        return as_of - timedelta(days=1)
    days = re.search(r"\bin\s+(\d+)\s+days?\b", t)
    if days:
        return as_of + timedelta(days=int(days.group(1)))
    if re.search(r"\bnext week\b", t):
        return as_of + timedelta(days=7)
    weekday = re.search(
        r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        t,
    )
    if weekday:
        target = _WEEKDAYS[weekday.group(2)]
        delta = (target - as_of.weekday()) % 7
        if weekday.group(1) and delta == 0:
            delta = 7
        return as_of + timedelta(days=delta)
    return None


def _extract_date(text: str, as_of: date | None = None) -> str | None:
    ref = as_of or date.today()
    relative = _extract_relative_date(text, ref)
    if relative:
        return relative.isoformat()
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    iso = re.search(r"(20\d{2})-(\d{2})-(\d{2})", cleaned)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    # e.g. 28 August, 28th of August, August 28, 2026
    m = re.search(
        r"(\d{1,2})(?:\s+of)?\s+(january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s*(,?\s*(20\d{2}))?",
        cleaned,
        re.I,
    )
    if m:
        day = int(m.group(1))
        month = _MONTHS[m.group(2).lower()]
        year = int(m.group(4)) if m.group(4) else ref.year
        return date(year, month, day).isoformat()
    m2 = re.search(
        r"(january|february|march|april|may|june|july|august|september|"
        r"october|november|december)(?:\s+the)?\s+(\d{1,2})(,?\s*(20\d{2}))?",
        cleaned,
        re.I,
    )
    if m2:
        month = _MONTHS[m2.group(1).lower()]
        day = int(m2.group(2))
        year = int(m2.group(4)) if m2.group(4) else ref.year
        return date(year, month, day).isoformat()
    return None


def get_language_pack(language_code: str) -> LanguagePack:
    if language_code.lower().startswith("ka"):
        return GeorgianLanguagePackStub()
    return EnglishLanguagePack()
