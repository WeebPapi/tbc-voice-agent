# Build plan for AI agents

## 1. Delivery strategy

Build vertical slices. Each milestone should leave the repository runnable and tested. Do not begin with streaming audio; prove the policy and integration loop in text mode first.

Agents working in parallel must agree on Pydantic/domain schemas from `03-service-contracts-and-events.md` before implementing either side of an interface.

## 2. Milestones

### Milestone 0 — repository foundation

Deliver:

- Python and web project scaffolding.
- Formatting, linting, type checking, and tests.
- `.env.example` and secret-safe `.gitignore`.
- Local start/test/reset commands.
- Shared domain models for money, session IDs, events, states, intents, and dispositions.

Exit criteria:

- A clean checkout starts placeholder web/API/mock services.
- Health endpoints and one smoke test pass.

### Milestone 1 — mock TBC contracts

Deliver:

- Campaign, pre-call, identity, context, offers, outcome, payment-link, and transfer endpoints.
- Fixture set from `05-mock-tbc-and-crm.md`.
- Verification tokens and idempotent outcome storage.
- Admin reset and failure injection.
- Contract tests.

Exit criteria:

- Protected data cannot be fetched before verification.
- Retry/idempotency behavior is demonstrated by tests.

### Milestone 2 — deterministic text conversation

Deliver:

- Session lifecycle and event store.
- State machine and pure policy decisions.
- `TextTransport`, `FakeSTT`, `FakeLLM`, and `FakeTTS`.
- TBC integration client.
- Happy-path reminder and PTP flows.
- Failed identity and wrong-party flows.

Exit criteria:

- Text scenarios run without external credentials.
- Forbidden-disclosure assertions pass.

### Milestone 3 — protected scenarios and resilience

Deliver:

- Payment plan/link, already-paid, dispute, hardship, stop-contact, low-confidence, and technical-failure flows.
- Retry, timeout, and idempotency handling.
- Response-value validation and deterministic safe templates.
- Complete domain event vocabulary.

Exit criteria:

- Mandatory scenario matrix passes.
- A failed CRM call can never cause disclosure or invented data.

### Milestone 4 — demo console

Deliver:

- Fixture/campaign selector and session controls.
- Text conversation panel.
- Live state, transcript, policy, integration, timing, and disposition timeline.
- Failure-injection controls with visible active state.
- Mock human-agent transfer panel.
- Reset function.

Exit criteria:

- A non-developer can run the text demo using `09-demo-and-acceptance.md`.

### Milestone 5 — browser voice

Deliver:

- Browser microphone permission and media transport.
- One real STT and TTS adapter.
- One real enterprise LLM adapter, while retaining fake mode.
- Playback, interruption, timeouts, and stage latency metrics.
- Voice/text mode switch.

Exit criteria:

- Happy-path PTP and hardship transfer work by voice.
- Text scenario suite remains provider-independent and green.

### Milestone 6 — Georgian foundation

Deliver:

- `LanguagePack` abstraction and source-controlled content packs.
- Native-reviewed Georgian text scenarios.
- Georgian normalization tests.
- Recorded-audio benchmark harness.
- One Georgian STT and TTS candidate adapter.

Exit criteria:

- Georgian results are reported using the metrics in `07-georgian-language-readiness.md`.
- No Georgian readiness claim is made without corpus evidence.

## 3. Suggested agent work packages

| Work package | Owns | Must coordinate with |
|---|---|---|
| Domain/contracts | Pydantic models, enums, event envelope, schema tests | Every other package |
| Mock TBC | Mock API, fixtures, failure injection, persistence | Integration client, scenario tests |
| Policy/conversation | State machine, policy decisions, templates | LLM adapter, mock contracts, QA |
| Orchestration/providers | Session coordinator, adapters, retries, timing | Policy, transport, frontend |
| Demo frontend | Browser console, stream, timeline, operator controls | Public API/event schemas |
| QA/scenarios | Scenario runner, forbidden-output checks, acceptance report | All packages |
| Georgian readiness | Language pack, corpus format, normalization, benchmark | Policy/content, provider adapters |

Avoid two agents editing shared schema files concurrently. Land domain contracts first, then use them as the boundary.

## 4. Test pyramid

### Unit tests

- State transitions.
- Policy allow/deny decisions.
- Amount/date normalization and validation.
- Confirmation classification.
- Response fact/offer validation.
- Retry and idempotency behavior.

### Contract tests

- Voice API payloads.
- Mock TBC protected access and error shapes.
- Event envelope and sequence behavior.
- Provider adapter conformance using fakes.

### Scenario tests

Run complete text conversations from session creation through outcome write-back. Assert spoken/returned text, state sequence, policy reason codes, external calls, and final disposition.

### Browser smoke tests

- Create/reset session.
- Run typed happy path.
- Watch event timeline.
- Enable a failure.
- Exercise microphone permission and one voice turn when provider credentials are available.

## 5. Implementation rules that reduce rework

- Establish enums and schema fixtures before endpoints.
- Keep all clocks and ID generators injectable for deterministic tests.
- Store canonical money/date values separately from spoken display strings.
- Version policies, prompts, and content on every session.
- Emit an event at the same point a state change or integration result is committed.
- Do not make browser UI state the source of truth.
- Do not parse business decisions from assistant prose; use structured model output and policy results.
- Add a regression scenario for every safety defect.

## 6. Handoff checklist per milestone

- Code and tests are committed together.
- README commands work from a clean checkout.
- New environment variables appear in `.env.example`.
- API or event changes update the contract document or `10-decisions.md`.
- No secret or real-looking customer data is present.
- Acceptance evidence includes test command output and a short demo note.
