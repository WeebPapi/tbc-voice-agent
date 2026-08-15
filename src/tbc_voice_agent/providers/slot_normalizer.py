"""LLM-assisted speech slot normalizer (no policy authority).

Deterministic extractors run first. The LLM may fill gaps with schema-validated
slots that are grounded in the transcript. Policy and the safety overlay remain
authoritative (ADR-009, ADR-013).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, field_validator

from tbc_voice_agent.content import parse_georgian_cardinal
from tbc_voice_agent.domain import Intent
from tbc_voice_agent.policy.safety import detect_safety_intent

NORMALIZER_PROMPT_VERSION = "slot-norm-v1"

SLOT_NORMALIZER_SYSTEM_PROMPT = """You normalize soft-collections speech into structured slots.
You do not decide outcomes, approve identity, invent offers, or judge PTP eligibility.

Extract ONLY what is grounded in the customer transcript. Never invent amounts,
dates, birth dates, ID digits, or offer IDs. Never invent allow/deny decisions.
Leave response_text empty. Leave fields null when unsure.

Return JSON with keys:
  intent (optional string), amount (decimal string like "200.00"), currency ("GEL"),
  date (YYYY-MM-DD), birth_day_month (MM-DD), id_last4 (4 chars),
  confirmation ("yes"|"no"|"ambiguous"), confidence (0-1).

Georgian examples (illustrative only — extract from the actual transcript):
  "ორას ლარს" / "ორასლარს" / "ორასი ლარის" → amount "200.00", currency "GEL"
  "ხუთმეტე მარტი" / "თხუთმეტი მარტი" → birth_day_month "03-15"
  "17 აგვისტოს" with as_of year → date using that year
Permitted facts below are for grounding checks only, not values to copy unless
the transcript clearly refers to the full balance.
"""


class NormalizedTurnSlots(BaseModel):
    """Schema-validated normalizer output for EN and KA."""

    intent: str | None = None
    amount: str | None = None
    currency: str | None = None
    date: str | None = None
    birth_day_month: str | None = None
    id_last4: str | None = None
    confirmation: str | None = None
    confidence: float = 0.5

    @field_validator("amount")
    @classmethod
    def _amount_format(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal string") from exc
        if parsed <= 0:
            raise ValueError("amount must be positive")
        return f"{parsed.quantize(Decimal('0.01'))}"

    @field_validator("date")
    @classmethod
    def _date_iso(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        date.fromisoformat(str(value))
        return str(value)

    @field_validator("birth_day_month")
    @classmethod
    def _mm_dd(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        m = re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", str(value))
        if not m:
            raise ValueError("birth_day_month must be MM-DD")
        return str(value)

    @field_validator("id_last4")
    @classmethod
    def _last4(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        s = str(value).strip()
        if len(s) != 4:
            raise ValueError("id_last4 must be 4 characters")
        return s

    @field_validator("confirmation")
    @classmethod
    def _confirmation(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        v = str(value).lower().strip()
        if v not in {"yes", "no", "ambiguous"}:
            raise ValueError("confirmation must be yes|no|ambiguous")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return str(value).upper()


_WEAK_INTENTS = frozenset(
    {
        Intent.UNKNOWN,
        Intent.LOW_CONFIDENCE,
        Intent.GREETING,
        Intent.REMINDER_ACK,
    }
)

_BALANCE_PHRASES_EN = (
    "the balance",
    "full amount",
    "all of it",
    "pay that",
)
_BALANCE_PHRASES_KA = (
    "ბალანსი",
    "სრულად",
    "მთლიანად",
    "ბოლომდე",
    "დავფარო",
)

_KA_MONTH_CUES = (
    "იანვარი",
    "თებერვალი",
    "მარტი",
    "აპრილი",
    "მაისი",
    "ივნისი",
    "ივლისი",
    "აგვისტო",
    "სექტემბერი",
    "ოქტომბერი",
    "ნოემბერი",
    "დეკემბერი",
)
_KA_RELATIVE = ("დღეს", "ხვალ", "გუშინ", "მომავალ კვირას")
_EN_MONTH_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
    re.I,
)
_EN_RELATIVE_RE = re.compile(
    r"\b(today|tonight|tomorrow|yesterday|next week|day after tomorrow)\b",
    re.I,
)
_KA_CURRENCY_RE = re.compile(r"(?:ლარი|ლარს|ლარის|ლარით|lari|gel|გელ)", re.I)
_MM_DD_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def is_valid_birth_day_month(value: str | None) -> bool:
    if not value:
        return False
    return bool(_MM_DD_RE.fullmatch(str(value).strip()))


def is_valid_id_last4(value: str | None) -> bool:
    if not value:
        return False
    return len(str(value).strip()) == 4


def _has_date_cue(text: str) -> bool:
    if any(m in text for m in _KA_MONTH_CUES) or any(r in text for r in _KA_RELATIVE):
        return True
    if _EN_MONTH_RE.search(text) or _EN_RELATIVE_RE.search(text):
        return True
    if re.search(r"20\d{2}-\d{2}-\d{2}", text):
        return True
    return False


def _looks_like_messy_ka_money(text: str) -> bool:
    """Digit-less Georgian money speech that regex may miss."""
    if re.search(r"\d", text):
        return False
    if not _KA_CURRENCY_RE.search(text):
        return False
    return bool(re.search(r"[ა-ჰ]", text))


def _looks_like_messy_ka_date(text: str) -> bool:
    if re.search(r"\d", text):
        return False
    return any(m in text for m in _KA_MONTH_CUES)


def _balance_phrase(text: str) -> bool:
    lowered = text.lower()
    if any(p in lowered for p in _BALANCE_PHRASES_EN):
        return True
    return any(p in text for p in _BALANCE_PHRASES_KA)


def needs_normalization(
    *,
    text: str,
    state: str,
    slots: dict[str, Any] | None,
    confidence: float,
    expect_identity_dob: bool = False,
    expect_identity_last4: bool = False,
    birth_day_month: str | None = None,
    id_last4: str | None = None,
    pending_ptp: dict[str, Any] | None = None,
) -> bool:
    """True when the LLM normalizer should attempt to fill gaps."""
    if detect_safety_intent(text):
        return False

    if expect_identity_dob and not is_valid_birth_day_month(birth_day_month):
        return True
    if expect_identity_last4 and not is_valid_id_last4(id_last4):
        return True

    if confidence < 0.55:
        return True

    slots = slots or {}
    pending = pending_ptp or {}
    amount = slots.get("amount") or pending.get("amount")
    pay_date = slots.get("date") or pending.get("date")

    if state in {"discussing_options", "confirming_ptp", "reminder"}:
        # Completing a partial PTP: missing the follow-up piece.
        if pending.get("date") and not slots.get("amount") and not amount:
            if _looks_like_messy_ka_money(text) or _KA_CURRENCY_RE.search(text) or re.search(
                r"\d", text
            ):
                return True
        if pending.get("amount") and not slots.get("date") and not pay_date:
            if _has_date_cue(text):
                return True
        if not slots.get("amount") and _looks_like_messy_ka_money(text):
            return True
        if not slots.get("date") and _looks_like_messy_ka_date(text):
            return True
        # Pay-like utterance with incomplete slots
        pay_like = (
            "pay" in text.lower()
            or "გადავიხდი" in text
            or "გადახდა" in text
            or "დავპირდები" in text
            or _KA_CURRENCY_RE.search(text)
        )
        if pay_like and (not slots.get("amount") or not slots.get("date")):
            # Only if there is a cue that something is present but unparsed
            if (
                _looks_like_messy_ka_money(text)
                or _looks_like_messy_ka_date(text)
                or (_has_date_cue(text) and not slots.get("date"))
                or (_KA_CURRENCY_RE.search(text) and not slots.get("amount"))
            ):
                return True

    return False


def _amount_grounded_in_digits(text: str, amount: str) -> bool:
    cleaned = text.replace(",", "")
    try:
        target = Decimal(amount).quantize(Decimal("0.01"))
    except InvalidOperation:
        return False
    for match in re.finditer(r"(\d+(?:\.\d{1,2})?)", cleaned):
        try:
            found = Decimal(match.group(1)).quantize(Decimal("0.01"))
        except InvalidOperation:
            continue
        if found == target:
            return True
        # Whole lari without cents in speech
        if found == target.to_integral_value() and target == found.quantize(Decimal("0.01")):
            return True
        if int(found) == int(target) and target == Decimal(int(found)).quantize(
            Decimal("0.01")
        ):
            return True
    return False


def _amount_grounded_in_ka_cardinal(text: str, amount: str) -> bool:
    try:
        target = int(Decimal(amount))
    except (InvalidOperation, ValueError):
        return False
    # Prefer spans before currency words
    for m in re.finditer(
        r"((?:[ა-ჰᲐ-Ჰ]+\s*){1,6}?)\s*(?:ლარი|ლარს|ლარის|ლარით|lari|gel|გელ)",
        text,
        re.I,
    ):
        tokens = [t for t in m.group(1).split() if t]
        for n in range(1, min(4, len(tokens)) + 1):
            candidate = " ".join(tokens[-n:])
            parsed = parse_georgian_cardinal(candidate)
            if parsed == target:
                return True
    # Also try full cardinal parse of money-ish substrings
    parsed = parse_georgian_cardinal(text)
    if parsed == target:
        return True
    return False


def _date_grounded_in_transcript(text: str, pay_date: str) -> bool:
    """Require the calendar day to appear as digits or Georgian speech near a date cue."""
    from tbc_voice_agent.content import _ka_fold_mtavruli, georgian_calendar_day_in_text

    text = _ka_fold_mtavruli(text)
    try:
        d = date.fromisoformat(str(pay_date))
    except ValueError:
        return False
    if str(pay_date) in text:
        return True
    # Relative dates: only if the cue is present
    if any(r in text for r in _KA_RELATIVE) or _EN_RELATIVE_RE.search(text):
        return _has_date_cue(text)
    if not _has_date_cue(text):
        return False
    return georgian_calendar_day_in_text(text, d.day)


def ground_slots(
    text: str,
    slots: dict[str, Any] | NormalizedTurnSlots,
    permitted_facts: dict[str, Any],
    *,
    allow_identity: bool = False,
) -> dict[str, Any]:
    """Fail closed: drop values not grounded in the transcript / permitted facts."""
    if isinstance(slots, NormalizedTurnSlots):
        raw = slots.model_dump(exclude_none=True)
    else:
        raw = dict(slots or {})

    out: dict[str, Any] = {}

    # Never pass through policy-like fields
    raw.pop("offer_id", None)
    raw.pop("response_text", None)
    raw.pop("allowed", None)
    raw.pop("denied", None)

    amount = raw.get("amount")
    if amount:
        amount_s = str(amount)
        try:
            amount_s = f"{Decimal(amount_s).quantize(Decimal('0.01'))}"
        except InvalidOperation:
            amount_s = None
        if amount_s:
            ok = False
            if _amount_grounded_in_digits(text, amount_s):
                ok = True
            elif _amount_grounded_in_ka_cardinal(text, amount_s):
                ok = True
            elif _balance_phrase(text):
                balance = permitted_facts.get("balance_amount")
                if balance and str(balance) == amount_s:
                    ok = True
            if ok:
                out["amount"] = amount_s
                out["currency"] = raw.get("currency") or permitted_facts.get("currency") or "GEL"

    pay_date = raw.get("date")
    if pay_date:
        try:
            date.fromisoformat(str(pay_date))
        except ValueError:
            pay_date = None
        if pay_date and _date_grounded_in_transcript(text, str(pay_date)):
            out["date"] = str(pay_date)

    if allow_identity:
        bdm = raw.get("birth_day_month")
        if bdm and is_valid_birth_day_month(str(bdm)):
            # Must have a month cue or MM-DD digits in transcript
            if any(m in text for m in _KA_MONTH_CUES) or _EN_MONTH_RE.search(text) or re.search(
                r"\d{1,2}", text
            ):
                out["birth_day_month"] = str(bdm)
        last4 = raw.get("id_last4")
        if last4 and is_valid_id_last4(str(last4)):
            # Digits or spoken digit words should appear
            if re.search(r"\d", text) or any(
                w in text
                for w in (
                    "ნული",
                    "ერთი",
                    "ორი",
                    "სამი",
                    "ოთხი",
                    "ხუთი",
                    "ექვსი",
                    "შვიდი",
                    "რვა",
                    "ცხრა",
                    "zero",
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                )
            ):
                out["id_last4"] = str(last4)

    conf = raw.get("confirmation")
    if conf in {"yes", "no", "ambiguous"}:
        out["confirmation"] = conf

    intent = raw.get("intent")
    if intent:
        out["intent"] = intent

    if "confidence" in raw:
        try:
            out["confidence"] = float(raw["confidence"])
        except (TypeError, ValueError):
            out["confidence"] = 0.5

    return out


def merge_normalized_slots(
    existing: dict[str, Any] | None,
    normalized: dict[str, Any],
    *,
    current_intent: Intent | None = None,
) -> tuple[dict[str, Any], Intent | None]:
    """Deterministic slots win; LLM fills empty fields only."""
    slots = dict(existing or {})
    filled_keys: list[str] = []
    for key in ("amount", "currency", "date", "birth_day_month", "id_last4", "confirmation"):
        if not slots.get(key) and normalized.get(key):
            slots[key] = normalized[key]
            filled_keys.append(key)

    new_intent: Intent | None = None
    intent_raw = normalized.get("intent")
    if intent_raw and (current_intent is None or current_intent in _WEAK_INTENTS):
        try:
            candidate = Intent(str(intent_raw))
        except ValueError:
            candidate = None
        if candidate and candidate not in {
            Intent.HARDSHIP,
            Intent.DISPUTE,
            Intent.STOP_CONTACT,
        }:
            # Safety intents must come from overlay, not normalizer inventing them
            # (overlay still wins later). Allow commercial intents.
            new_intent = candidate
        elif candidate in {Intent.HARDSHIP, Intent.DISPUTE, Intent.STOP_CONTACT}:
            # Allow labeling if transcript will be re-checked by overlay anyway
            new_intent = candidate

    return slots, new_intent


def slots_changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return keys that were filled or repaired (non-PII comparison for PTP)."""
    changed: list[str] = []
    for key in ("amount", "currency", "date", "confirmation"):
        if before.get(key) != after.get(key) and after.get(key) is not None:
            changed.append(key)
    for key in ("birth_day_month", "id_last4"):
        if before.get(key) != after.get(key) and after.get(key) is not None:
            changed.append(key)
    return changed


def parse_normalized_payload(raw: dict[str, Any]) -> NormalizedTurnSlots | None:
    """Validate raw LLM JSON; return None on schema failure."""
    try:
        return NormalizedTurnSlots.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None
