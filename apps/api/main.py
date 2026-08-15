"""Voice-agent FastAPI application."""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from tbc_voice_agent.config import Settings, get_settings
from tbc_voice_agent.domain import CreateSessionRequest, SessionView, TextTurnRequest
from tbc_voice_agent.integrations.tbc_client import TBCClient
from tbc_voice_agent.orchestrator import Orchestrator
from tbc_voice_agent.orchestrator.store import EventStore

settings = get_settings()
store = EventStore(settings.voice_db_path)
tbc = TBCClient(settings.mock_tbc_base_url, settings.mock_tbc_bearer_token)
orchestrator = Orchestrator(settings, store, tbc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="TBC Voice Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_local_admin() -> None:
    if settings.bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="Admin only on localhost")


def _session_view(session) -> SessionView:
    return SessionView(
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        campaign_id=session.campaign_id,
        customer_ref=session.customer_ref,
        language=session.language,
        transport=session.transport,
        state=session.state,
        disposition=session.disposition,
        identity_status=session.identity.status,
        write_back_status=session.write_back_status,
        created_at=session.created_at,
        ended_at=session.ended_at,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    mock_ok = False
    try:
        await tbc.health()
        mock_ok = True
    except Exception:  # noqa: BLE001
        mock_ok = False
    return {
        "status": "ok" if mock_ok else "degraded",
        "service": "voice_api",
        "mock_tbc": mock_ok,
        "tts": type(orchestrator.tts).__name__,
        "openai_configured": bool(settings.openai_api_key.strip()),
    }


@app.post("/v1/sessions")
async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    try:
        session = await orchestrator.create_session(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": session.session_id,
        "correlation_id": session.correlation_id,
        "state": session.state.value,
        "events_url": f"/v1/sessions/{session.session_id}/events",
    }


@app.post("/v1/sessions/{session_id}/start")
async def start_session(session_id: str) -> dict[str, Any]:
    try:
        result = await orchestrator.start_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return result.model_dump(mode="json")


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str) -> SessionView:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_view(session)


@app.post("/v1/sessions/{session_id}/end")
async def end_session(session_id: str) -> SessionView:
    try:
        session = await orchestrator.end_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return _session_view(session)


@app.get("/v1/sessions/{session_id}/events")
async def get_events(session_id: str, after_sequence: int = 0) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events = store.events_after(session_id, after_sequence)
    return {"events": [e.model_dump(mode="json") for e in events]}


@app.post("/v1/sessions/{session_id}/turns")
async def text_turn(session_id: str, body: TextTurnRequest) -> dict[str, Any]:
    try:
        result = await orchestrator.handle_text_turn(
            session_id, body.text, body.client_turn_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return result.model_dump(mode="json")


@app.post("/v1/sessions/{session_id}/speak")
async def speak_text(session_id: str, body: dict[str, Any]):
    """Synthesize assistant speech for the demo console (mp3 when OpenAI TTS is on)."""
    from fastapi.responses import Response

    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if type(orchestrator.tts).__name__ == "FakeTTS":
        return Response(status_code=204)
    audio = await orchestrator.tts.synthesize(text, session.language)
    if not audio:
        return Response(status_code=204)
    # Fake/fallback may return UTF-8 text bytes — use browser speech instead.
    try:
        audio.decode("utf-8")
        return Response(status_code=204)
    except UnicodeDecodeError:
        pass
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    return {
        "stt": type(orchestrator.stt).__name__,
        "llm": type(orchestrator.llm).__name__,
        "tts": type(orchestrator.tts).__name__,
        "openai_configured": bool(settings.openai_api_key.strip()),
    }


@app.get("/v1/campaigns")
async def campaigns() -> dict[str, Any]:
    return await tbc.list_campaigns("cor_ui")


@app.post("/v1/admin/reset")
async def admin_reset() -> dict[str, str]:
    _require_local_admin()
    await tbc.admin_reset()
    store.reset()
    return {"status": "reset"}


@app.post("/v1/admin/failures")
async def admin_failures(body: dict[str, Any]) -> dict[str, Any]:
    _require_local_admin()
    return await tbc.admin_failures(body["mode"], body.get("session_id"))


@app.delete("/v1/admin/failures")
async def clear_failures() -> dict[str, Any]:
    _require_local_admin()
    return await tbc.clear_failures()


@app.get("/v1/admin/failures")
async def list_failures() -> dict[str, Any]:
    _require_local_admin()
    return await tbc.list_failures()


@app.get("/v1/admin/outcomes")
async def list_outcomes() -> dict[str, Any]:
    _require_local_admin()
    return await tbc.list_outcomes()


@app.get("/v1/admin/transfers")
async def list_transfers() -> dict[str, Any]:
    _require_local_admin()
    return await tbc.list_transfers()


@app.websocket("/v1/sessions/{session_id}/stream")
async def stream(session_id: str, websocket: WebSocket) -> None:
    session = store.get(session_id)
    if not session:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    audio_buffer = bytearray()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"] is not None:
                audio_buffer.extend(message["bytes"])
                continue
            raw = message.get("text")
            if not raw:
                continue
            data = json.loads(raw)
            msg_type = data.get("type")
            if msg_type == "media.start":
                audio_buffer.clear()
                await websocket.send_json({"type": "state.changed", "state": session.state.value})
            elif msg_type == "media.chunk":
                chunk_b64 = data.get("data", "")
                if chunk_b64:
                    audio_buffer.extend(base64.b64decode(chunk_b64))
            elif msg_type == "media.stop":
                if not audio_buffer:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "No audio captured. Hold record briefly, then stop.",
                        }
                    )
                    continue
                text, confidence = await orchestrator.stt.transcribe(
                    bytes(audio_buffer), session.language
                )
                if not (text or "").strip():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                "Could not hear that. For voice mode set OPENAI_API_KEY and "
                                "restart the servers so speech-to-text is enabled."
                            ),
                        }
                    )
                    audio_buffer.clear()
                    continue
                await websocket.send_json(
                    {
                        "type": "transcript.final",
                        "text": text,
                        "confidence": confidence,
                    }
                )
                if session.interrupted:
                    session.interrupted = False
                result = await orchestrator.handle_text_turn(session_id, text)
                await websocket.send_json(
                    {
                        "type": "assistant.text",
                        "text": result.assistant_text,
                        "state": result.state.value,
                    }
                )
                audio = await orchestrator.tts.synthesize(
                    result.assistant_text, session.language
                )
                # Prefer binary frames for PCM/audio bytes
                await websocket.send_bytes(audio)
                await websocket.send_json({"type": "assistant.audio_end"})
                for event in result.events:
                    if event.type.startswith("policy") or event.type.startswith("state"):
                        await websocket.send_json(
                            {"type": event.type, "payload": event.payload}
                        )
                if result.disposition:
                    await websocket.send_json(
                        {
                            "type": "session.ended",
                            "disposition": result.disposition.value,
                        }
                    )
                audio_buffer.clear()
            elif msg_type == "user.interrupt":
                session.interrupted = True
                await websocket.send_json({"type": "assistant.audio_end", "interrupted": True})
            elif msg_type == "session.end":
                await orchestrator.end_session(session_id)
                await websocket.send_json({"type": "session.ended"})
                break
            elif msg_type == "text.turn":
                result = await orchestrator.handle_text_turn(
                    session_id, data.get("text", ""), data.get("client_turn_id")
                )
                await websocket.send_json(
                    {
                        "type": "assistant.text",
                        "text": result.assistant_text,
                        "state": result.state.value,
                    }
                )
    except WebSocketDisconnect:
        return


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    return app
