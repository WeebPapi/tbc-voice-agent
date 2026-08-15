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

Open [http://127.0.0.1:5173](http://127.0.0.1:5173) for the **English** console. Text mode works with no paid credentials.

Georgian demo (same orchestrator, isolated ElevenLabs voice): [http://127.0.0.1:5173/ka](http://127.0.0.1:5173/ka).

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

## Consoles

| Route | Language | Voice providers | WebSocket |
|---|---|---|---|
| `/` | English (`en-US`) | OpenAI or fake | `WS /v1/sessions/{id}/stream` |
| `/ka` | Georgian (`ka-GE`) | ElevenLabs or unconfigured | `WS /v1/sessions/{id}/voice` |

Setting `ELEVENLABS_API_KEY` does **not** switch the English providers (ADR-011).

## Voice mode (optional)

### English (`/`)

Set `OPENAI_API_KEY` in `.env`. Providers auto-switch from fake → openai. Choose **Voice** in the English console.

### Georgian (`/ka`)

Set **both**:

```text
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
ELEVENLABS_STT_LANGUAGE_CODE=kat
ELEVENLABS_TTS_MODEL_ID=eleven_v3
ELEVENLABS_TTS_OUTPUT_FORMAT=pcm_16000
```

Without a voice ID, ElevenLabs stays **unconfigured** (no default English voice). Text mode on `/ka` still works.

Optional: `ELEVENLABS_ZERO_RETENTION=true` only when your account supports enterprise zero-retention (`enable_logging=false`). Leave false otherwise.

## Provider status / health

- `GET /v1/providers` — English STT/LLM/TTS class names plus Georgian pack status (`configured`, model, language, format). Never returns API keys.
- `GET /health` — mock TBC reachability, `openai_configured`, `elevenlabs_configured`. Does **not** send audio or consume quota.

## Demo path (English)

1. Reset demo state.
2. Select `cust-001` (Alex Morgan).
3. Start call → answer identity (yes → `15 March` → `0001`).
4. Say/type a PTP such as `I can pay 275.40 GEL on 28 August`, then confirm with `Yes`.
5. Optionally inject `outcome_fail_once` before confirmation to watch retry + single CRM write.
6. Review the event timeline and disposition `PTP_CAPTURED`.

Safety demo: `cust-004` after verification → a natural hardship phrase such as `I crashed my car`. The assistant must stop negotiation and transfer.

## Demo path (Georgian `/ka`)

Same customers and journeys with synthetic Georgian templates:

1. Open `/ka`, text mode (no credentials needed).
2. `cust-001` → `კი` → `15 მარტი` → `0001` → `გადავიხდი 275.40 ლარი 28 აგვისტო` → `კი`.
3. Safety: `cust-004` → verify → `მანქანა დამიტეხა, რთული მდგომარეობაა`.

Voice on `/ka` streams PCM16 16 kHz to ElevenLabs Scribe and plays PCM TTS. Partials update the UI only; finals become turns.

## Georgian smoke corpus

See [`tests/fixtures/georgian_smoke_corpus.md`](tests/fixtures/georgian_smoke_corpus.md). Live smoke (quota):

```powershell
# Requires ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID
python -m pytest tests/integration/test_elevenlabs_smoke.py -q
```

This does **not** claim production Georgian readiness. Full gates: [`docs/07-georgian-language-readiness.md`](docs/07-georgian-language-readiness.md).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/ka` voice says provider not configured | Missing `ELEVENLABS_API_KEY` or `ELEVENLABS_VOICE_ID` |
| English voice silent / STT empty | Missing `OPENAI_API_KEY`; restart after setting |
| Microphone denied | Browser permission; allow mic for `127.0.0.1` |
| STT timeout / technical close before ID | Network or ElevenLabs error; safe close, no disclosure |
| TTS text present but no audio | Check `ELEVENLABS_TTS_OUTPUT_FORMAT=pcm_16000`; console plays PCM via AudioContext |
| English broke after setting ElevenLabs | Should not happen — report if `/` regresses; English uses `/stream` only |

## Known limitations

- Georgian content is synthetic POC copy, not Bank-approved.
- `/ka` TTS uses HTTP streaming (`eleven_v3`); the ElevenLabs TTS WebSocket does not support v3.
- English voice remains push-to-talk WebM + OpenAI, not streaming Scribe.
- Automated tests never call ElevenLabs; live smoke is opt-in.

## Repository layout

```text
apps/api/                 FastAPI voice-agent API + WebSocket
apps/web/                 React + Vite demo console (/ and /ka)
src/tbc_voice_agent/      orchestrator, policy, providers, content, integrations
mock_tbc/                 synthetic Bank API
tests/                    unit, contract, scenarios (AC-01..AC-22 text + ka)
docs/                     specifications (build authority)
```

## Spec authority

See [AGENTS.md](AGENTS.md) and the ordered docs under [`docs/`](docs/). Intentional simplifications are logged in [`docs/10-decisions.md`](docs/10-decisions.md).

## Source material

The original proposal remains under [`work/`](work/). Markdown specifications are the build authority for this POC.
