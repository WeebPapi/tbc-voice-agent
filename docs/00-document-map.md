# Document map

| Document | Purpose | Primary reader |
|---|---|---|
| `01-vision-and-scope.md` | Product intent, boundaries, actors, and success measures | Product, architecture, delivery agents |
| `02-technical-specification.md` | Target POC architecture, components, runtime, and repository design | Backend and frontend agents |
| `03-service-contracts-and-events.md` | HTTP/WebSocket contracts, domain schemas, and event vocabulary | Integration and test agents |
| `04-conversation-and-policy.md` | State machine, disclosure gate, scenario rules, and LLM limits | Conversation, policy, and QA agents |
| `05-mock-tbc-and-crm.md` | Synthetic Bank services, fixture data, and failure injection | Mock-service and integration agents |
| `06-security-and-data-handling.md` | POC security controls and production gaps | Security and platform agents |
| `07-georgian-language-readiness.md` | Path from English demo to Georgian telephone quality | Voice, language, and QA agents |
| `08-agent-build-plan.md` | Ordered work packages with dependencies and hand-offs | Coordinating and implementation agents |
| `09-demo-and-acceptance.md` | Demo script, observable acceptance criteria, and test matrix | QA, stakeholders, demo operator |
| `10-decisions.md` | Architecture decisions and intentional deviations | All agents |

## Shared vocabulary

- **Assistant:** the complete voice-agent experience.
- **Orchestrator:** coordinates audio turns, state, tools, and service calls.
- **Policy engine:** deterministic code that permits or rejects protected actions.
- **LLM:** language model used for constrained understanding and wording.
- **Mock TBC:** local service emulating Bank-owned CRM, policy, SMS, and transfer capabilities.
- **Disclosure:** revealing account, debt, balance, overdue, payment, or offer information.
- **Disposition:** final structured outcome of a call.
- **PTP:** promise to pay, including a confirmed amount and date.
- **Fail closed:** take the safer action when a required system or decision is unavailable.
