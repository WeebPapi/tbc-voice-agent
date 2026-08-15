"""Fake TTS for text mode and tests."""

from __future__ import annotations


class FakeTTS:
    async def synthesize(self, text: str, language: str) -> bytes:
        return text.encode("utf-8")
