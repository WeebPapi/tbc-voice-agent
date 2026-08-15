"""Provider protocols and adapters.

English path uses Fake/OpenAI batch adapters. Georgian `/ka` voice uses
ElevenLabs streaming adapters selected via the factory (ADR-011).
"""

from __future__ import annotations

from tbc_voice_agent.providers.llm import (
    FakeLLM,
    LanguageModel,
    OpenAILLM,
    validate_llm_response,
)
from tbc_voice_agent.providers.slot_normalizer import (
    NormalizedTurnSlots,
    ground_slots,
    needs_normalization,
)
from tbc_voice_agent.providers.stt.base import (
    SpeechToText,
    StreamingSpeechToText,
    TranscriptEvent,
)
from tbc_voice_agent.providers.stt.elevenlabs import ElevenLabsScribeRealtime
from tbc_voice_agent.providers.stt.fake import FakeSTT
from tbc_voice_agent.providers.stt.openai import OpenAISTT
from tbc_voice_agent.providers.tts.base import StreamingTextToSpeech, TextToSpeech
from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS
from tbc_voice_agent.providers.tts.fake import FakeTTS
from tbc_voice_agent.providers.tts.openai import OpenAITTS

__all__ = [
    "SpeechToText",
    "StreamingSpeechToText",
    "TranscriptEvent",
    "TextToSpeech",
    "StreamingTextToSpeech",
    "LanguageModel",
    "FakeSTT",
    "FakeTTS",
    "FakeLLM",
    "OpenAISTT",
    "OpenAITTS",
    "OpenAILLM",
    "ElevenLabsScribeRealtime",
    "ElevenLabsTTS",
    "validate_llm_response",
    "NormalizedTurnSlots",
    "ground_slots",
    "needs_normalization",
]
