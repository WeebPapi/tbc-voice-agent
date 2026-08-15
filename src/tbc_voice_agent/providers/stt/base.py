"""STT protocols: batch (English) and streaming (Georgian voice)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TranscriptEvent:
    """Partial or final transcript from a streaming STT session."""

    kind: str  # "partial" | "final"
    text: str
    confidence: float = 1.0
    language: str | None = None
    client_turn_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SpeechToText(Protocol):
    """Batch transcription used by the English push-to-talk path."""

    async def transcribe(self, audio: bytes, language: str) -> tuple[str, float]: ...


class StreamingSpeechToText(Protocol):
    """Session-scoped streaming STT (one remote stream per conversation)."""

    provider_name: str
    model_id: str
    language_code: str
    audio_format: str
    sample_rate: int

    async def start(
        self,
        *,
        correlation_id: str,
        on_event: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
    ) -> None: ...

    async def push_audio(self, chunk: bytes) -> list[TranscriptEvent]: ...

    async def aclose(self) -> None: ...

    def events(self) -> AsyncIterator[TranscriptEvent]: ...
