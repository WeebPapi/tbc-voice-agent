"""OpenAI TTS for the English browser voice path."""

from __future__ import annotations

from tbc_voice_agent.providers.tts.fake import FakeTTS


class OpenAITTS:
    def __init__(self, api_key: str, model: str, voice: str) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.voice = voice
        self._fallback = FakeTTS()
        self.format = "mp3"

    async def synthesize(self, text: str, language: str) -> bytes:
        if not self.client.api_key:
            return await self._fallback.synthesize(text, language)
        try:
            result = await self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="mp3",
            )
            return result.content
        except Exception:  # noqa: BLE001
            return await self._fallback.synthesize(text, language)
