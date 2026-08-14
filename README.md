# TBC Voice Agent POC

This repository contains the source proposal and the implementation specifications for a proof-of-concept outbound collections voice assistant.

The POC is intentionally safe and small:

- TBC telephony, CRM, policy, payment-link, and human-agent systems are mocked.
- The demo runs from a browser microphone instead of a real telephone network.
- The first working language is English.
- Conversation decisions are made by deterministic policy code, not by the language model.
- All customers, balances, and offers are synthetic.
- Speech, model, and transport providers sit behind adapters so they can be replaced.

The goal is to prove the conversation loop and the control boundaries—not to simulate a production debt-collection deployment.

## Start here

Future implementation agents should read the documents in this order:

1. [Document map and vocabulary](docs/00-document-map.md)
2. [Vision and scope](docs/01-vision-and-scope.md)
3. [Technical specification](docs/02-technical-specification.md)
4. [Service contracts and events](docs/03-service-contracts-and-events.md)
5. [Conversation and policy specification](docs/04-conversation-and-policy.md)
6. [Mock TBC and CRM specification](docs/05-mock-tbc-and-crm.md)
7. [Security and data handling](docs/06-security-and-data-handling.md)
8. [Georgian language readiness](docs/07-georgian-language-readiness.md)
9. [Build plan for AI agents](docs/08-agent-build-plan.md)
10. [Demo script and acceptance criteria](docs/09-demo-and-acceptance.md)

[AGENTS.md](AGENTS.md) contains repository-level rules for coding agents, and [the decision log](docs/10-decisions.md) records deliberate POC simplifications.

## Target POC experience

An operator selects a synthetic customer and starts a simulated outbound call. The browser connects the microphone to the orchestrator. The assistant verifies identity before disclosing account information, gives an approved reminder, handles one of a limited set of scenarios, and either records an outcome, requests a mocked payment link, or transfers to a mocked human queue.

The operator can see a live event timeline showing transcripts, state transitions, policy decisions, mocked CRM calls, latency, and the final disposition.

## Source material

The original technical and commercial proposal is retained under [`work/`](work/). The Markdown specifications are the build authority for the POC; where they intentionally simplify the proposal, the simplification is called out explicitly.
