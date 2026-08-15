"""Speech-to-text adapters."""

from tbc_voice_agent.providers.stt.base import (
    SpeechToText,
    StreamingSpeechToText,
    TranscriptEvent,
)
from tbc_voice_agent.providers.stt.elevenlabs import ElevenLabsScribeRealtime
from tbc_voice_agent.providers.stt.fake import FakeSTT
from tbc_voice_agent.providers.stt.openai import OpenAISTT

__all__ = [
    "SpeechToText",
    "StreamingSpeechToText",
    "TranscriptEvent",
    "FakeSTT",
    "OpenAISTT",
    "ElevenLabsScribeRealtime",
]
