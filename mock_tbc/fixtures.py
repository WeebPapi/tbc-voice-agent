"""Synthetic campaign/customer fixtures for mock TBC."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

CAMPAIGN = {
    "campaign_id": "campaign-en-001",
    "name": "English Soft Collections Demo",
    "language": "en-US",
    "calling_window": "09:00-18:00",
    "policy_version": "poc-v1",
    "identity_question_set": "idq-poc-v1",
    "content_version": "en-poc-v1",
    "customer_refs": [
        "cust-001",
        "cust-002",
        "cust-003",
        "cust-004",
        "cust-005",
        "cust-006",
        "cust-007",
    ],
}

CUSTOMERS: dict[str, dict] = {
    "cust-001": {
        "customer_ref": "cust-001",
        "display_name": "Alex Morgan",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "03-15",
            "id_last4": "0001",
        },
        "account_ref": "demo-account-001",
        "balance": {"amount": "275.40", "currency": "GEL"},
        "due_date": "2026-08-10",
        "days_past_due": 4,
        "ptp_policy": {
            "minimum_amount": "25.00",
            "maximum_date": "2026-09-13",
        },
        "offer_refs": ["offer-001"],
        "context_version": "ctx-3",
        "path": "happy_path_ptp",
    },
    "cust-002": {
        "customer_ref": "cust-002",
        "display_name": "Jordan Lee",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "07-22",
            "id_last4": "0002",
        },
        "account_ref": "demo-account-002",
        "balance": {"amount": "480.00", "currency": "GEL"},
        "due_date": "2026-08-05",
        "days_past_due": 9,
        "ptp_policy": {
            "minimum_amount": "40.00",
            "maximum_date": "2026-09-20",
        },
        "offer_refs": ["offer-002", "offer-002-expired"],
        "context_version": "ctx-2",
        "path": "payment_plan",
    },
    "cust-003": {
        "customer_ref": "cust-003",
        "display_name": "Casey Brown",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "11-02",
            "id_last4": "0003",
        },
        "account_ref": "demo-account-003",
        "balance": {"amount": "150.00", "currency": "GEL"},
        "due_date": "2026-08-01",
        "days_past_due": 13,
        "ptp_policy": {
            "minimum_amount": "20.00",
            "maximum_date": "2026-09-10",
        },
        "offer_refs": [],
        "context_version": "ctx-1",
        "path": "already_paid",
    },
    "cust-004": {
        "customer_ref": "cust-004",
        "display_name": "Taylor Smith",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "01-09",
            "id_last4": "0004",
        },
        "account_ref": "demo-account-004",
        "balance": {"amount": "320.75", "currency": "GEL"},
        "due_date": "2026-07-28",
        "days_past_due": 17,
        "ptp_policy": {
            "minimum_amount": "25.00",
            "maximum_date": "2026-09-15",
        },
        "offer_refs": ["offer-004"],
        "context_version": "ctx-4",
        "path": "hardship",
    },
    "cust-005": {
        "customer_ref": "cust-005",
        "display_name": "Morgan Reed",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "05-30",
            "id_last4": "0005",
        },
        "account_ref": "demo-account-005",
        "balance": {"amount": "99.99", "currency": "GEL"},
        "due_date": "2026-08-08",
        "days_past_due": 6,
        "ptp_policy": {
            "minimum_amount": "10.00",
            "maximum_date": "2026-09-08",
        },
        "offer_refs": [],
        "context_version": "ctx-5",
        "path": "stop_contact",
    },
    "cust-006": {
        "customer_ref": "cust-006",
        "display_name": "Jamie Wilson",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "09-18",
            "id_last4": "0006",
        },
        "account_ref": "demo-account-006",
        "balance": {"amount": "210.00", "currency": "GEL"},
        "due_date": "2026-08-12",
        "days_past_due": 2,
        "ptp_policy": {
            "minimum_amount": "25.00",
            "maximum_date": "2026-09-12",
        },
        "offer_refs": [],
        "context_version": "ctx-6",
        "path": "wrong_party",
    },
    "cust-007": {
        "customer_ref": "cust-007",
        "display_name": "Riley Davis",
        "preferred_language": "en-US",
        "contact_allowed": True,
        "campaign_id": "campaign-en-001",
        "policy_version": "poc-v1",
        "identity": {
            "birth_day_month": "12-04",
            "id_last4": "0007",
        },
        "account_ref": "demo-account-007",
        "balance": {"amount": "500.00", "currency": "GEL"},
        "due_date": "2026-07-20",
        "days_past_due": 25,
        "ptp_policy": {
            "minimum_amount": "50.00",
            "maximum_date": "2026-09-01",
        },
        "offer_refs": [],
        "context_version": "ctx-7",
        "path": "technical_failure",
        "force_context_failure": True,
    },
}

OFFERS: dict[str, dict] = {
    "offer-001": {
        "offer_id": "offer-001",
        "display_text": "Two payments of 137.70 GEL due within 30 days",
        "installments": 2,
        "installment_amount": {"amount": "137.70", "currency": "GEL"},
        "valid_until": "2026-09-13",
        "expired": False,
    },
    "offer-002": {
        "offer_id": "offer-002",
        "display_text": "Three payments of 160.00 GEL due within 45 days",
        "installments": 3,
        "installment_amount": {"amount": "160.00", "currency": "GEL"},
        "valid_until": "2026-09-30",
        "expired": False,
    },
    "offer-002-expired": {
        "offer_id": "offer-002-expired",
        "display_text": "Expired two-payment plan of 240.00 GEL",
        "installments": 2,
        "installment_amount": {"amount": "240.00", "currency": "GEL"},
        "valid_until": "2026-07-01",
        "expired": True,
    },
    "offer-004": {
        "offer_id": "offer-004",
        "display_text": "Two payments of 160.38 GEL due within 30 days",
        "installments": 2,
        "installment_amount": {"amount": "160.38", "currency": "GEL"},
        "valid_until": "2026-09-15",
        "expired": False,
    },
}


def fresh_customers() -> dict[str, dict]:
    return deepcopy(CUSTOMERS)


def fresh_offers() -> dict[str, dict]:
    return deepcopy(OFFERS)


def fresh_campaign() -> dict:
    return deepcopy(CAMPAIGN)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)
