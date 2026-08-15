"""ElevenLabs Scribe v2 Realtime streaming STT adapter.

Uses documented WebSocket fields only:
  wss://api.elevenlabs.io/v1/speech-to-text/realtime
  message_type=input_audio_chunk / partial_transcript / committed_transcript

Push-to-talk uses commit_strategy=manual: audio streams while the mic is open,
then commit() finalizes the segment when the operator stops recording.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from tbc_voice_agent.providers.stt.base import TranscriptEvent

logger = logging.getLogger(__name__)

WebSocketFactory = Callable[..., Any]


class ElevenLabsScribeRealtime:
    """Session-scoped Scribe v2 Realtime connection."""

    provider_name = "ElevenLabsScribeRealtime"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "scribe_v2_realtime",
        language_code: str = "kat",
        audio_format: str = "pcm_16000",
        sample_rate: int = 16000,
        connect_timeout_seconds: float = 10.0,
        turn_timeout_seconds: float = 15.0,
        zero_retention: bool = False,
        websocket_factory: WebSocketFactory | None = None,
        base_url: str = "wss://api.elevenlabs.io",
        commit_strategy: str = "manual",
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs API key is required")
        self.api_key = api_key
        self.model_id = model_id
        self.language_code = language_code
        self.audio_format = audio_format
        self.sample_rate = sample_rate
        self.connect_timeout_seconds = connect_timeout_seconds
        self.turn_timeout_seconds = turn_timeout_seconds
        self.zero_retention = zero_retention
        self.commit_strategy = commit_strategy
        self._websocket_factory = websocket_factory
        self.base_url = base_url.rstrip("/")
        self._ws: Any = None
        self._recv_task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        self._on_event: Callable[[TranscriptEvent], Awaitable[None]] | None = None
        self._correlation_id: str = ""
        self._closed = False
        self._started = False
        self._first_audio_at: float | None = None
        self._first_partial_at: float | None = None
        self._first_final_at: float | None = None
        self._connect_started_at: float | None = None
        self._awaiting_final = False
        self._commit_deadline: float | None = None
        self._bytes_since_commit = 0

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._started and not self._closed

    def mark_disconnected(self) -> None:
        self._started = False
        self._ws = None

    def _build_url(self) -> str:
        params: dict[str, str] = {
            "model_id": self.model_id,
            "language_code": self.language_code,
            "audio_format": self.audio_format,
            "commit_strategy": self.commit_strategy,
        }
        if self.zero_retention:
            params["enable_logging"] = "false"
        return f"{self.base_url}/v1/speech-to-text/realtime?{urlencode(params)}"

    async def start(
        self,
        *,
        correlation_id: str,
        on_event: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
    ) -> None:
        if self._started and self._ws is not None:
            return
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        self._correlation_id = correlation_id
        self._on_event = on_event
        self._closed = False
        self._connect_started_at = asyncio.get_event_loop().time()
        url = self._build_url()
        headers = {"xi-api-key": self.api_key}

        factory = self._websocket_factory
        if factory is None:
            import websockets

            async def _default_connect(uri: str, **kwargs: Any) -> Any:
                return await websockets.connect(uri, **kwargs)

            factory = _default_connect

        try:
            self._ws = await asyncio.wait_for(
                factory(url, additional_headers=headers),
                timeout=self.connect_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._safe_error(exc, "connect")) from None

        self._started = True
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def push_audio(self, chunk: bytes) -> list[TranscriptEvent]:
        if not self._ws or self._closed:
            raise RuntimeError("STT stream is not connected")
        if not chunk:
            return []
        if self._first_audio_at is None:
            self._first_audio_at = asyncio.get_event_loop().time()
        self._bytes_since_commit += len(chunk)
        payload = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(chunk).decode("ascii"),
            "commit": False,
            "sample_rate": self.sample_rate,
        }
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._safe_error(exc, "send")) from None
        return []

    async def commit(self) -> None:
        """Finalize the current audio segment (manual commit strategy)."""
        if not self._ws or self._closed:
            raise RuntimeError("STT stream is not connected")
        if self._bytes_since_commit == 0:
            # Nothing spoken — do not hang waiting for a final.
            return
        payload = {
            "message_type": "input_audio_chunk",
            "audio_base_64": "",
            "commit": True,
            "sample_rate": self.sample_rate,
        }
        self._awaiting_final = True
        self._commit_deadline = (
            asyncio.get_event_loop().time() + self.turn_timeout_seconds
        )
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:  # noqa: BLE001
            self._awaiting_final = False
            self._commit_deadline = None
            raise RuntimeError(self._safe_error(exc, "commit")) from None
        self._bytes_since_commit = 0

    async def aclose(self) -> None:
        self._closed = True
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        await self._queue.put(None)
        self._started = False

    async def events(self) -> AsyncIterator[TranscriptEvent]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    def timing_metadata(self) -> dict[str, Any]:
        now = asyncio.get_event_loop().time()
        meta: dict[str, Any] = {
            "provider": self.provider_name,
            "model": self.model_id,
            "language": self.language_code,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
        }
        if self._connect_started_at and self._first_partial_at:
            meta["time_to_first_transcript_ms"] = int(
                (self._first_partial_at - self._connect_started_at) * 1000
            )
        if self._first_audio_at and self._first_final_at:
            meta["time_to_final_transcript_ms"] = int(
                (self._first_final_at - self._first_audio_at) * 1000
            )
        if self._connect_started_at:
            meta["connection_age_ms"] = int((now - self._connect_started_at) * 1000)
        return meta

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            while not self._closed:
                # Idle between turns must NOT kill the session. Only apply a
                # short wait while we are expecting a post-commit final.
                timeout = 1.0
                try:
                    raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
                except TimeoutError:
                    if (
                        self._awaiting_final
                        and self._commit_deadline is not None
                        and asyncio.get_event_loop().time() >= self._commit_deadline
                    ):
                        self._awaiting_final = False
                        self._commit_deadline = None
                        await self._emit(
                            TranscriptEvent(
                                kind="final",
                                text="",
                                confidence=0.0,
                                metadata={
                                    "error_category": "timeout",
                                    "provider": self.provider_name,
                                },
                            )
                        )
                    continue
                if isinstance(raw, bytes):
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("message_type") or data.get("type")
                if msg_type == "session_started":
                    continue
                if msg_type == "partial_transcript":
                    text = (data.get("text") or "").strip()
                    if self._first_partial_at is None:
                        self._first_partial_at = asyncio.get_event_loop().time()
                    await self._emit(
                        TranscriptEvent(
                            kind="partial",
                            text=text,
                            confidence=0.5,
                            language=self.language_code,
                            metadata=self.timing_metadata(),
                        )
                    )
                elif msg_type in {
                    "committed_transcript",
                    "committed_transcript_with_timestamps",
                    "final_transcript",
                    "final_transcript_with_timestamps",
                }:
                    text = (data.get("text") or "").strip()
                    if self._first_final_at is None:
                        self._first_final_at = asyncio.get_event_loop().time()
                    self._awaiting_final = False
                    self._commit_deadline = None
                    await self._emit(
                        TranscriptEvent(
                            kind="final",
                            text=text,
                            confidence=0.9,
                            language=data.get("language_code") or self.language_code,
                            metadata=self.timing_metadata(),
                        )
                    )
                elif msg_type in {
                    "error",
                    "auth_error",
                    "quota_exceeded",
                    "rate_limited",
                    "input_error",
                    "resource_exhausted",
                    "session_time_limit_exceeded",
                    "commit_throttled",
                    "queue_overflow",
                    "unaccepted_terms",
                }:
                    self._awaiting_final = False
                    self._commit_deadline = None
                    await self._emit(
                        TranscriptEvent(
                            kind="final",
                            text="",
                            confidence=0.0,
                            metadata={
                                "error_category": msg_type,
                                "provider": self.provider_name,
                            },
                        )
                    )
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("STT recv failed: %s", self._safe_error(exc, "recv"))
            self._started = False
            self._ws = None
            await self._emit(
                TranscriptEvent(
                    kind="final",
                    text="",
                    confidence=0.0,
                    metadata={
                        "error_category": "connection",
                        "provider": self.provider_name,
                    },
                )
            )
        finally:
            self._started = False
            await self._queue.put(None)

    async def _emit(self, event: TranscriptEvent) -> None:
        await self._queue.put(event)
        if self._on_event:
            try:
                await self._on_event(event)
            except Exception:  # noqa: BLE001
                logger.exception("STT on_event handler failed")

    @staticmethod
    def _safe_error(exc: BaseException, stage: str) -> str:
        msg = str(exc)
        for secret_marker in ("xi-api-key", "Authorization", "Bearer ", "sk_"):
            if secret_marker.lower() in msg.lower():
                return f"STT {stage} failed (details redacted)"
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return f"STT {stage} failed: {msg}"
