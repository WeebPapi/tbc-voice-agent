"""Language pack protocol and English content."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
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
    "ptp_need_amount": (
        "What amount in GEL do you intend to pay on {date}?"
    ),
    "ptp_need_date": (
        "What date do you intend to pay {amount} {currency}?"
    ),
    "ptp_out_of_range": (
        "That date or amount is outside the allowed window. Please choose a date from {as_of} "
        "through {maximum_date}, and an amount of at least {minimum_amount} GEL."
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


def _ka_fold_mtavruli(text: str) -> str:
    """Map Georgian Mtavruli capitals (U+1C90–U+1CBF) to Mkhedruli for matching."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x1C90 <= code <= 0x1CBF:
            out.append(chr(code - 0x1C90 + 0x10D0))
        else:
            out.append(ch)
    return "".join(out)


class GeorgianLanguagePack:
    """Synthetic ka-GE content for the /ka POC — not Bank-approved production copy."""

    language_code = "ka-GE"

    def normalize_slots(self, text: str, hints: SlotHints) -> NormalizedSlots:
        text = _ka_fold_mtavruli(text)
        slots = NormalizedSlots()
        # Prefer Georgian month / ლარი extraction; fall back to English numerics.
        if hints.expect_amount or "ლარი" in text or "gel" in text.lower() or "გელ" in text.lower():
            amount = _extract_amount_ka(text) or _extract_amount(text)
            if amount:
                # Drop calendar-day false positives (e.g. "13 აგვისტოს" without ლარი).
                parsed_date = _extract_date_ka(text, as_of=hints.as_of)
                if parsed_date and not _extract_amount_ka(text):
                    try:
                        day = int(parsed_date.split("-")[2])
                        if Decimal(amount) == Decimal(day):
                            amount = None
                    except (InvalidOperation, IndexError, ValueError):
                        pass
            if amount:
                slots.amount = amount
                slots.currency = "GEL"
                slots.raw_fragments["amount"] = amount
        if hints.expect_date or _has_ka_date(text) or any(m in text.lower() for m in _MONTHS):
            parsed = _extract_date_ka(text, as_of=hints.as_of) or _extract_date(text, as_of=hints.as_of)
            if parsed:
                slots.date = parsed
                slots.raw_fragments["date"] = parsed
        return slots

    def classify_confirmation(self, text: str) -> ConfirmationResult:
        t = text.strip().lower()
        raw = text.strip()
        yes_words = {"კი", "დიახ", "diakh", "ki", "yes", "yeah", "yep"}
        no_words = {"არა", "ara", "no", "nope"}
        ambiguous = {"შესაძლოა", "ალბათ", "maybe", "probably", "იაზრება"}
        if raw in yes_words or t in yes_words:
            return ConfirmationResult("yes", 0.95)
        if raw in no_words or t in no_words:
            return ConfirmationResult("no", 0.95)
        tokens = [
            tok.casefold().strip(".,!?;:")
            for tok in re.split(r"\s+", raw)
            if tok.strip(".,!?;:")
        ]
        if tokens and tokens[0] in yes_words:
            return ConfirmationResult("yes", 0.95)
        if tokens and tokens[0] in no_words:
            return ConfirmationResult("no", 0.95)
        if any(a in raw or a in t for a in ambiguous) or not t:
            return ConfirmationResult("ambiguous", 0.4)
        if "სწორია" in raw or "that's right" in t or "that is right" in t:
            return ConfirmationResult("yes", 0.9)
        return ConfirmationResult("ambiguous", 0.5)

    def render_template(self, key: str, values: dict[str, object]) -> str:
        template = KA_TEMPLATES.get(key, "")
        if not template:
            return EnglishLanguagePack().render_template(key, values)
        try:
            return template.format(**values)
        except KeyError:
            return template


KA_TEMPLATES: dict[str, str] = {
    "greeting_neutral": (
        "გამარჯობა, ეს არის TBC დემო ასისტენტი. შემიძლია ვისაუბრო {display_name}-თან?"
    ),
    "identity_confirm_name": (
        "გთხოვთ დაადასტუროთ, რომ ვსაუბრობ {display_name}-თან."
    ),
    "identity_question_birth_day_month": (
        "უსაფრთხოებისთვის გთხოვთ მითხრათ დაბადების დღე და თვე, მაგალითად 15 მარტი."
    ),
    "identity_question_customer_id_last4": (
        "გმადლობთ. გთხოვთ მითხრათ თქვენი კლიენტის ნომრის ბოლო ოთხი სიმბოლო."
    ),
    "identity_failed_retry": (
        "ვერ დავადასტურე ეს მონაცემები. კიდევ ერთხელ ვცადოთ. "
        "გთხოვთ დაადასტუროთ დაბადების დღე და თვე."
    ),
    "identity_failed_close": (
        "ვერ მოხერხდა თქვენი იდენტობის დადასტურება, ამიტომ ვასრულებ ზარს. ნახვამდის."
    ),
    "wrong_party_close": (
        "გმადლობთ რომ შემატყობინეთ. ახლა ვასრულებ ზარს. ნახვამდის."
    ),
    "reminder_verified": (
        "გმადლობთ დადასტურებისთვის. ჩვენს ჩანაწერებში ჩანს ვადაგადაცილებული ბალანსი "
        "{balance_amount} {currency}, ვადა {due_date}. როგორ გსურთ გაგრძელება?"
    ),
    "ptp_readback": (
        "დასადასტურებლად: გეგმავთ გადაიხადოთ {amount} {currency} {date}-ში. სწორია?"
    ),
    "ptp_captured": (
        "გმადლობთ. ჩავწერე თქვენი დაპირება გადაიხადოთ {amount} {currency} {date}-ში."
    ),
    "ptp_ambiguous": (
        "დაპირების ჩასაწერად მჭირდება მკაფიო კი. თანხა და თარიღი სწორია?"
    ),
    "ptp_need_amount": (
        "რა თანხის გადახდა გსურთ {date}-ში ლარში?"
    ),
    "ptp_need_date": (
        "რომელ თარიღს გეგმავთ {amount} {currency}-ის გადახდას?"
    ),
    "ptp_out_of_range": (
        "ეს თარიღი ან თანხა დაშვებულ ფარგლებს გარეთაა. გთხოვთ აირჩიოთ თარიღი {as_of}-დან "
        "{maximum_date}-მდე და თანხა მინიმუმ {minimum_amount} ლარი."
    ),
    "payment_plan_offer": (
        "თქვენ გაქვთ უფლება ამ გეგმაზე: {offer_text}. გსურთ მიღება?"
    ),
    "payment_plan_accepted": "გმადლობთ. ჩავწერე გადახდის გეგმის მიღება.",
    "unsupported_discount": (
        "ვერ შევცვლი პირობებს ან ფასდაკლებას. შემიძლია შემოგთავაზოთ დამტკიცებული გეგმა "
        "ან გადაგაერთოთ სპეციალისტთან."
    ),
    "payment_link_acknowledged": (
        "მოვითხოვე გადახდის ბმულის გაგზავნა ბანკის უსაფრთხო არხით."
    ),
    "already_paid_ack": (
        "გმადლობთ რომ გვითხარით, რომ ეს უკვე გადახდილია. "
        "ჩავწერ შენიშვნას შესამოწმებლად. ამ ზარზე ვერ დავადასტურებ დასრულებას."
    ),
    "dispute_transfer": (
        "მესმის, რომ სადავოა. ვწყვეტ საინკასო განხილვას და გადაგაერთებთ სპეციალისტთან."
    ),
    "hardship_transfer": (
        "ბოდიში, რომ ამ სირთულეს გადიხართ. აღარ გავაგრძელებ გადახდის განხილვას. "
        "გადაგაერთებთ სპეციალისტთან, რომელიც დაგეხმარებათ."
    ),
    "stop_contact_close": (
        "მესმის. ჩავწერ თხოვნას კონტაქტის შეწყვეტის შესახებ და ვასრულებ ზარს. ნახვამდის."
    ),
    "technical_failure_close": (
        "ამჟამად უსაფრთხოდ ვერ გავაგრძელებ. ვასრულებ ზარს ანგარიშის დეტალების განხილვის გარეშე. "
        "ნახვამდის."
    ),
    "low_confidence_clarify": (
        "კარგად ვერ გავიგე. გთხოვთ გაიმეოროთ თანხა და თარიღი."
    ),
    "prompt_injection_ignore": (
        "ჯერ კიდევ მჭირდება იდენტობის დადასტურება. შემიძლია ვისაუბრო {display_name}-თან?"
    ),
    "discuss_options_prompt": (
        "შეგიძლიათ დაპირდეთ გადახდის თარიღს, მოითხოვოთ გადახდის გეგმა, გადახდის ბმული, "
        "ან დაასრულოთ ზარი. როგორ გსურთ გაგრძელება?"
    ),
    "customer_ended": "გასაგებია. ნახვამდის.",
    "outcome_failed": (
        "ვერ შევინახე შედეგი უსაფრთხოდ, ამიტომ წარმატებას ვერ დავადასტურებ. სპეციალისტი "
        "შეიძლება დაგიკავშირდეთ."
    ),
}


# Latin demo names → common Georgian STT / transliteration spellings (POC only).
_NAME_SCRIPT_VARIANTS: dict[str, tuple[str, ...]] = {
    "alex": ("alex", "ალექს", "ალექსი"),
    "morgan": ("morgan", "მორგან", "მორგენ", "მორგანი", "მორგენი"),
    "jordan": ("jordan", "ჯორდან", "ჯორდანი"),
    "lee": ("lee", "ლი"),
    "casey": ("casey", "კეისი", "ქეისი"),
    "brown": ("brown", "ბრაუნ", "ბრაუნი"),
    "taylor": ("taylor", "ტეილორ", "თეილორ", "ტეილორი"),
    "smith": ("smith", "სმით", "სმიტი", "სმითი"),
    "reed": ("reed", "რიდ", "რიდი"),
    "jamie": ("jamie", "ჯეიმი"),
    "wilson": ("wilson", "უილსონ", "ვილსონ", "უილსონი"),
    "riley": ("riley", "რაილი"),
    "davis": ("davis", "დევის", "დეივის", "დევისი"),
}


def customer_name_mentioned(text: str, display_name: str) -> bool:
    """True when the spoken text includes the synthetic customer name (any script)."""
    name = (display_name or "").strip()
    if not name or not text.strip():
        return False
    hay = text.casefold()
    if name.casefold() in hay:
        return True
    parts = [p for p in re.split(r"\s+", name) if p]
    if not parts:
        return False
    for part in parts:
        key = part.casefold()
        variants = _NAME_SCRIPT_VARIANTS.get(key, (key,))
        if not any(variant.casefold() in hay for variant in variants):
            return False
    return True


_KA_MONTHS = {
    "იანვარი": 1,
    "თებერვალი": 2,
    "მარტი": 3,
    "აპრილი": 4,
    "მაისი": 5,
    "ივნისი": 6,
    "ივლისი": 7,
    "აგვისტო": 8,
    "სექტემბერი": 9,
    "ოქტომბერი": 10,
    "ნოემბერი": 11,
    "დეკემბერი": 12,
}


def _has_ka_date(text: str) -> bool:
    text = _ka_fold_mtavruli(text)
    return any(m in text for m in _KA_MONTHS) or any(
        p in text for p in ("დღეს", "ხვალ", "გუშინ", "მომავალ კვირას")
    )


_KA_CURRENCY = r"(?:ლარი|ლარს|ლარის|ლარით|lari|gel|გელ)"


def _normalize_ka_money_text(text: str) -> str:
    """Split STT compounds like ორასლარს → ორას ლარს; normalize currency case forms."""
    # Number stem glued to lari/lars (common STT): ორასლარს, ასლარი, …
    out = re.sub(
        rf"([ა-ჰᲐ-Ჰ]+?)({_KA_CURRENCY})",
        r"\1 \2",
        text,
        flags=re.I,
    )
    return out


def _extract_amount_ka(text: str) -> str | None:
    cleaned = _normalize_ka_money_text(_ka_fold_mtavruli(text).replace(",", ""))
    money = re.search(
        rf"(\d+(?:\.\d{{1,2}})?)\s*{_KA_CURRENCY}",
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
    spoken = _extract_spoken_gel_amount(cleaned)
    if spoken:
        return spoken
    return None


def _ka_strip_case_ending(token: str) -> str:
    """Normalize common Georgian case endings (e.g. ორასის → ორასი)."""
    t = token.strip(".,!?;:\"'«»")
    if len(t) < 3:
        return t
    # Genitive -ის / -ს on cardinals ending in ი
    if t.endswith("ის") and len(t) > 3:
        return t[:-1]  # ორასის → ორასი, ასის → ასი
    if t.endswith("ს") and t[:-1].endswith("ი"):
        return t[:-1]
    return t


@lru_cache(maxsize=1)
def _ka_cardinal_lookup() -> dict[str, int]:
    """Map spoken Georgian cardinals (and genitive forms) to integers 0–9999."""
    table: dict[str, int] = {"ნული": 0}
    for n in range(1, 10000):
        spoken = georgian_cardinal(n)
        table[spoken] = n
        table[spoken.replace(" ", "")] = n
        parts = spoken.split()
        if len(parts) == 1:
            table[parts[0]] = n
            # Stem without final ი — STT often returns "ორას" before ლარს
            if parts[0].endswith("ი") and len(parts[0]) > 2:
                table[parts[0][:-1]] = n
    # Genitive / colloquial variants often returned by STT
    extras = {
        "ორასის": 200,
        "ასის": 100,
        "სამასის": 300,
        "ოთხასის": 400,
        "ხუთასის": 500,
        "ათასის": 1000,
        "ორას": 200,
        "ას": 100,
        "სამას": 300,
    }
    table.update(extras)
    return table


def parse_georgian_cardinal(text: str) -> int | None:
    """Parse a Georgian number word phrase into an int, or None."""
    raw = text.strip()
    if not raw:
        return None
    # Drop currency / filler words; keep the numeral phrase.
    cleaned = re.sub(
        rf"({_KA_CURRENCY}|თეთრი|და)",
        " ",
        raw,
        flags=re.I,
    )
    cleaned = re.sub(r"[^\w\sა-ჰᲐ-Ჰ]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    lookup = _ka_cardinal_lookup()
    if cleaned in lookup:
        return lookup[cleaned]
    compact = cleaned.replace(" ", "")
    if compact in lookup:
        return lookup[compact]
    tokens = [_ka_strip_case_ending(tok) for tok in cleaned.split() if tok]
    if not tokens:
        return None
    joined = " ".join(tokens)
    if joined in lookup:
        return lookup[joined]
    if "".join(tokens) in lookup:
        return lookup["".join(tokens)]
    if len(tokens) == 1 and tokens[0] in lookup:
        return lookup[tokens[0]]
    # Stem without ი on single tokens (ორას → 200)
    if len(tokens) == 1 and tokens[0] + "ი" in lookup:
        return lookup[tokens[0] + "ი"]
    # "ორას ოცდახუთი" style: greedy left-to-right
    total = 0
    i = 0
    while i < len(tokens):
        matched = False
        for span in range(min(4, len(tokens) - i), 0, -1):
            chunk = " ".join(tokens[i : i + span])
            if chunk in lookup:
                total += lookup[chunk]
                i += span
                matched = True
                break
            chunk2 = "".join(tokens[i : i + span])
            if chunk2 in lookup:
                total += lookup[chunk2]
                i += span
                matched = True
                break
            if span == 1 and tokens[i] + "ი" in lookup:
                total += lookup[tokens[i] + "ი"]
                i += 1
                matched = True
                break
        if not matched:
            return None
    return total if total > 0 else None


def _extract_spoken_gel_amount(text: str) -> str | None:
    """Extract GEL amount from Georgian number words (ორასი ლარი, ორას ლარს, …)."""
    text = _normalize_ka_money_text(text)
    has_currency = bool(re.search(_KA_CURRENCY, text, re.I))
    if not has_currency and any(month in text for month in _KA_MONTHS):
        return None

    candidates: list[str] = []
    for m in re.finditer(
        rf"((?:[ა-ჰᲐ-Ჰ]+\s*){{1,6}}?)\s*{_KA_CURRENCY}",
        text,
        re.I,
    ):
        tokens = [t for t in m.group(1).split() if t]
        for n in range(1, min(4, len(tokens)) + 1):
            candidates.append(" ".join(tokens[-n:]))
    stripped = re.sub(
        rf"(გადავიხდი|გადახდა|დავპირდები|{_KA_CURRENCY}|თეთრი)",
        " ",
        text,
        flags=re.I,
    )
    stripped = re.sub(r"\s+", " ", stripped).strip(" .,!?;:")
    if stripped:
        candidates.append(stripped)
        toks = stripped.split()
        for n in range(1, min(4, len(toks)) + 1):
            candidates.append(" ".join(toks[-n:]))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        value = parse_georgian_cardinal(candidate)
        if value is not None and value > 0:
            return f"{Decimal(value).quantize(Decimal('0.01'))}"
    return None


def _extract_date_ka(text: str, as_of: date | None = None) -> str | None:
    text = _ka_fold_mtavruli(text)
    ref = as_of or date.today()
    if "ხვალ" in text:
        return (ref + timedelta(days=1)).isoformat()
    if "დღეს" in text:
        return ref.isoformat()
    if "გუშინ" in text:
        return (ref - timedelta(days=1)).isoformat()
    if "მომავალ კვირას" in text:
        return (ref + timedelta(days=7)).isoformat()
    for name, month in _KA_MONTHS.items():
        m = re.search(rf"(\d{{1,2}})\s+{name}", text)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                return date(ref.year, month, day).isoformat()
        m2 = re.search(rf"{name}\s+(\d{{1,2}})", text)
        if m2:
            day = int(m2.group(1))
            if 1 <= day <= 31:
                return date(ref.year, month, day).isoformat()
        # Spoken day before month: "ოცი აგვისტო", "ოც აგვისტოს", "თხუთმეტი მარტი"
        spoken = _extract_spoken_day_before_month(text, name)
        if spoken is not None:
            try:
                return date(ref.year, month, spoken).isoformat()
            except ValueError:
                pass
        # Genitive month + spoken day: "მარტის მეთხუთმეტე"
        spoken_after = _extract_spoken_day_after_month(text, name)
        if spoken_after is not None:
            try:
                return date(ref.year, month, spoken_after).isoformat()
            except ValueError:
                pass
    return None


_KA_DAY_ORDINAL_ALIASES: dict[str, int] = {
    # Common STT / colloquial day-of-month forms (thin aliases, not a money dictionary)
    "მეერთე": 1,
    "მეორე": 2,
    "მესამე": 3,
    "მეოთხე": 4,
    "მეხუთე": 5,
    "მეექვსე": 6,
    "მეშვიდე": 7,
    "მერვე": 8,
    "მეცხრე": 9,
    "მეათე": 10,
    "მეთერთმეტე": 11,
    "მეთორმეტე": 12,
    "მეცამეტე": 13,
    "მეთოთხმეტე": 14,
    "მეთხუთმეტე": 15,
    "მეექვსმეტე": 16,
    "მეჩვიდმეტე": 17,
    "მეთვრამეტე": 18,
    "მეცხრამეტე": 19,
    "მეოცე": 20,
    "ხუთმეტე": 15,
    "ხუთმეტი": 15,
}


def _parse_day_of_month_phrase(phrase: str) -> int | None:
    """Parse a Georgian day-of-month word/phrase into 1–31."""
    raw = phrase.strip().strip(".,!?;:\"'«»")
    if not raw:
        return None
    if raw in _KA_DAY_ORDINAL_ALIASES:
        return _KA_DAY_ORDINAL_ALIASES[raw]
    # Strip leading მე- ordinal marker: მეთხუთმეტე → თხუთმეტე-ish handled via aliases
    cleaned = re.sub(r"^(მე)?", "", raw)
    if cleaned in _KA_DAY_ORDINAL_ALIASES:
        return _KA_DAY_ORDINAL_ALIASES[cleaned]
    value = parse_georgian_cardinal(raw)
    if value is not None and 1 <= value <= 31:
        return value
    # Stem without final ი: ოც → 20
    if raw.endswith("ი") and len(raw) > 2:
        value = parse_georgian_cardinal(raw[:-1])
        if value is not None and 1 <= value <= 31:
            return value
    if not raw.endswith("ი"):
        value = parse_georgian_cardinal(raw + "ი")
        if value is not None and 1 <= value <= 31:
            return value
    return None


def _extract_spoken_day_before_month(text: str, month_name: str) -> int | None:
    idx = text.find(month_name)
    if idx < 0:
        return None
    before = text[:idx].strip()
    # Drop pay/currency fillers; keep the trailing numeral phrase.
    before = re.sub(
        rf"(გადავიხდი|გადახდა|დავპირდები|დავფარო|ბოლომდე|მთლიანად|{_KA_CURRENCY}|და)",
        " ",
        before,
        flags=re.I,
    )
    before = re.sub(r"\d+", " ", before)  # prefer spoken day over stray digits (e.g. "45 ოც")
    before = re.sub(r"[^\w\sა-ჰᲐ-Ჰ]", " ", before, flags=re.UNICODE)
    before = re.sub(r"\s+", " ", before).strip()
    if not before:
        return None
    tokens = before.split()
    # Try last 1–3 tokens immediately before the month
    for n in range(1, min(3, len(tokens)) + 1):
        phrase = " ".join(tokens[-n:])
        day = _parse_day_of_month_phrase(phrase)
        if day is not None:
            return day
    return _parse_day_of_month_phrase(tokens[-1])


def _extract_spoken_day_after_month(text: str, month_name: str) -> int | None:
    """Handle 'მარტის მეთხუთმეტე' / 'მარტის თხუთმეტი'."""
    m = re.search(
        rf"{re.escape(month_name)}(?:ის)?\s+([ა-ჰᲐ-Ჰ]+)",
        text,
    )
    if not m:
        return None
    return _parse_day_of_month_phrase(m.group(1))


def georgian_calendar_day_in_text(text: str, day: int) -> bool:
    """True when the calendar day appears as digits or spoken Georgian near a month."""
    text = _ka_fold_mtavruli(text)
    if re.search(rf"(?<!\d){day}(?!\d)", text):
        return True
    for name in _KA_MONTHS:
        if name not in text:
            continue
        if _extract_spoken_day_before_month(text, name) == day:
            return True
        if _extract_spoken_day_after_month(text, name) == day:
            return True
    for token in re.findall(r"[ა-ჰᲐ-Ჰ]+", text):
        parsed = _parse_day_of_month_phrase(_ka_fold_mtavruli(token))
        if parsed == day:
            return True
    return False


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
        r"(\d+(?:\.\d{1,2})?)\s*(?:gel|lari|\$|ლარი|გელ)",
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
    ka_months = "|".join(re.escape(m) for m in _KA_MONTHS)
    # "pay 275.40 on ..." — number not immediately before a month name (EN or KA)
    for match in re.finditer(r"(\d+(?:\.\d{1,2})?)", cleaned):
        after = cleaned[match.end() : match.end() + 24]
        after_lower = after.lower()
        if re.match(
            r"(?:st|nd|rd|th)?(?:\s+of)?\s+"
            r"(?:january|february|march|april|may|june|july|august|september|"
            r"october|november|december)\b",
            after_lower,
        ):
            continue
        if ka_months and re.match(rf"\s+(?:{ka_months})", after):
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


_KA_ONES = (
    "",
    "ერთი",
    "ორი",
    "სამი",
    "ოთხი",
    "ხუთი",
    "ექვსი",
    "შვიდი",
    "რვა",
    "ცხრა",
)
_KA_TEENS = {
    10: "ათი",
    11: "თერთმეტი",
    12: "თორმეტი",
    13: "ცამეტი",
    14: "თოთხმეტი",
    15: "თხუთმეტი",
    16: "თექვსმეტი",
    17: "ჩვიდმეტი",
    18: "თვრამეტი",
    19: "ცხრამეტი",
}
_KA_TWENTY_STEMS = {1: "ოც", 2: "ორმოც", 3: "სამოც", 4: "ოთხმოც"}
_KA_HUNDREDS = {
    1: "ასი",
    2: "ორასი",
    3: "სამასი",
    4: "ოთხასი",
    5: "ხუთასი",
    6: "ექვსასი",
    7: "შვიდასი",
    8: "რვაასი",
    9: "ცხრაასი",
}
_KA_MONTH_NAMES = (
    "",
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


def _ka_under_100(n: int) -> str:
    if n <= 0:
        return ""
    if n < 10:
        return _KA_ONES[n]
    if n < 20:
        return _KA_TEENS[n]
    scores, rest = divmod(n, 20)
    stem = _KA_TWENTY_STEMS[scores]
    if rest == 0:
        return f"{stem}ი"
    if rest < 10:
        return f"{stem}და{_KA_ONES[rest]}"
    if rest == 10:
        return f"{stem}დაათი"
    return f"{stem}და{_KA_TEENS[rest]}"


def _ka_under_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if hundreds == 0:
        return _ka_under_100(n)
    head = _KA_HUNDREDS[hundreds]
    if rest == 0:
        return head
    stem = head[:-1] if head.endswith("ი") else head
    return f"{stem} {_ka_under_100(rest)}"


def georgian_cardinal(n: int) -> str:
    """Spoken Georgian cardinal for demo amounts/dates (0–9999)."""
    if n < 0:
        return georgian_cardinal(-n)
    if n == 0:
        return "ნული"
    thousands, rest = divmod(n, 1000)
    parts: list[str] = []
    if thousands:
        if thousands == 1:
            parts.append("ათასი" if rest == 0 else "ათას")
        else:
            head = _ka_under_1000(thousands)
            parts.append(f"{head} ათასი" if rest == 0 else f"{head} ათას")
    if rest:
        parts.append(_ka_under_1000(rest))
    return " ".join(parts)


def _spoken_gel_amount(whole: str, frac: str) -> str:
    lari = georgian_cardinal(int(whole or "0"))
    tetri = int((frac + "00")[:2]) if frac else 0
    if tetri:
        return f"{lari} ლარი და {georgian_cardinal(tetri)} თეთრი"
    return f"{lari} ლარი"


def _spoken_iso_date(year: int, month: int, day: int) -> str:
    month_name = _KA_MONTH_NAMES[month] if 1 <= month <= 12 else str(month)
    return f"{georgian_cardinal(day)} {month_name}, {georgian_cardinal(year)}"


def prepare_spoken_text(text: str, language: str) -> str:
    """Expand digits/dates for TTS. UI transcript stays numeric."""
    if not language.lower().startswith("ka"):
        return text
    spoken = text
    spoken = re.sub(
        r"\b(20\d{2})-(\d{2})-(\d{2})\b",
        lambda m: _spoken_iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3))),
        spoken,
    )
    spoken = re.sub(
        r"\b(\d+)\.(\d{1,2})\s*(?:GEL|gel|Gel|ლარი)?\b",
        lambda m: _spoken_gel_amount(m.group(1), m.group(2)),
        spoken,
    )
    spoken = re.sub(r"\bGEL\b", "ლარი", spoken)
    months = "|".join(_KA_MONTH_NAMES[1:])
    spoken = re.sub(
        rf"\b(\d{{1,2}})\s+({months})\b",
        lambda m: f"{georgian_cardinal(int(m.group(1)))} {m.group(2)}",
        spoken,
    )
    return spoken


def get_language_pack(language_code: str) -> LanguagePack:
    if language_code.lower().startswith("ka"):
        return GeorgianLanguagePack()
    return EnglishLanguagePack()


# Backward-compatible alias for older tests/imports.
GeorgianLanguagePackStub = GeorgianLanguagePack
