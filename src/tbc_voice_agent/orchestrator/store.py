"""SQLite event and session store."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tbc_voice_agent.domain import (
    ConversationState,
    Disposition,
    EventEnvelope,
    IdentityState,
    IdentityStatus,
    utc_now,
)


@dataclass
class SessionRecord:
    session_id: str
    correlation_id: str
    campaign_id: str
    customer_ref: str
    language: str
    transport: str
    state: ConversationState = ConversationState.CREATED
    disposition: Disposition | None = None
    identity: IdentityState = field(default_factory=IdentityState)
    context: dict[str, Any] | None = None
    offers: list[dict[str, Any]] = field(default_factory=list)
    pending_ptp: dict[str, Any] | None = None
    pending_dob: str | None = None
    pending_offer_id: str | None = None
    display_name: str = ""
    write_back_status: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    seen_turn_ids: set[str] = field(default_factory=set)
    sequence: int = 0
    events: list[EventEnvelope] = field(default_factory=list)
    interrupted: bool = False


class EventStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    data TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(self, session: SessionRecord) -> SessionRecord:
        with self._lock:
            self._sessions[session.session_id] = session
            self._persist_session(session)
            return session

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def append_event(
        self,
        session: SessionRecord,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        redaction: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        session.sequence += 1
        event = EventEnvelope(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            sequence=session.sequence,
            type=event_type,
            source=source,
            payload=payload,
            redaction=redaction
            or {"contains_pii": False, "fields_removed": []},
        )
        session.events.append(event)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events(event_id, session_id, sequence, data) VALUES (?, ?, ?, ?)",
                (event.event_id, session.session_id, event.sequence, event.model_dump_json()),
            )
            conn.commit()
        self._persist_session(session)
        return event

    def events_after(self, session_id: str, after_sequence: int = 0) -> list[EventEnvelope]:
        session = self.get(session_id)
        if not session:
            return []
        return [e for e in session.events if e.sequence > after_sequence]

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()
            with self._conn() as conn:
                conn.execute("DELETE FROM sessions")
                conn.execute("DELETE FROM events")
                conn.commit()

    def _persist_session(self, session: SessionRecord) -> None:
        data = {
            "session_id": session.session_id,
            "correlation_id": session.correlation_id,
            "campaign_id": session.campaign_id,
            "customer_ref": session.customer_ref,
            "language": session.language,
            "transport": session.transport,
            "state": session.state.value,
            "disposition": session.disposition.value if session.disposition else None,
            "identity_status": session.identity.status.value,
            "write_back_status": session.write_back_status,
            "created_at": session.created_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id, data) VALUES (?, ?)",
                (session.session_id, json.dumps(data)),
            )
            conn.commit()
