"""TTS protocols: batch (English) and streaming (Georgian voice)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class TextToSpeech(Protocol):
    async def synthesize(self, text: str, language: str) -> bytes: ...


class StreamingTextToSpeech(Protocol):
    """Streaming TTS that can cancel an in-flight generation."""

    provider_name: str
    model_id: str
    output_format: str
    voice_id: str

    async def stream_synthesize(
        self,
        text: str,
        language: str,
        *,
        generation_id: str,
    ) -> AsyncIterator[bytes]: ...

    async def cancel(self, generation_id: str) -> None: ...

    async def synthesize(self, text: str, language: str) -> bytes: ...
