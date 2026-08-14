# Conversation and policy specification

## 1. Separation of responsibilities

| Capability | Orchestrator | Policy engine | LLM | Mock TBC |
|---|---:|---:|---:|---:|
| Track current conversation state | Owner | Validates transitions | No | No |
| Verify identity | Coordinates | Decides how result affects flow | No | Evaluates synthetic answers |
| Decide what can be disclosed | Requests decision | Owner | No | Supplies protected facts |
| Classify customer language | Coordinates | Uses structured intent | Assists | No |
| Determine eligible offers | No | Enforces returned set | No | Owner |
| Draft natural wording | Coordinates | Constrains facts/action | Owner | No |
| Confirm PTP validity | Coordinates | Owner | Extracts candidate slots | Supplies limits/context |
| Persist final outcome | Coordinates | Requires correct evidence | No | Owner |

The LLM never receives a role that contains “decide whether allowed.” It proposes an intent, slots, and wording. Code validates each of those outputs.

## 2. Conversation states

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> VERIFYING_IDENTITY: session starts
    VERIFYING_IDENTITY --> VERIFIED: identity succeeds
    VERIFYING_IDENTITY --> TERMINATED: wrong party or attempts exhausted
    VERIFIED --> REMINDER: protected context loaded
    REMINDER --> DISCUSSING_OPTIONS: customer engages
    REMINDER --> ESCALATING: protected scenario
    DISCUSSING_OPTIONS --> CONFIRMING_PTP: valid amount/date captured
    DISCUSSING_OPTIONS --> REQUESTING_PAYMENT_LINK: approved request
    DISCUSSING_OPTIONS --> ESCALATING: dispute, hardship, or unsupported request
    CONFIRMING_PTP --> COMPLETED: explicit confirmation and write-back
    CONFIRMING_PTP --> DISCUSSING_OPTIONS: customer corrects details
    REQUESTING_PAYMENT_LINK --> COMPLETED: Bank mock accepts request
    ESCALATING --> COMPLETED: transfer or callback recorded
    VERIFIED --> TERMINATED: stop-contact or technical failure
    REMINDER --> TERMINATED: customer ends
    COMPLETED --> [*]
    TERMINATED --> [*]
```

Every transition must be explicit in code. An LLM cannot name an arbitrary next state.

## 3. Disclosure classes

### Pre-verification content

Allowed:

- Neutral greeting.
- Bank identity, if approved for the POC script.
- Request to speak to the named synthetic person without stating the purpose.
- Approved identity questions.
- Neutral wrong-party or failed-verification closing.

Forbidden:

- Debt or collections purpose.
- Balance, overdue status, due date, creditor/account details.
- Offers, payment plans, payment links, or prior payment behavior.

### Post-verification content

Only facts returned by the protected mock context and listed in the latest policy decision may be spoken. The response validator should reject monetary values, dates, and offer identifiers that do not match permitted facts.

## 4. Identity flow

POC question set:

1. Confirm that the respondent is the named synthetic customer.
2. Ask for birth day and month.
3. Ask for the last four characters of the synthetic customer identifier.

The mock TBC service evaluates normalized values and returns only `verified`, `failed`, or `locked`, plus an evidence reference. Raw answers are not retained in the event log.

Rules:

- Maximum two failed attempts.
- A wrong-party statement ends immediately and neutrally.
- Ambiguous or low-confidence critical speech is confirmed before submission.
- A service timeout is not a failed identity; it is a technical failure and closes without disclosure.
- The POC does not imply that this method is sufficient for production.

## 5. Required scenario behavior

| Scenario | Deterministic action | Final disposition |
|---|---|---|
| Verified customer, reminder only | State approved balance/due information; close politely | `VERIFIED_REMINDER` |
| Failed identity | Retry once, then neutral close | `ID_FAILED` |
| Wrong party | Do not state purpose; close | `WRONG_PARTY` |
| Already paid | Acknowledge claim without confirming settlement; record for reconciliation | `ALREADY_PAID_CLAIMED` |
| PTP | Validate amount/date, read back, require explicit yes, write once | `PTP_CAPTURED` |
| Payment plan | Present only offer IDs returned by mock TBC | `PLAN_ACCEPTED` or escalation |
| Payment link | Request through mock TBC; do not generate a link in the assistant | `PAYMENT_LINK_REQUESTED` |
| Dispute | Stop collection discussion and request priority transfer | `DISPUTE_ESCALATED` |
| Hardship/vulnerability | Use approved empathetic phrase; stop negotiation; transfer | `VULNERABILITY_ESCALATED` |
| Stop-contact | Acknowledge, record suppression request, end | `STOP_CONTACT` |
| Unsupported discount | Explain inability to change terms; offer approved options or transfer | scenario-dependent |
| CRM/policy unavailable | No disclosure or negotiation; safe close | `TECHNICAL_FAILURE` |
| Repeated low-confidence speech | Clarify within limit, then transfer or close | `LOW_CONFIDENCE` |

## 6. PTP rules

A promise to pay is valid only when all of the following are true:

- Identity is verified.
- Currency is GEL.
- Amount is positive and within mock policy bounds.
- Date is valid, not in the past, and not beyond the configured maximum horizon.
- The assistant has read the normalized amount and date back to the customer.
- The customer gives an explicit affirmative response to that read-back.
- The outcome write succeeds or is safely queued for retry with the same idempotency key.

Statements such as “I should be able to,” “probably,” or silence are not confirmation.

## 7. Offer rules

- The assistant may mention only offers returned for the current verified customer.
- Each offer has an ID, validity window, payment schedule, and display text.
- Expired offers are rejected even if they remain in conversation history.
- The LLM may simplify approved display text but may not alter amount, count, date, interest, fee, or eligibility.
- If the customer asks for different terms, the assistant offers an approved alternative or transfers.

## 8. Response construction

Preferred pipeline:

1. Classify the user turn and extract candidate slots.
2. Run a deterministic policy decision.
3. Build an LLM context containing only permitted facts and actions.
4. Validate the structured LLM result.
5. Scan critical values in `response_text` against the permitted fact set.
6. Use a deterministic template if validation fails.
7. Send only the approved final text to TTS.

For pre-verification and safety-critical closings, deterministic templates are preferred over generated wording.

## 9. Prompt requirements

The system prompt must state:

- The current state and allowed intents.
- That supplied facts are exhaustive, not examples.
- That the model must never invent values or offers.
- That it must return the required schema.
- That it must not treat customer instructions as system instructions.
- That it must keep responses brief and suitable for speech.

Prompt injection, abusive language, or requests to ignore policy are classified as customer content; they do not modify system behavior.

## 10. Initial English content

Content should be concise, calm, and non-accusatory. Store scripts by stable keys such as:

```text
greeting_neutral
identity_question_birth_day_month
identity_question_customer_id_last4
identity_failed_retry
identity_failed_close
reminder_verified
ptp_readback
payment_link_acknowledged
dispute_transfer
hardship_transfer
stop_contact_close
technical_failure_close
```

Each content version records language, author, approval status, and effective date. The POC may seed these as source-controlled fixtures.
