# TBC Voice Agent POC

Local, synthetic proof-of-concept for an outbound soft-collections voice assistant. Mock TBC services stand in for CRM/identity/offers/SMS/transfer. The browser is the call transport. Deterministic policy owns disclosure and outcomes; the LLM only classifies and drafts wording.

## Quick start (Windows)

`make` is optional. Prefer the PowerShell scripts:

```powershell
cd C:\Users\mylaptop.ge\.cursor\tbc-voice-agent\tbc-voice-agent
python -m pip install -e ".[dev]"
copy .env.example .env
cd apps\web
npm install
cd ..\..
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Text mode works with no paid credentials.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
powershell -ExecutionPolicy Bypass -File scripts\demo-reset.ps1
```

If you have Make installed, `make dev`, `make test`, and `make demo-reset` call the same scripts.

Services bind to `127.0.0.1` only:

| Service | Port |
|---|---|
| Demo web console | 5173 |
| Voice-agent API | 8000 |
| Mock TBC API | 8090 |

## Voice mode (optional)

Set `OPENAI_API_KEY` in `.env` and set:

```text
TRANSPORT_PROVIDER=browser
STT_PROVIDER=openai
LLM_PROVIDER=openai
TTS_PROVIDER=openai
```

Then choose **Voice** in the demo console. Without a key, fake adapters remain active and text scenarios stay green.

## Demo path

1. Reset demo state.
2. Select `cust-001` (Alex Morgan).
3. Start call → answer identity (yes → `15 March` → `0001`).
4. Say/type a PTP such as `I can pay 275.40 GEL on 28 August`, then confirm with `Yes`.
5. Optionally inject `outcome_fail_once` before confirmation to watch retry + single CRM write.
6. Review the event timeline and disposition `PTP_CAPTURED`.

Safety demo: `cust-004` after verification → a natural hardship phrase such as `I crashed my car` or `I lost my job and this is a hardship`. The assistant must stop negotiation and transfer.

## Repository layout

```text
apps/api/                 FastAPI voice-agent API + WebSocket
apps/web/                 React + Vite demo console
src/tbc_voice_agent/      orchestrator, policy, providers, content, integrations
mock_tbc/                 synthetic Bank API
tests/                    unit, contract, scenarios (AC-01..AC-22 text)
docs/                     specifications (build authority)
```

## Spec authority

See [AGENTS.md](AGENTS.md) and the ordered docs under [`docs/`](docs/). Intentional simplifications are logged in [`docs/10-decisions.md`](docs/10-decisions.md).

## Source material

The original proposal remains under [`work/`](work/). Markdown specifications are the build authority for this POC.
