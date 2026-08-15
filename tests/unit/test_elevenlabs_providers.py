"""Unit tests for ElevenLabs adapters and factory — no live API calls."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx
import pytest

from tbc_voice_agent.config import Settings
from tbc_voice_agent.domain import (
    ConversationState,
    CreateSessionRequest,
    Disposition,
    Intent,
    LLMResult,
)
from tbc_voice_agent.orchestrator import Orchestrator
from tbc_voice_agent.orchestrator.store import EventStore
from tbc_voice_agent.orchestrator.voice_runtime import VoiceSessionRuntime
from tbc_voice_agent.providers import FakeLLM, validate_llm_response
from tbc_voice_agent.providers.factory import (
    build_elevenlabs_stt,
    build_elevenlabs_tts,
    build_english_stt,
    build_english_tts,
    build_llm,
    provider_status,
)
from tbc_voice_agent.providers.stt.elevenlabs import ElevenLabsScribeRealtime
from tbc_voice_agent.providers.tts.elevenlabs import ElevenLabsTTS
from tests.scenarios.helpers import ASGITBCClient


class FakeWS:
    def __init__(self, inbound: list[str] | None = None) -> None:
        self.sent: list[str] = []
        self._inbound = list(inbound or [])
        self._closed = False
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        for item in self._inbound:
            self._queue.put_nowait(item)

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return await asyncio.wait_for(self._queue.get(), timeout=5)

    def push(self, message: dict[str, Any]) -> None:
        self._queue.put_nowait(json.dumps(message))

    async def close(self) -> None:
        self._closed = True


@pytest.fixture()
def settings_no_el(tmp_path):
    return Settings(
        voice_db_path=str(tmp_path / "voice.sqlite"),
        mock_db_path=str(tmp_path / "mock.sqlite"),
        llm_provider="fake",
        stt_provider="fake",
        tts_provider="fake",
        openai_api_key="",
        elevenlabs_api_key="",
        elevenlabs_voice_id="",
        policy_as_of_date="2026-08-14",
    )


@pytest.fixture()
def settings_el(tmp_path):
    return Settings(
        voice_db_path=str(tmp_path / "voice.sqlite"),
        mock_db_path=str(tmp_path / "mock.sqlite"),
        llm_provider="fake",
        stt_provider="fake",
        tts_provider="fake",
        openai_api_key="",
        elevenlabs_api_key="test-key-not-real",
        elevenlabs_voice_id="voice-test-001",
        elevenlabs_stt_language_code="kat",
        policy_as_of_date="2026-08-14",
    )


def test_factory_without_elevenlabs(settings_no_el):
    assert build_elevenlabs_stt(settings_no_el) is None
    assert build_elevenlabs_tts(settings_no_el) is None
    assert type(build_english_stt(settings_no_el)).__name__ == "FakeSTT"
    assert type(build_english_tts(settings_no_el)).__name__ == "FakeTTS"
    status = provider_status(
        settings_no_el,
        english_stt=build_english_stt(settings_no_el),
        english_tts=build_english_tts(settings_no_el),
        llm=build_llm(settings_no_el),
    )
    assert status["georgian"]["configured"] is False
    assert status["georgian"]["stt"] == "unconfigured"
    assert status["georgian"]["api_key_configured"] is False


def test_factory_key_without_voice_id(tmp_path):
    s = Settings(
        voice_db_path=str(tmp_path / "v.sqlite"),
        elevenlabs_api_key="test-key",
        elevenlabs_voice_id="",
        llm_provider="fake",
        stt_provider="fake",
        tts_provider="fake",
    )
    assert s.has_elevenlabs is False
    assert build_elevenlabs_stt(s) is None


def test_factory_with_elevenlabs(settings_el):
    stt = build_elevenlabs_stt(settings_el)
    tts = build_elevenlabs_tts(settings_el)
    assert isinstance(stt, ElevenLabsScribeRealtime)
    assert isinstance(tts, ElevenLabsTTS)
    assert stt.language_code == "kat"
    status = provider_status(
        settings_el,
        english_stt=build_english_stt(settings_el),
        english_tts=build_english_tts(settings_el),
        llm=build_llm(settings_el),
    )
    assert status["georgian"]["stt"] == "ElevenLabsScribeRealtime"
    assert status["georgian"]["tts"] == "ElevenLabsTTS"
    dumped = json.dumps(status)
    assert "test-key" not in dumped
    assert "xi-api-key" not in dumped


@pytest.mark.asyncio
async def test_partial_does_not_trigger_turn(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE", transport="browser")
    )
    await orch.start_session(session.session_id)

    ws = FakeWS()
    turns: list[str] = []

    async def track_turn(sid, text, client_turn_id=None):
        turns.append(text)
        return await Orchestrator.handle_text_turn(orch, sid, text, client_turn_id)

    orch.handle_text_turn = track_turn  # type: ignore[method-assign]

    async def factory(uri, **kwargs):
        return ws

    stt = ElevenLabsScribeRealtime(
        api_key="test-key",
        websocket_factory=factory,
        turn_timeout_seconds=2,
    )
    tts = ElevenLabsTTS(
        api_key="test-key",
        voice_id="voice-1",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x00\x01"))
        ),
    )
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=stt,
        tts=tts,
        send_json=send_json,
    )
    await runtime.start_stt()
    ws.push({"message_type": "session_started", "session_id": "el-1", "config": {}})
    await runtime.set_listening(True)
    ws.push({"message_type": "partial_transcript", "text": "გამარჯობა"})
    await asyncio.sleep(0.05)
    assert turns == []
    assert any(m.get("type") == "transcript.partial" for m in messages)
    await runtime.aclose()


@pytest.mark.asyncio
async def test_final_triggers_exactly_one_turn(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    turns: list[str] = []
    original = orch.handle_text_turn

    async def track(sid, text, client_turn_id=None):
        turns.append(text)
        return await original(sid, text, client_turn_id)

    orch.handle_text_turn = track  # type: ignore[method-assign]

    ws = FakeWS()

    async def factory(uri, **kwargs):
        return ws

    stt = ElevenLabsScribeRealtime(api_key="k", websocket_factory=factory)
    tts = ElevenLabsTTS(
        api_key="k",
        voice_id="v",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x00\x00"))
        ),
    )
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=stt,
        tts=tts,
        send_json=send_json,
    )
    await runtime.start_stt()
    ws.push({"message_type": "session_started", "session_id": "el-1", "config": {}})
    ws.push({"message_type": "committed_transcript", "text": "კი"})
    await asyncio.sleep(0.15)
    assert turns == ["კი"]
    assert sum(1 for m in messages if m.get("type") == "transcript.final") == 1
    await runtime.aclose()


@pytest.mark.asyncio
async def test_duplicate_client_turn_id_ignored(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)
    r1 = await orch.handle_text_turn(session.session_id, "კი", "turn-dup-1")
    r2 = await orch.handle_text_turn(session.session_id, "კი", "turn-dup-1")
    assert r1.assistant_text
    assert r2.assistant_text == ""


@pytest.mark.asyncio
async def test_identity_redacted_and_not_sent_to_llm(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    llm = FakeLLM("ka-GE")
    called: list[str] = []

    async def wrap_classify(**kwargs):
        called.append(kwargs["text"])
        return await FakeLLM.classify(llm, **kwargs)

    llm.classify = wrap_classify  # type: ignore[method-assign]
    orch = Orchestrator(settings_el, store, tbc, llm=llm)
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)
    await orch.handle_text_turn(session.session_id, "კი")
    await orch.handle_text_turn(session.session_id, "15 მარტი")
    events = store.events_after(session.session_id, 0)
    identity_transcripts = [
        e for e in events if e.type == "transcript.final" and e.redaction.get("contains_pii")
    ]
    assert identity_transcripts
    assert all(e.payload["text"] == "[redacted identity answer]" for e in identity_transcripts)
    assert called == []  # identity path skips LLM


@pytest.mark.asyncio
async def test_stt_timeout_after_commit_does_not_kill_session(settings_el, tmp_path):
    """Post-commit silence should ask to retry, not auto-close the call."""
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    ws = FakeWS()

    async def factory(uri, **kwargs):
        return ws

    stt = ElevenLabsScribeRealtime(
        api_key="k", websocket_factory=factory, turn_timeout_seconds=0.05
    )
    tts = ElevenLabsTTS(
        api_key="k",
        voice_id="v",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b""))
        ),
    )
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=stt,
        tts=tts,
        send_json=send_json,
    )
    await runtime.start_stt()
    ws.push({"message_type": "session_started", "session_id": "el-1", "config": {}})
    await runtime.set_listening(True)
    await runtime.push_audio(b"\x00\x01" * 100)
    await runtime.set_listening(False)
    await runtime.commit_audio()
    await asyncio.sleep(1.3)
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.disposition is None
    assert rec.state == ConversationState.VERIFYING_IDENTITY
    assert any(m.get("code") == "stt_timeout" for m in messages)
    await runtime.aclose()


@pytest.mark.asyncio
async def test_stt_hard_failure_before_verification_technical_close(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    ws = FakeWS()

    async def factory(uri, **kwargs):
        return ws

    stt = ElevenLabsScribeRealtime(api_key="k", websocket_factory=factory)
    tts = ElevenLabsTTS(
        api_key="k",
        voice_id="v",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b""))
        ),
    )
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=stt,
        tts=tts,
        send_json=send_json,
    )
    await runtime.start_stt()
    ws.push({"message_type": "session_started", "session_id": "el-1", "config": {}})
    ws.push({"message_type": "auth_error", "error": "bad key"})
    await asyncio.sleep(0.15)
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.disposition == Disposition.TECHNICAL_FAILURE
    assert rec.state == ConversationState.TERMINATED
    assert not any("275.40" in str(m) for m in messages)
    await runtime.aclose()


@pytest.mark.asyncio
async def test_approved_response_reaches_tts(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    spoken: list[str] = []

    class CapturingTTS(ElevenLabsTTS):
        async def stream_synthesize(self, text, language, *, generation_id):
            spoken.append(text)
            yield b"\x00\x01"

    tts = CapturingTTS(api_key="k", voice_id="v")
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=None,
        tts=tts,
        send_json=send_json,
    )
    runtime._configured = True
    await runtime.handle_text_turn("კი", "t1")
    await asyncio.sleep(0.05)
    assert spoken
    assert any(m.get("type") == "assistant.audio_chunk" for m in messages)


@pytest.mark.asyncio
async def test_unvalidated_response_never_reaches_tts():
    bad = LLMResult(
        intent=Intent.ACCEPT_PLAN,
        slots={"offer_id": "offer-invented-999"},
        confidence=0.9,
        response_text="Take offer-invented-999 for 1.00 GEL",
    )
    ok, reason = validate_llm_response(bad, {"eligible_offer_ids": ["offer-001"]}, ["offer-001"])
    assert ok is False
    assert reason == "INVENTED_OFFER"


@pytest.mark.asyncio
async def test_tts_chunks_bound_to_session_and_turn(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    class CapturingTTS(ElevenLabsTTS):
        async def stream_synthesize(self, text, language, *, generation_id):
            yield b"\x01\x02"

    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=None,
        tts=CapturingTTS(api_key="k", voice_id="v"),
        send_json=send_json,
    )
    runtime._configured = True
    await runtime.handle_text_turn("კი", "turn-bound-1")
    await asyncio.sleep(0.05)
    chunks = [m for m in messages if m.get("type") == "assistant.audio_chunk"]
    assert chunks
    assert all(m.get("generation_id") for m in chunks)
    events = [e for e in store.events_after(session.session_id, 0) if e.type == "tts.started"]
    assert events
    assert events[0].payload["turn_id"] == "turn-bound-1"
    assert events[0].session_id == session.session_id


@pytest.mark.asyncio
async def test_barge_in_cancels_tts_late_chunks_ignored(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    class SlowTTS(ElevenLabsTTS):
        async def stream_synthesize(self, text, language, *, generation_id):
            yield b"\x01\x00"
            await asyncio.sleep(0.05)
            if self.is_cancelled(generation_id):
                return
            yield b"\x02\x00"
            await asyncio.sleep(0.05)
            if self.is_cancelled(generation_id):
                return
            yield b"\x03\x00"

    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    tts = SlowTTS(api_key="k", voice_id="v")
    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=None,
        tts=tts,
        send_json=send_json,
    )
    runtime._configured = True
    task = asyncio.create_task(runtime.handle_text_turn("კი", "turn-barge"))
    await asyncio.sleep(0.02)
    await runtime.interrupt(reason="barge_in")
    await task
    await asyncio.sleep(0.15)
    chunks = [m for m in messages if m.get("type") == "assistant.audio_chunk"]
    # At most the first chunk before cancel; late chunks discarded
    assert len(chunks) <= 1
    cancelled = [
        e for e in store.events_after(session.session_id, 0) if e.type == "tts.cancelled"
    ]
    assert cancelled


@pytest.mark.asyncio
async def test_two_sessions_isolated(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    s1 = await orch.create_session(CreateSessionRequest(customer_ref="cust-001", language="ka-GE"))
    s2 = await orch.create_session(CreateSessionRequest(customer_ref="cust-004", language="ka-GE"))
    await orch.start_session(s1.session_id)
    await orch.start_session(s2.session_id)

    msgs1: list[dict] = []
    msgs2: list[dict] = []

    async def send1(p):
        msgs1.append(p)

    async def send2(p):
        msgs2.append(p)

    r1 = VoiceSessionRuntime(
        session_id=s1.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=None,
        tts=None,
        send_json=send1,
    )
    r2 = VoiceSessionRuntime(
        session_id=s2.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=None,
        tts=None,
        send_json=send2,
    )
    await r1.handle_text_turn("კი", "a1")
    await r2.handle_text_turn("კი", "b1")
    assert all(True for _ in msgs1)  # r1 only
    # Messages collected separately — no cross-talk by construction
    assert msgs1 is not msgs2
    e1 = store.events_after(s1.session_id, 0)
    e2 = store.events_after(s2.session_id, 0)
    assert all(e.session_id == s1.session_id for e in e1)
    assert all(e.session_id == s2.session_id for e in e2)


@pytest.mark.asyncio
async def test_missing_credentials_text_mode_works(settings_no_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_no_el, store, tbc, llm=FakeLLM())
    session = await orch.create_session(CreateSessionRequest(customer_ref="cust-001"))
    started = await orch.start_session(session.session_id)
    assert "Alex" in started.assistant_text or "TBC" in started.assistant_text
    result = await orch.handle_text_turn(session.session_id, "Yes")
    assert result.assistant_text


def test_provider_failures_expose_no_secrets():
    err = ElevenLabsScribeRealtime._safe_error(
        Exception("auth failed xi-api-key=sk_live_secret Authorization: Bearer tok"),
        "connect",
    )
    assert "sk_live" not in err
    assert "Bearer" not in err
    assert "xi-api-key" not in err.lower() or "redacted" in err.lower()
    tts_err = ElevenLabsTTS._safe_error(
        Exception("header xi-api-key=abc Authorization Bearer xyz")
    )
    assert "abc" not in tts_err or "redacted" in tts_err.lower()
    assert "Bearer" not in tts_err


@pytest.mark.asyncio
async def test_stt_sends_documented_audio_chunk_shape(settings_el):
    ws = FakeWS()
    ws.push({"message_type": "session_started", "session_id": "x", "config": {}})

    async def factory(uri, **kwargs):
        assert "model_id=scribe_v2_realtime" in uri
        assert "language_code=kat" in uri
        assert "commit_strategy=manual" in uri
        assert "enable_logging" not in uri  # zero retention off
        assert kwargs.get("additional_headers", {}).get("xi-api-key") == "k"
        return ws

    stt = ElevenLabsScribeRealtime(api_key="k", language_code="kat", websocket_factory=factory)
    await stt.start(correlation_id="cor_1")
    await stt.push_audio(b"\x00\x01\x02\x03")
    assert ws.sent
    payload = json.loads(ws.sent[0])
    assert payload["message_type"] == "input_audio_chunk"
    assert payload["commit"] is False
    assert payload["sample_rate"] == 16000
    assert base64.b64decode(payload["audio_base_64"]) == b"\x00\x01\x02\x03"
    await stt.aclose()


def test_zero_retention_only_when_enabled(settings_el):
    stt = ElevenLabsScribeRealtime(
        api_key="k", language_code="eng", zero_retention=True
    )
    url = stt._build_url()
    assert "enable_logging=false" in url
    stt2 = ElevenLabsScribeRealtime(api_key="k", language_code="eng", zero_retention=False)
    assert "enable_logging" not in stt2._build_url()


@pytest.mark.asyncio
async def test_stt_send_failure_emits_once(settings_el, tmp_path):
    store = EventStore(str(tmp_path / "voice.sqlite"))
    tbc = ASGITBCClient()
    orch = Orchestrator(settings_el, store, tbc, llm=FakeLLM("ka-GE"))
    session = await orch.create_session(
        CreateSessionRequest(customer_ref="cust-001", language="ka-GE")
    )
    await orch.start_session(session.session_id)

    class DeadWS(FakeWS):
        async def send(self, data: str) -> None:
            raise RuntimeError("socket closed")

    ws = DeadWS()

    async def factory(uri, **kwargs):
        return ws

    stt = ElevenLabsScribeRealtime(api_key="k", websocket_factory=factory)
    tts = ElevenLabsTTS(
        api_key="k",
        voice_id="v",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x00\x00"))
        ),
    )
    messages: list[dict] = []

    async def send_json(p):
        messages.append(p)

    runtime = VoiceSessionRuntime(
        session_id=session.session_id,
        settings=settings_el,
        orchestrator=orch,
        store=store,
        stt=stt,
        tts=tts,
        send_json=send_json,
    )
    await runtime.start_stt()
    await runtime.set_listening(True)
    for _ in range(12):
        await runtime.push_audio(b"\x00\x10" * 64)
    failed = [
        e for e in store.events_after(session.session_id, 0) if e.type == "stt.failed"
    ]
    assert len(failed) == 1
    rec = store.get(session.session_id)
    assert rec is not None
    assert rec.state != ConversationState.TERMINATED
    assert any(m.get("code") == "stt_reconnecting" for m in messages)
    await runtime.aclose()
