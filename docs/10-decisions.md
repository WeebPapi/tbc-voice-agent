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

## Decision template

```markdown
## ADR-NNN — Title

**Status:** Proposed | Accepted | Superseded

**Decision:** What changes or is fixed.

**Reason:** Why this choice is appropriate.

**Consequences:** Important trade-offs, migrations, or new tests.
```
