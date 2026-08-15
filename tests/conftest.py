"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_tbc.app import app as mock_app
from mock_tbc.app import store as mock_store
from tbc_voice_agent.config import Settings
from tbc_voice_agent.orchestrator import Orchestrator
from tbc_voice_agent.orchestrator.store import EventStore
from tbc_voice_agent.providers import FakeLLM
from tests.scenarios.helpers import ASGITBCClient

AUTH = {"Authorization": "Bearer dev-mock-tbc-token"}


@pytest.fixture()
def mock_client(tmp_path: Path):
    mock_store.db_path = str(tmp_path / "mock.sqlite")
    mock_store.reset()
    with TestClient(mock_app) as client:
        yield client
    mock_store.reset()


@pytest.fixture()
async def harness(tmp_path: Path):
    mock_store.db_path = str(tmp_path / "mock.sqlite")
    mock_store.reset()
    settings = Settings(
        voice_db_path=str(tmp_path / "voice.sqlite"),
        mock_db_path=str(tmp_path / "mock.sqlite"),
        llm_provider="fake",
        stt_provider="fake",
        tts_provider="fake",
        policy_as_of_date="2026-08-14",
    )
    store = EventStore(settings.voice_db_path)
    tbc = ASGITBCClient()
    orch = Orchestrator(settings, store, tbc, llm=FakeLLM())
    yield orch, store, tbc
    mock_store.reset()
