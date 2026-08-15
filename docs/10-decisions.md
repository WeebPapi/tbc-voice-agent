# Architecture decisions

This log records POC decisions and deliberate simplifications. Add new entries rather than silently changing a boundary in the specifications.

## ADR-001 — Browser audio instead of SIP for the POC

**Status:** Accepted

**Decision:** Use browser microphone/speaker transport for the demo and keep it behind a transport interface.

**Reason:** It proves the real-time conversation loop without requiring TBC telephony access. Production SIP/media remains a later adapter.

## ADR-002 — English first, Georgian-ready interfaces

**Status:** Accepted

**Decision:** Implement and test the first interactive version in English while passing language through every provider/content interface and keeping normalization language-specific.

**Reason:** The architecture and safety behavior can be validated quickly, while Georgian quality needs a dedicated corpus and native-speaker review.

## ADR-003 — Policy module in the voice API process

**Status:** Accepted for POC

**Decision:** Implement policy as a pure, independently tested module inside the FastAPI voice service, with an explicit request/decision contract.

**Reason:** A separate network service adds operational overhead without improving the POC. The contract preserves a later extraction path.

## ADR-004 — Separate mock TBC process

**Status:** Accepted

**Decision:** Run CRM, identity, offers, SMS/payment-link, outcome, and transfer mocks as a separate local API.

**Reason:** A network boundary makes authentication, timeouts, retries, idempotency, and failure behavior demonstrable.

## ADR-005 — Text mode is mandatory

**Status:** Accepted

**Decision:** All scenarios run without speech or LLM credentials using text transport and fake providers.

**Reason:** Safety and policy behavior must be deterministic, cheap, and testable in continuous integration.

## ADR-006 — Synthetic data and local binding only

**Status:** Accepted

**Decision:** Use obviously synthetic fixtures, bind to localhost by default, and prohibit real data.

**Reason:** This is a behavior/architecture POC, not an approved banking-data environment.

## ADR-007 — Thin project-owned orchestrator instead of Pipecat

**Status:** Accepted for POC

**Decision:** Implement turn coordination as a project-owned FastAPI orchestrator with provider adapters, rather than adopting Pipecat for the first vertical slice.

**Reason:** Identity, disclosure, offers, confirmation, and termination must be owned by deterministic policy code. A thin coordinator makes those boundaries explicit and keeps text-mode scenario tests free of audio-framework coupling.

**Consequences:** Browser voice uses a simple WebSocket media loop (base64 JSON chunks acceptable for POC with binary frames preferred for TTS playback). A later SIP/Pipecat adapter can replace the transport without rewriting policy.

## ADR-008 — OpenAI as the optional English voice provider pack

**Status:** Accepted for POC

**Decision:** Use OpenAI Whisper, `gpt-4o-mini`, and `tts-1` when `OPENAI_API_KEY` is present; default all providers to fake adapters so text mode needs no credentials.

**Reason:** One vendor keeps local setup small for the browser-voice milestone while preserving provider interfaces for Bank-approved replacements.

## ADR-009 — Deterministic safety overlay and template-only speech

**Status:** Accepted

**Decision:** After the LLM classifies a turn, the orchestrator applies a deterministic phrase overlay for hardship, dispute, and stop-contact. That overlay wins in every post-verification state, including PTP confirmation. Customer-facing speech uses approved templates only; LLM `response_text` is never spoken. Identity answers are not sent to the LLM and are redacted in the event log.

**Reason:** A live OpenAI classifier missed “I crashed my car” during PTP confirmation, treated it as an unclear yes/no, then presented an unrelated payment plan. Spec AC-12 requires an empathetic stop and transfer. The LLM remains a classifier, not an authority.

**Consequences:** Phrase lists must be extended as new vulnerability language appears. Spoken wording is less varied. Scenario tests cover the Taylor Smith car-crash transcript and a stub LLM that returns `UNKNOWN` plus chatbot prose.

## ADR-010 — Configurable policy as-of date

**Status:** Accepted

**Decision:** PTP date bounds use `Settings.policy_as_of_date` when set, otherwise `date.today()`. Tests pin `2026-08-14` to stay aligned with fixtures.

**Reason:** A hardcoded calendar day in the policy engine would reject valid promises as soon as the demo clock moved.

## Decision template

```markdown
## ADR-NNN — Title

**Status:** Proposed | Accepted | Superseded

**Decision:** What changes or is fixed.

**Reason:** Why this choice is appropriate.

**Consequences:** Important trade-offs, migrations, or new tests.
```
