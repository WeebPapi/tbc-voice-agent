"""Text-to-speech adapters."""

from tbc_voice_agent.providers.tts.base import StreamingTextToSpeech, TextToSpeech
from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS
from tbc_voice_agent.providers.tts.fake import FakeTTS
from tbc_voice_agent.providers.tts.openai import OpenAITTS

__all__ = [
    "TextToSpeech",
    "StreamingTextToSpeech",
    "FakeTTS",
    "OpenAITTS",
    "ElevenLabsTTS",
]
