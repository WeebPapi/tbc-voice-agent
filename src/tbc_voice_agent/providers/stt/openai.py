"""OpenAI Whisper batch STT for the English browser voice path."""

from __future__ import annotations

from tbc_voice_agent.providers.stt.fake import FakeSTT


class OpenAISTT:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._fallback = FakeSTT()

    async def transcribe(self, audio: bytes, language: str) -> tuple[str, float]:
        if not self.client.api_key:
            return await self._fallback.transcribe(audio, language)
        import io

        lang = "en" if language.lower().startswith("en") else "ka"
        file_obj = io.BytesIO(audio)
        file_obj.name = "audio.webm"
        try:
            result = await self.client.audio.transcriptions.create(
                model=self.model,
                file=file_obj,
                language=lang,
            )
            return result.text, 0.9
        except Exception:  # noqa: BLE001
            return await self._fallback.transcribe(audio, language)
