"""Fake batch STT for text mode and tests."""

from __future__ import annotations


class FakeSTT:
    async def transcribe(self, audio: bytes, language: str) -> tuple[str, float]:
        try:
            text = audio.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        return text, 1.0
