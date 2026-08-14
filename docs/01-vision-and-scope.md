# Vision and scope

## Vision

Demonstrate that a Georgian-capable AI voice assistant can conduct a useful outbound soft-collections conversation while keeping sensitive decisions under explicit Bank control.

The POC should make three things obvious to a viewer:

1. The conversation can feel responsive and natural.
2. The assistant cannot disclose or negotiate outside deterministic rules.
3. Every important action can be traced back to an input, rule, and system event.

The first version uses English so the team can validate the architecture and scenario behavior quickly. The design must make Georgian a provider/configuration change plus a focused language-quality workstream, not a rewrite.

## Product principles

### Bank systems remain authoritative

The mocked TBC services stand in for the future sources of customer context, identity decisions, eligible offers, payment links, and final records. The assistant does not maintain an independent version of banking truth.

### Natural language is not policy

The language model can interpret a customer turn and draft a response. Deterministic code controls identity, disclosure, offers, confirmation, escalation, and termination.

### Safe failure is visible

If a critical dependency fails, the demo should visibly show the assistant withholding protected information, selecting a safe response, and recording a technical outcome.

### The POC is replaceable by design

Browser audio stands in for SIP telephony. Mock APIs stand in for TBC APIs. Provider adapters stand in front of speech and model vendors. These boundaries let each mock be replaced independently.

### Text mode is a first-class capability

Voice is required for the stakeholder demo, but every conversation scenario must also run in a deterministic text-mode harness. This makes policy and regression testing possible without microphones, network timing, or paid providers.

## In scope

- Synthetic outbound campaign/customer selection.
- Browser microphone and speaker as a simulated call transport.
- Streaming or near-streaming speech recognition and synthesis.
- An orchestrator that handles turns, interruptions, timeouts, tool calls, and state.
- Deterministic identity and disclosure gating.
- Friendly reminder after successful identity verification.
- Promise-to-pay capture with amount/date validation and explicit read-back.
- One eligible payment-plan path based only on mock TBC offers.
- Mocked TBC payment-link request and delivery status.
- Dispute, hardship, stop-contact, wrong-party, low-confidence, and technical-failure paths.
- Mocked warm transfer with a structured hand-off summary.
- Structured event timeline and basic operational dashboard.
- English prompts and voices initially.
- Georgian readiness plan, normalization rules, test corpus design, and provider adapter support.

## Out of scope

- Real telephone numbers, carriers, SIP trunks, diallers, or production contact-centre routing.
- Real TBC connectivity or customer information.
- Payment processing or generation of real payment credentials.
- Voice biometrics.
- Autonomous credit decisions, discounts, fee waivers, settlements, or legal collections.
- Production-grade identity verification.
- A complete business-user configuration portal; a developer/demo control panel is sufficient.
- Full enterprise reporting, data warehousing, high availability, disaster recovery, or regulatory certification.
- Public internet deployment.
- Claims that the selected speech providers meet Georgian quality or Bank security requirements before benchmarking and approval.

## Actors

| Actor | POC responsibility |
|---|---|
| Demo operator | Selects a fixture, starts/resets a call, watches events, and injects failures |
| Synthetic customer | Speaks or types customer responses |
| Voice assistant | Conducts the controlled conversation |
| Mock TBC services | Supply customer context, policy, offers, SMS, outcome storage, and transfer routing |
| Human-agent simulator | Receives the transfer summary and marks the transfer accepted or unavailable |
| Developer/QA | Runs text scenarios, inspects events, and verifies forbidden behavior never occurs |

## Success measures

The POC succeeds when:

- All mandatory scenarios in `09-demo-and-acceptance.md` pass in text mode.
- At least the happy path and one escalation path work with browser voice.
- No protected data is emitted before identity verification in any automated test.
- No offer absent from the mock TBC response is spoken or recorded.
- A confirmed PTP is written once even when the outcome request is retried.
- A viewer can follow the call through state, transcript, policy, integration, and final-outcome events.
- Provider credentials are optional for the text-only development loop.
- The Georgian workstream has measurable entry criteria rather than a simple prompt translation.

## POC versus production

This POC validates boundaries and behavior. Production would additionally require real SIP/media integration, TBC-approved authentication and networking, provider due diligence, data residency and retention decisions, load and recovery engineering, penetration testing, formal Georgian benchmarking, audit integration, and operational readiness approval.
