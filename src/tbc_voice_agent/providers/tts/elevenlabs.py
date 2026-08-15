"""ElevenLabs HTTP streaming TTS adapter.

Uses POST /v1/text-to-speech/{voice_id}/stream — not the stream-input WebSocket,
which does not support eleven_v3 (ADR-011).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HttpClientFactory = Callable[..., Any]


class ElevenLabsTTS:
    """Streaming TTS with generation-id cancellation and late-chunk discard."""

    provider_name = "ElevenLabsTTS"

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_v3",
        output_format: str = "pcm_16000",
        connect_timeout_seconds: float = 10.0,
        turn_timeout_seconds: float = 15.0,
        zero_retention: bool = False,
        base_url: str = "https://api.elevenlabs.io",
        http_client: httpx.AsyncClient | None = None,
        http_client_factory: HttpClientFactory | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs API key is required")
        if not voice_id.strip():
            raise ValueError("ElevenLabs voice ID is required")
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self.connect_timeout_seconds = connect_timeout_seconds
        self.turn_timeout_seconds = turn_timeout_seconds
        self.zero_retention = zero_retention
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._http_client_factory = http_client_factory
        self._owns_client = http_client is None
        self._cancelled: set[str] = set()
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._active_responses: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }

    def _url(self) -> str:
        return (
            f"{self.base_url}/v1/text-to-speech/{self.voice_id}/stream"
            f"?output_format={self.output_format}"
        )

    def _body(self, text: str, language: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "text": text,
            "model_id": self.model_id,
        }
        # language_code is supported on TTS stream as ISO 639-1 when provided.
        if language.lower().startswith("ka"):
            body["language_code"] = "ka"
        elif language.lower().startswith("en"):
            body["language_code"] = "en"
        if self.zero_retention:
            body["enable_logging"] = False
        return body

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is not None:
            return self._http_client
        if self._http_client_factory is not None:
            self._http_client = self._http_client_factory()
            return self._http_client
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                # Streaming reads can exceed a single "turn" budget for long lines.
                max(self.turn_timeout_seconds, 60.0),
                connect=self.connect_timeout_seconds,
                read=max(self.turn_timeout_seconds, 60.0),
                write=self.connect_timeout_seconds,
                pool=self.connect_timeout_seconds,
            )
        )
        return self._http_client

    async def cancel(self, generation_id: str) -> None:
        self._cancelled.add(generation_id)
        resp = self._active_responses.pop(generation_id, None)
        if resp is not None:
            try:
                await resp.aclose()
            except Exception:  # noqa: BLE001
                pass

    def is_cancelled(self, generation_id: str) -> bool:
        return generation_id in self._cancelled

    async def stream_synthesize(
        self,
        text: str,
        language: str,
        *,
        generation_id: str,
    ) -> AsyncIterator[bytes]:
        if generation_id in self._cancelled:
            return
        client = await self._client()
        try:
            request = client.build_request(
                "POST",
                self._url(),
                headers=self._headers(),
                json=self._body(text, language),
            )
            response = await client.send(request, stream=True)
            self._active_responses[generation_id] = response
            if response.status_code >= 400:
                await response.aread()
                await response.aclose()
                raise RuntimeError(
                    f"TTS stream failed with status {response.status_code}"
                )
            pending = bytearray()
            async for chunk in response.aiter_bytes():
                if generation_id in self._cancelled:
                    break
                if chunk:
                    pending.extend(chunk)
                    # Coalesce small HTTP frames so the browser gets usable PCM blocks.
                    while len(pending) >= 4096:
                        out = bytes(pending[:4096])
                        del pending[:4096]
                        yield out
            if pending and generation_id not in self._cancelled:
                yield bytes(pending)
        except Exception as exc:  # noqa: BLE001
            if generation_id in self._cancelled:
                return
            raise RuntimeError(self._safe_error(exc)) from None
        finally:
            resp = self._active_responses.pop(generation_id, None)
            if resp is not None:
                try:
                    await resp.aclose()
                except Exception:  # noqa: BLE001
                    pass

    async def synthesize(self, text: str, language: str) -> bytes:
        chunks: list[bytes] = []
        generation_id = "batch"
        async for chunk in self.stream_synthesize(
            text, language, generation_id=generation_id
        ):
            chunks.append(chunk)
        return b"".join(chunks)

    async def aclose(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        msg = str(exc)
        for secret_marker in ("xi-api-key", "Authorization", "Bearer ", "sk_"):
            if secret_marker.lower() in msg.lower():
                return "TTS failed (details redacted)"
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return f"TTS failed: {msg}"
