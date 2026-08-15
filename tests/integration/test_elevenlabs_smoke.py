"""Opt-in ElevenLabs live smoke — skipped unless credentials are present.

WARNING: This test consumes ElevenLabs quota. Synthetic Georgian content only.
"""

from __future__ import annotations

import os

import pytest

REQUIRED = (
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
)


def _configured() -> bool:
    return all(os.getenv(k, "").strip() for k in REQUIRED)


pytestmark = pytest.mark.skipif(
    not _configured(),
    reason="Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID to run live smoke (consumes quota)",
)


@pytest.mark.asyncio
async def test_elevenlabs_tts_smoke_synthetic_georgian():
    """Synthesize one short synthetic Georgian greeting — warns quota use."""
    import warnings

    warnings.warn(
        "Live ElevenLabs smoke is running and will consume quota.",
        UserWarning,
        stacklevel=1,
    )
    from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS

    tts = ElevenLabsTTS(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        model_id=os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_v3"),
        output_format=os.getenv("ELEVENLABS_TTS_OUTPUT_FORMAT", "pcm_16000"),
    )
    audio = await tts.synthesize(
        "გამარჯობა, ეს არის TBC დემო ასისტენტი.",
        "ka-GE",
    )
    assert audio
    assert len(audio) > 100
    await tts.aclose()
