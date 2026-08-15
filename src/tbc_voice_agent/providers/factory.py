"""Provider factory — English pack vs Georgian ElevenLabs pack (ADR-011)."""

from __future__ import annotations

from typing import Any

from tbc_voice_agent.config import Settings
from tbc_voice_agent.providers.llm import FakeLLM, LanguageModel, OpenAILLM
from tbc_voice_agent.providers.stt.elevenlabs import ElevenLabsScribeRealtime
from tbc_voice_agent.providers.stt.fake import FakeSTT
from tbc_voice_agent.providers.stt.openai import OpenAISTT
from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS
from tbc_voice_agent.providers.tts.fake import FakeTTS
from tbc_voice_agent.providers.tts.openai import OpenAITTS


def build_english_stt(settings: Settings) -> FakeSTT | OpenAISTT:
    if settings.stt_provider == "openai" and settings.openai_api_key:
        return OpenAISTT(settings.openai_api_key, settings.openai_stt_model)
    return FakeSTT()


def build_english_tts(settings: Settings) -> FakeTTS | OpenAITTS:
    if settings.tts_provider == "openai" and settings.openai_api_key:
        return OpenAITTS(
            settings.openai_api_key,
            settings.openai_tts_model,
            settings.openai_tts_voice,
        )
    return FakeTTS()


def build_llm(settings: Settings) -> LanguageModel:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAILLM(settings.openai_api_key, settings.openai_llm_model)
    return FakeLLM(settings.voice_language)


def build_elevenlabs_stt(
    settings: Settings,
    *,
    websocket_factory: Any = None,
) -> ElevenLabsScribeRealtime | None:
    if not settings.has_elevenlabs:
        return None
    return ElevenLabsScribeRealtime(
        api_key=settings.elevenlabs_api_key,
        model_id=settings.elevenlabs_stt_model_id,
        language_code=settings.elevenlabs_stt_language_code,
        audio_format=f"pcm_{settings.elevenlabs_input_sample_rate}",
        sample_rate=settings.elevenlabs_input_sample_rate,
        connect_timeout_seconds=settings.elevenlabs_connect_timeout_seconds,
        turn_timeout_seconds=settings.elevenlabs_turn_timeout_seconds,
        zero_retention=settings.elevenlabs_zero_retention,
        websocket_factory=websocket_factory,
    )


def build_elevenlabs_tts(
    settings: Settings,
    *,
    http_client: Any = None,
) -> ElevenLabsTTS | None:
    if not settings.has_elevenlabs:
        return None
    return ElevenLabsTTS(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_tts_model_id,
        output_format=settings.elevenlabs_tts_output_format,
        connect_timeout_seconds=settings.elevenlabs_connect_timeout_seconds,
        turn_timeout_seconds=settings.elevenlabs_turn_timeout_seconds,
        zero_retention=settings.elevenlabs_zero_retention,
        http_client=http_client,
    )


def provider_status(
    settings: Settings,
    *,
    english_stt: Any,
    english_tts: Any,
    llm: Any,
) -> dict[str, Any]:
    """Safe provider status for /v1/providers — never includes credentials."""
    ka_configured = settings.has_elevenlabs
    return {
        "english": {
            "stt": type(english_stt).__name__,
            "llm": type(llm).__name__,
            "tts": type(english_tts).__name__,
            "openai_configured": settings.has_openai,
        },
        "georgian": {
            "stt": "ElevenLabsScribeRealtime" if ka_configured else "unconfigured",
            "tts": "ElevenLabsTTS" if ka_configured else "unconfigured",
            "configured": ka_configured,
            "stt_model": settings.elevenlabs_stt_model_id if ka_configured else None,
            "tts_model": settings.elevenlabs_tts_model_id if ka_configured else None,
            "language_code": (
                settings.elevenlabs_stt_language_code if ka_configured else None
            ),
            "audio_format": (
                settings.elevenlabs_tts_output_format if ka_configured else None
            ),
            "sample_rate": (
                settings.elevenlabs_input_sample_rate if ka_configured else None
            ),
            "voice_configured": bool(settings.elevenlabs_voice_id.strip()),
            "api_key_configured": bool(settings.elevenlabs_api_key.strip()),
        },
        # Backward-compatible flat fields for the English console.
        "stt": type(english_stt).__name__,
        "llm": type(llm).__name__,
        "tts": type(english_tts).__name__,
        "openai_configured": settings.has_openai,
        "elevenlabs_configured": ka_configured,
    }
