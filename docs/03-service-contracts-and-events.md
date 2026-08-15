# Service contracts and events

## 1. Contract rules

- JSON uses `snake_case`.
- Timestamps use UTC ISO 8601.
- Money is a decimal string plus ISO currency, never a floating-point number.
- Dates use `YYYY-MM-DD`.
- Every request carries `correlation_id`.
- Every write carries `idempotency_key`.
- Error responses use a stable `code`, human-readable `message`, and `retryable` flag.
- APIs are versioned under `/v1`.
- Unknown fields may be ignored during the POC; removing or changing a field is breaking.

## 2. Voice-agent public API

### Create a session

`POST /v1/sessions`

```json
{
  "campaign_id": "campaign-en-001",
  "customer_ref": "cust-001",
  "transport": "text",
  "language": "en-US"
}
```

Response:

```json
{
  "session_id": "ses_01...",
  "correlation_id": "cor_01...",
  "state": "created",
  "events_url": "/v1/sessions/ses_01.../events"
}
```

### Start, inspect, and end

- `POST /v1/sessions/{session_id}/start`
- `GET /v1/sessions/{session_id}`
- `POST /v1/sessions/{session_id}/end`
- `GET /v1/sessions/{session_id}/events?after_sequence=42`

### Text turn

`POST /v1/sessions/{session_id}/turns`

```json
{"text": "Yes, this is Alex", "client_turn_id": "turn-3"}
```

The response includes the accepted user turn, assistant text, state, and new events. Repeating `client_turn_id` must not create a second turn.

### Browser media/events WebSocket

`WS /v1/sessions/{session_id}/stream`

English OpenAI/fake push-to-talk path (ADR-008 / ADR-011). Batch audio on `media.stop`.

Client messages:

- `media.start`
- `media.chunk`
- `media.stop`
- `user.interrupt`
- `session.end`

Server messages:

- `transcript.partial`
- `transcript.final`
- `assistant.text`
- `assistant.audio_chunk`
- `assistant.audio_end`
- `state.changed`
- `policy.decided`
- `integration.completed`
- `error`
- `session.ended`

Binary audio frames are preferred for media chunks. If base64 JSON is used for the first slice, document the performance limitation and keep the transport interface independent.

### Georgian streaming voice WebSocket

`WS /v1/sessions/{session_id}/voice`

Isolated ElevenLabs path for the `/ka` console (ADR-011). PCM16 16 kHz incremental audio; partials never trigger policy.

Client messages:

- `media.start`
- `media.chunk` (base64 PCM) or raw binary PCM frames
- `media.stop` (ack only; VAD commits on the provider)
- `user.interrupt`
- `session.end`
- `text.turn` (optional text fallback on the same socket)

Server messages:

- `provider.status` (configured flag, model, language, format — never credentials)
- `transcript.partial`
- `transcript.final`
- `assistant.text`
- `assistant.audio_chunk` (base64 PCM) and/or binary frames
- `assistant.audio_end`
- `state.changed` / `policy.decided`
- `error` (`provider_not_configured`, `stt_failed`, `tts_failed`)
- `session.ended`

## 3. Internal policy contract

```json
{
  "session_id": "ses_01...",
  "policy_version": "poc-v1",
  "state": "discussing_options",
  "identity": {"status": "verified", "evidence_ref": "idv_01..."},
  "intent": "promise_to_pay",
  "slots": {"amount": "275.40", "currency": "GEL", "date": "2026-08-28"},
  "context": {"eligible_offer_ids": ["offer-001"], "account_status": "overdue"},
  "dependency_health": {"crm": "available", "policy": "available"}
}
```

Decision:

```json
{
  "allowed": true,
  "action": "request_ptp_confirmation",
  "next_state": "confirming_ptp",
  "reason_code": "PTP_WITHIN_ALLOWED_RANGE",
  "permitted_facts": ["requested_amount", "requested_date"],
  "permitted_offer_ids": [],
  "required_confirmation": true
}
```

Denied decisions include a safe template key, such as `technical_failure_close`, and must not rely on the LLM to invent the safe action.

## 4. Mock TBC API summary

Detailed behavior is in `05-mock-tbc-and-crm.md`.

| Method and path | Purpose |
|---|---|
| `GET /v1/campaigns` | List synthetic campaigns |
| `GET /v1/customers/{customer_ref}/pre_call` | Minimum pre-verification calling context |
| `POST /v1/identity/verifications` | Deterministic synthetic identity check |
| `GET /v1/customers/{customer_ref}/collections-context` | Protected context; requires verification token |
| `GET /v1/customers/{customer_ref}/eligible-offers` | Current approved offers; requires verification token |
| `POST /v1/outcomes` | Idempotent CRM outcome write |
| `POST /v1/payment-link-requests` | Mock Bank-authorized SMS/link action |
| `POST /v1/transfers` | Mock human queue hand-off |
| `POST /v1/admin/failures` | Operator-only failure injection |
| `POST /v1/admin/reset` | Restore fixture state |

## 5. Domain event envelope

```json
{
  "event_id": "evt_01...",
  "session_id": "ses_01...",
  "correlation_id": "cor_01...",
  "sequence": 17,
  "type": "policy.decided",
  "occurred_at": "2026-08-14T18:15:04.120Z",
  "source": "policy_engine",
  "payload": {},
  "redaction": {"contains_pii": false, "fields_removed": []}
}
```

Sequence is monotonically increasing within a session. Consumers order by `sequence`, not wall-clock time.

## 6. Minimum event vocabulary

| Event | Required payload |
|---|---|
| `session.created` | campaign, customer reference, language, transport |
| `session.started` | policy and prompt versions |
| `transcript.final` | speaker, text, confidence, timing |
| `intent.classified` | intent, slots, confidence, model/fake adapter |
| `slots.normalized` | filled/repaired keys, adapter, confidence; non-PII before/after for amount/date; identity values never logged |
| `identity.requested` | question-set version and attempt number |
| `identity.decided` | verified/failed, reason, evidence reference; no raw answers |
| `policy.decided` | input state, allowed, action, next state, reason code |
| `state.changed` | previous and next state, trigger |
| `assistant.response_approved` | text, template/prompt version, permitted fact references |
| `integration.requested` | integration name, operation, idempotency key if applicable |
| `integration.completed` | status, external reference, latency, retry count |
| `ptp.confirmed` | amount, currency, date, confirmation turn reference |
| `payment_link.requested` | offer/payment reference and Bank response reference |
| `transfer.requested` | route, reason, priority |
| `error.occurred` | component, stable code, retryable, safe action |
| `session.ended` | disposition, reason, duration, write-back status |
| `stt.connection_started` | provider, model, language, audio format, sample rate |
| `stt.partial_received` | provider; timing metadata; no identity answers |
| `stt.final_received` | provider, confidence, timing; no identity answers in payload |
| `stt.connection_closed` | provider |
| `stt.failed` | provider, error category |
| `tts.started` | provider, model, output format, generation_id, turn_id |
| `tts.first_audio` | provider, generation_id, time_to_first_audio_ms |
| `tts.completed` | provider, generation_id, duration_ms |
| `tts.cancelled` | provider, generation_id, reason |
| `tts.failed` | provider, generation_id, error category, safe message |

## 7. Dispositions

Minimum values:

```text
VERIFIED_REMINDER
ID_FAILED
WRONG_PARTY
NO_ANSWER
ALREADY_PAID_CLAIMED
PTP_CAPTURED
PLAN_ACCEPTED
PAYMENT_LINK_REQUESTED
DISPUTE_ESCALATED
VULNERABILITY_ESCALATED
STOP_CONTACT
LEGAL_ESCALATION
LOW_CONFIDENCE
HUMAN_TRANSFERRED
TECHNICAL_FAILURE
CUSTOMER_ENDED
```

## 8. Error shape

```json
{
  "error": {
    "code": "MOCK_CRM_UNAVAILABLE",
    "message": "Customer context is temporarily unavailable.",
    "retryable": true,
    "safe_action": "close_without_disclosure"
  },
  "correlation_id": "cor_01..."
}
```

Never return stack traces, provider credentials, full prompts, or raw identity answers to the browser.
