"""Session-scoped Georgian voice runtime: STT stream, turns, TTS with barge-in."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from tbc_voice_agent.config import Settings
from tbc_voice_agent.domain import ConversationState, Disposition, new_id, utc_now
from tbc_voice_agent.orchestrator import Orchestrator
from tbc_voice_agent.orchestrator.store import EventStore, SessionRecord
from tbc_voice_agent.providers.factory import build_elevenlabs_stt, build_elevenlabs_tts
from tbc_voice_agent.providers.stt.base import TranscriptEvent
from tbc_voice_agent.providers.stt.elevenlabs import ElevenLabsScribeRealtime
from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS

logger = logging.getLogger(__name__)


class VoiceSessionRuntime:
    """One STT stream + TTS generation state per conversation session."""

    def __init__(
        self,
        *,
        session_id: str,
        settings: Settings,
        orchestrator: Orchestrator,
        store: EventStore,
        stt: ElevenLabsScribeRealtime | None = None,
        tts: ElevenLabsTTS | None = None,
        send_json: Any = None,
        send_bytes: Any = None,
    ) -> None:
        self.session_id = session_id
        self.settings = settings
        self.orchestrator = orchestrator
        self.store = store
        self.stt = stt
        self.tts = tts
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._stt_task: asyncio.Task[None] | None = None
        self._active_generation_id: str | None = None
        self._active_turn_id: str | None = None
        self._interrupted = False
        self._closed = False
        self._configured = stt is not None and tts is not None
        self._seen_finals: set[str] = set()
        self._listening = False
        self._greeting_spoken = False
        self._stt_drop_notified = False
        # Ignore near-silence so open-mic noise does not cancel TTS.
        self._barge_in_rms_threshold = 0.02

    @classmethod
    def create(
        cls,
        session_id: str,
        settings: Settings,
        orchestrator: Orchestrator,
        store: EventStore,
        *,
        send_json: Any = None,
        send_bytes: Any = None,
        stt: ElevenLabsScribeRealtime | None = None,
        tts: ElevenLabsTTS | None = None,
        websocket_factory: Any = None,
        http_client: Any = None,
    ) -> VoiceSessionRuntime:
        if stt is None:
            stt = build_elevenlabs_stt(settings, websocket_factory=websocket_factory)
        if tts is None:
            tts = build_elevenlabs_tts(settings, http_client=http_client)
        return cls(
            session_id=session_id,
            settings=settings,
            orchestrator=orchestrator,
            store=store,
            stt=stt,
            tts=tts,
            send_json=send_json,
            send_bytes=send_bytes,
        )

    def _session(self) -> SessionRecord:
        session = self.store.get(self.session_id)
        if not session:
            raise KeyError(self.session_id)
        return session

    async def _emit_ws(self, payload: dict[str, Any]) -> None:
        if self._send_json:
            await self._send_json(payload)

    async def _emit_audio(self, chunk: bytes) -> None:
        if self._send_bytes and chunk:
            await self._send_bytes(chunk)

    def _append(
        self,
        session: SessionRecord,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        redaction: dict[str, Any] | None = None,
    ) -> None:
        self.store.append_event(session, event_type, source, payload, redaction=redaction)

    async def start_stt(self) -> None:
        session = self._session()
        if not self._configured or self.stt is None:
            await self._emit_ws(
                {
                    "type": "error",
                    "code": "provider_not_configured",
                    "message": (
                        "ElevenLabs voice is not configured. Set ELEVENLABS_API_KEY and "
                        "ELEVENLABS_VOICE_ID, or use text mode on /ka."
                    ),
                }
            )
            return
        await self.stt.start(
            correlation_id=session.correlation_id,
            on_event=self._on_stt_event,
        )
        self._append(
            session,
            "stt.connection_started",
            "stt",
            {
                "provider": self.stt.provider_name,
                "model": self.stt.model_id,
                "language": self.stt.language_code,
                "audio_format": self.stt.audio_format,
                "sample_rate": self.stt.sample_rate,
            },
        )
        self._stt_task = None

    @staticmethod
    def _pcm_rms(chunk: bytes) -> float:
        if len(chunk) < 4:
            return 0.0
        import array

        samples = array.array("h")
        samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
        if not samples:
            return 0.0
        acc = 0.0
        for s in samples:
            v = s / 32768.0
            acc += v * v
        return (acc / len(samples)) ** 0.5

    async def set_listening(self, active: bool) -> None:
        self._listening = active
        if active and self.stt is not None and not self._closed:
            self._stt_drop_notified = False
            if not self.stt.is_connected:
                try:
                    await self.stt.start(
                        correlation_id=self._session().correlation_id,
                        on_event=self._on_stt_event,
                    )
                except Exception as exc:  # noqa: BLE001
                    await self._note_stt_drop(str(exc), "reconnect")

    async def commit_audio(self) -> None:
        """Finalize STT segment when the operator stops the mic."""
        if not self._configured or self.stt is None or self._closed:
            return
        if not self.stt.is_connected:
            await self._note_stt_drop("STT stream is not connected", "commit")
            return
        try:
            await self.stt.commit()
        except Exception as exc:  # noqa: BLE001
            await self._note_stt_drop(str(exc), "commit")

    async def speak_approved(self, text: str, *, turn_id: str | None = None) -> None:
        """Speak already-approved assistant text (e.g. greeting) without a new turn."""
        if not text.strip() or not self._configured or self.tts is None:
            return
        tid = turn_id or new_id("turn")
        self._active_turn_id = tid
        self._interrupted = False
        await self._speak(text, tid)

    async def push_audio(self, chunk: bytes) -> None:
        if not self._configured or self.stt is None or self._closed:
            return
        # Customer speech during playback → barge-in only when energy is real speech
        if (
            self._active_generation_id
            and self._listening
            and self._pcm_rms(chunk) >= self._barge_in_rms_threshold
        ):
            await self.interrupt(reason="barge_in")
        # Never feed STT while TTS is in flight (bleed overflows Scribe).
        if self._active_generation_id or not self._listening:
            return
        if not self.stt.is_connected:
            return
        try:
            await self.stt.push_audio(chunk)
        except Exception as exc:  # noqa: BLE001
            await self._note_stt_drop(str(exc), "send")

    async def interrupt(self, reason: str = "user_interrupt") -> None:
        self._interrupted = True
        session = self._session()
        session.interrupted = True
        gen = self._active_generation_id
        if gen and self.tts is not None:
            await self.tts.cancel(gen)
            self._append(
                session,
                "tts.cancelled",
                "tts",
                {
                    "provider": self.tts.provider_name,
                    "generation_id": gen,
                    "reason": reason,
                },
            )
        self._active_generation_id = None
        self._active_turn_id = None
        await self._emit_ws({"type": "assistant.audio_end", "interrupted": True})

    async def handle_text_turn(self, text: str, client_turn_id: str | None = None) -> None:
        turn_id = client_turn_id or new_id("turn")
        await self._process_final_transcript(text, turn_id, confidence=1.0)

    async def aclose(self) -> None:
        self._closed = True
        if self._active_generation_id and self.tts is not None:
            await self.tts.cancel(self._active_generation_id)
        if self.stt is not None:
            session = self.store.get(self.session_id)
            await self.stt.aclose()
            if session:
                self._append(
                    session,
                    "stt.connection_closed",
                    "stt",
                    {"provider": self.stt.provider_name},
                )
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
            try:
                await self._stt_task
            except asyncio.CancelledError:
                pass

    async def _drain_stt_events(self) -> None:
        if self.stt is None:
            return
        try:
            async for event in self.stt.events():
                await self._on_stt_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await self._handle_stt_failure(str(exc), "recv")

    async def _on_stt_event(self, event: TranscriptEvent) -> None:
        if self._closed:
            return
        session = self._session()
        if event.kind == "partial":
            self._append(
                session,
                "stt.partial_received",
                "stt",
                {
                    "provider": self.stt.provider_name if self.stt else "unknown",
                    **(event.metadata or {}),
                },
            )
            await self._emit_ws(
                {
                    "type": "transcript.partial",
                    "text": event.text,
                    "confidence": event.confidence,
                }
            )
            return

        # Final / committed
        if event.metadata.get("error_category"):
            cat = str(event.metadata.get("error_category") or "failed")
            if cat == "timeout":
                await self._handle_stt_failure(cat, cat)
            elif cat in {"send", "commit", "reconnect", "connection", "queue_overflow"}:
                await self._note_stt_drop(cat, cat)
            else:
                await self._handle_stt_failure(cat, cat)
            return

        text = (event.text or "").strip()
        turn_id = event.client_turn_id or new_id("turn")
        # Deduplicate identical finals in a short window
        dedupe_key = f"{turn_id}:{text}"
        if dedupe_key in self._seen_finals:
            return
        self._seen_finals.add(dedupe_key)

        self._append(
            session,
            "stt.final_received",
            "stt",
            {
                "provider": self.stt.provider_name if self.stt else "unknown",
                "confidence": event.confidence,
                **(event.metadata or {}),
            },
        )
        await self._emit_ws(
            {
                "type": "transcript.final",
                "text": text,
                "confidence": event.confidence,
                "client_turn_id": turn_id,
            }
        )
        if not text:
            return
        await self._process_final_transcript(text, turn_id, confidence=event.confidence)

    async def _process_final_transcript(
        self, text: str, client_turn_id: str, confidence: float
    ) -> None:
        session = self._session()
        # Cancel any in-flight response belonging to a previous turn
        if self._active_generation_id:
            await self.interrupt(reason="new_final_transcript")

        self._interrupted = False
        session.interrupted = False
        self._active_turn_id = client_turn_id

        try:
            result = await self.orchestrator.handle_text_turn(
                self.session_id, text, client_turn_id
            )
        except Exception:  # noqa: BLE001
            logger.exception("turn failed")
            await self._emit_ws(
                {
                    "type": "error",
                    "code": "turn_failed",
                    "message": "Could not process the turn.",
                }
            )
            return

        # If interrupted while processing, drop the response
        if self._interrupted or session.interrupted:
            return
        if self._active_turn_id != client_turn_id:
            return

        await self._emit_ws(
            {
                "type": "assistant.text",
                "text": result.assistant_text,
                "state": result.state.value,
            }
        )
        for event in result.events:
            if event.type.startswith("policy") or event.type.startswith("state"):
                await self._emit_ws({"type": event.type, "payload": event.payload})

        if result.assistant_text and self.tts is not None and self._configured:
            await self._speak(result.assistant_text, client_turn_id)

        if result.disposition:
            await self._emit_ws(
                {
                    "type": "session.ended",
                    "disposition": result.disposition.value,
                }
            )

    async def _speak(self, text: str, turn_id: str) -> None:
        assert self.tts is not None
        session = self._session()
        generation_id = new_id("tts")
        self._active_generation_id = generation_id
        started = asyncio.get_event_loop().time()
        first_audio_at: float | None = None
        self._append(
            session,
            "tts.started",
            "tts",
            {
                "provider": self.tts.provider_name,
                "model": self.tts.model_id,
                "output_format": self.tts.output_format,
                "generation_id": generation_id,
                "turn_id": turn_id,
            },
        )
        from tbc_voice_agent.content import prepare_spoken_text

        spoken = prepare_spoken_text(text, session.language)
        try:
            async for chunk in self.tts.stream_synthesize(
                spoken, session.language, generation_id=generation_id
            ):
                if (
                    self._interrupted
                    or self.tts.is_cancelled(generation_id)
                    or self._active_generation_id != generation_id
                    or self._active_turn_id != turn_id
                ):
                    # Late chunks from cancelled generation — discard
                    break
                if first_audio_at is None:
                    first_audio_at = asyncio.get_event_loop().time()
                    self._append(
                        session,
                        "tts.first_audio",
                        "tts",
                        {
                            "provider": self.tts.provider_name,
                            "generation_id": generation_id,
                            "time_to_first_audio_ms": int((first_audio_at - started) * 1000),
                        },
                    )
                b64 = base64.b64encode(chunk).decode("ascii")
                await self._emit_ws(
                    {
                        "type": "assistant.audio_chunk",
                        "format": self.tts.output_format,
                        "data": b64,
                        "generation_id": generation_id,
                    }
                )
                # Prefer JSON base64 for the browser console; avoid dual binary+JSON playback.
            else:
                # Completed without break
                if not self.tts.is_cancelled(generation_id) and not self._interrupted:
                    duration_ms = int((asyncio.get_event_loop().time() - started) * 1000)
                    self._append(
                        session,
                        "tts.completed",
                        "tts",
                        {
                            "provider": self.tts.provider_name,
                            "generation_id": generation_id,
                            "duration_ms": duration_ms,
                        },
                    )
                    await self._emit_ws(
                        {
                            "type": "assistant.audio_end",
                            "generation_id": generation_id,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            if self.tts.is_cancelled(generation_id):
                return
            safe = ElevenLabsTTS._safe_error(exc)
            self._append(
                session,
                "tts.failed",
                "tts",
                {
                    "provider": self.tts.provider_name,
                    "generation_id": generation_id,
                    "error_category": "tts_failed",
                    "message": safe,
                },
            )
            await self._emit_ws(
                {
                    "type": "error",
                    "code": "tts_failed",
                    "message": (
                        "Speech playback failed; the text transcript remains available."
                    ),
                }
            )
            await self._emit_ws(
                {"type": "assistant.audio_end", "generation_id": generation_id, "failed": True}
            )
        finally:
            if self._active_generation_id == generation_id:
                self._active_generation_id = None

    async def _note_stt_drop(self, message: str, category: str) -> None:
        """Scribe WS often dies during TTS idle; reconnect on next Start mic."""
        if self.stt is not None:
            self.stt.mark_disconnected()
        if self._stt_drop_notified:
            return
        self._stt_drop_notified = True
        session = self._session()
        self._append(
            session,
            "stt.failed",
            "stt",
            {
                "provider": self.stt.provider_name if self.stt else "unknown",
                "error_category": category,
            },
        )
        await self._emit_ws(
            {
                "type": "error",
                "code": "stt_reconnecting",
                "message": (
                    "Speech recognition dropped. Press Start mic again to continue."
                ),
            }
        )

    async def _handle_stt_failure(self, message: str, category: str) -> None:
        session = self._session()
        self._append(
            session,
            "stt.failed",
            "stt",
            {
                "provider": self.stt.provider_name if self.stt else "unknown",
                "error_category": category,
            },
        )
        # Soft timeout after commit: ask to retry; do not kill the session.
        if category == "timeout":
            await self._emit_ws(
                {
                    "type": "error",
                    "code": "stt_timeout",
                    "message": (
                        "Did not catch that clearly. Hold the mic, speak, then Stop mic "
                        "to send."
                    ),
                }
            )
            return

        await self._emit_ws(
            {
                "type": "error",
                "code": "stt_failed",
                "message": "Speech recognition failed. Closing safely without disclosure.",
            }
        )
        # Before identity: technical failure, neutral close
        if session.identity.status.value == "unverified" or session.state in {
            ConversationState.CREATED,
            ConversationState.VERIFYING_IDENTITY,
        }:
            pack_key = "technical_failure_close"
            from tbc_voice_agent.content import get_language_pack

            pack = get_language_pack(session.language)
            text = pack.render_template(pack_key, {"display_name": session.display_name})
            session.state = ConversationState.TERMINATED
            session.disposition = Disposition.TECHNICAL_FAILURE
            session.ended_at = session.ended_at or utc_now()
            self._append(
                session,
                "assistant.response_approved",
                "orchestrator",
                {"text": text, "template": pack_key},
            )
            self._append(
                session,
                "session.ended",
                "orchestrator",
                {
                    "disposition": Disposition.TECHNICAL_FAILURE.value,
                    "write_back_status": session.write_back_status,
                },
            )
            await self._emit_ws(
                {
                    "type": "assistant.text",
                    "text": text,
                    "state": session.state.value,
                }
            )
            await self._emit_ws(
                {
                    "type": "session.ended",
                    "disposition": Disposition.TECHNICAL_FAILURE.value,
                }
            )


# Registry so session A never receives events for session B
_runtimes: dict[str, VoiceSessionRuntime] = {}


def get_runtime(session_id: str) -> VoiceSessionRuntime | None:
    return _runtimes.get(session_id)


def register_runtime(runtime: VoiceSessionRuntime) -> None:
    _runtimes[runtime.session_id] = runtime


async def unregister_runtime(session_id: str) -> None:
    runtime = _runtimes.pop(session_id, None)
    if runtime:
        await runtime.aclose()
