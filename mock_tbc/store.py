"""In-memory / SQLite-backed store for mock TBC."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from mock_tbc.fixtures import fresh_campaign, fresh_customers, fresh_offers


def _now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class VerificationToken:
    token: str
    session_id: str
    customer_ref: str
    evidence_ref: str
    expires_at: datetime


@dataclass
class MockStore:
    db_path: str
    customers: dict[str, dict] = field(default_factory=fresh_customers)
    offers: dict[str, dict] = field(default_factory=fresh_offers)
    campaign: dict = field(default_factory=fresh_campaign)
    tokens: dict[str, VerificationToken] = field(default_factory=dict)
    outcomes: dict[str, dict] = field(default_factory=dict)  # key -> record
    payment_links: list[dict] = field(default_factory=list)
    transfers: list[dict] = field(default_factory=list)
    suppressions: list[dict] = field(default_factory=list)
    failures: dict[str, Any] = field(default_factory=dict)
    outcome_fail_once_used: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def reset(self) -> None:
        with self._lock:
            self.customers = fresh_customers()
            self.offers = fresh_offers()
            self.campaign = fresh_campaign()
            self.tokens.clear()
            self.outcomes.clear()
            self.payment_links.clear()
            self.transfers.clear()
            self.suppressions.clear()
            self.failures.clear()
            self.outcome_fail_once_used.clear()
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            with self._conn() as conn:
                conn.execute("DELETE FROM kv")
                conn.commit()

    def set_failure(self, mode: str, scope: str = "global", session_id: str | None = None) -> None:
        key = f"{scope}:{session_id or '*'}"
        with self._lock:
            self.failures[key] = mode

    def clear_failures(self) -> None:
        with self._lock:
            self.failures.clear()
            self.outcome_fail_once_used.clear()

    def active_failure(self, session_id: str | None = None) -> str | None:
        with self._lock:
            if session_id:
                specific = self.failures.get(f"session:{session_id}")
                if specific:
                    return specific
            return self.failures.get("global:*")

    def create_token(self, session_id: str, customer_ref: str) -> VerificationToken:
        token = VerificationToken(
            token=_id("tok"),
            session_id=session_id,
            customer_ref=customer_ref,
            evidence_ref=_id("idv"),
            expires_at=_now() + timedelta(minutes=30),
        )
        with self._lock:
            self.tokens[token.token] = token
        return token

    def validate_token(
        self, token: str | None, session_id: str, customer_ref: str
    ) -> VerificationToken:
        if not token:
            raise PermissionError("VERIFICATION_REQUIRED")
        with self._lock:
            record = self.tokens.get(token)
        if record is None:
            raise PermissionError("INVALID_TOKEN")
        if record.expires_at < _now():
            raise PermissionError("TOKEN_EXPIRED")
        if record.session_id != session_id or record.customer_ref != customer_ref:
            raise PermissionError("TOKEN_MISMATCH")
        return record

    def store_outcome(self, idempotency_key: str, payload: dict) -> tuple[dict, bool]:
        with self._lock:
            existing = self.outcomes.get(idempotency_key)
            if existing is not None:
                comparable = {k: v for k, v in existing.items() if k not in {"outcome_id", "created_at"}}
                incoming = {k: v for k, v in payload.items() if k not in {"outcome_id", "created_at"}}
                if comparable != incoming:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return existing, False
            record = {
                **payload,
                "outcome_id": _id("out"),
                "created_at": _now().isoformat(),
            }
            self.outcomes[idempotency_key] = record
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)",
                    (f"outcome:{idempotency_key}", json.dumps(record)),
                )
                conn.commit()
            return record, True
