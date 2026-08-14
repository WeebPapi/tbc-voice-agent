# Instructions for implementation agents

## Mission

Build a local, repeatable POC of the TBC outbound collections voice assistant described in `docs/`. Do not treat this repository as a production banking system.

## Specification authority

When documents disagree, use this order:

1. `docs/09-demo-and-acceptance.md` for observable acceptance behavior.
2. `docs/04-conversation-and-policy.md` for safety and conversation behavior.
3. `docs/03-service-contracts-and-events.md` for interfaces.
4. `docs/02-technical-specification.md` for architecture and implementation choices.
5. `docs/08-agent-build-plan.md` for sequencing.
6. The source proposal under `work/` for background intent.

Record a decision in `docs/10-decisions.md` before intentionally changing a specified boundary.

## Non-negotiable constraints

- Use synthetic data only. Never add real customer data, credentials, recordings, or transcripts.
- Do not allow account, balance, overdue, offer, or payment information before deterministic identity verification succeeds.
- The LLM may classify and draft wording; it may not approve identity, determine eligibility, invent offers, or select protected-case outcomes.
- If CRM, identity, policy, or offer data is unavailable, fail closed: do not disclose or negotiate.
- Every material action must emit a structured event with a correlation ID.
- CRM outcome writes must be idempotent.
- Keep transport, STT, LLM, and TTS behind interfaces. The text-mode simulator must work without paid provider credentials.
- Keep the first milestone runnable locally with one documented command.
- Do not expose the development server publicly by default.

## Intended repository shape

```text
apps/
  api/                 FastAPI application and WebSocket endpoints
  web/                 browser demo console
src/tbc_voice_agent/
  orchestrator/        session lifecycle and turn coordination
  policy/              deterministic state machine and rules
  providers/           STT, LLM, TTS, and transport adapters
  integrations/        clients for mocked TBC services
  domain/              typed commands, events, and models
mock_tbc/               synthetic CRM/policy/SMS/transfer service
tests/
  unit/
  contract/
  scenarios/
docs/
```

A simpler layout is acceptable during the first vertical slice, but preserve the module boundaries.

## Engineering expectations

- Python 3.12+, FastAPI, Pydantic, and pytest are the default backend choices.
- Use a small browser application for the demo console. React + TypeScript + Vite is preferred, but plain TypeScript is acceptable if it keeps the POC simpler.
- Use SQLite or in-memory repositories for demo persistence. Do not introduce a production database unless a later decision requires it.
- Prefer typed domain objects over unstructured dictionaries.
- Keep prompts versioned in source control and validate all LLM output against a schema.
- Unit-test policy decisions without calling an LLM or speech provider.
- Scenario tests must run through text mode and assert both final outcome and forbidden disclosures.
- Provide `.env.example`; never commit `.env` or secrets.
- Add `make dev`, `make test`, and `make demo-reset` (or cross-platform equivalents documented in the README) before declaring the POC complete.

## Definition of done

An implementation milestone is complete only when its tests pass, its documented demo path works from a clean checkout, and the event log makes the behavior explainable.
