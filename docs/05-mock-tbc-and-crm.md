# Mock TBC and CRM specification

## 1. Purpose

`mock_tbc` emulates the Bank-owned services required by the voice agent. It is intentionally a separate API process so integration boundaries, errors, latency, retries, and idempotency are visible in the demo.

It is not a realistic core-banking system and must never be connected to real customer data.

## 2. Mock capabilities

### Campaign service

Returns the available synthetic campaigns and the customer references in each campaign. A campaign supplies language, calling window, policy version, identity question set, and content version.

### Pre-call context

Returns only information safe before verification:

```json
{
  "customer_ref": "cust-001",
  "display_name": "Alex Morgan",
  "preferred_language": "en-US",
  "contact_allowed": true,
  "campaign_id": "campaign-en-001",
  "policy_version": "poc-v1"
}
```

No balance, overdue status, due date, offer, or debt-purpose field may appear here.

### Identity service

Accepts normalized synthetic answers and returns:

```json
{
  "status": "verified",
  "evidence_ref": "idv_01...",
  "verification_token": "short-lived-session-bound-token",
  "expires_at": "2026-08-14T18:30:00Z"
}
```

The token is bound to session and customer. Protected endpoints reject a missing, expired, or mismatched token.

### Collections context

Returns synthetic balance, due date, account state, prior claim/PTP indicators, and policy references after verification.

### Eligible offers

Returns zero or more versioned offers. The policy engine treats this response as exhaustive.

### Outcome service

Stores the final structured disposition. Reusing the same idempotency key with the same payload returns the original result. Reusing it with a different payload returns `409 IDEMPOTENCY_CONFLICT`.

### Payment-link service

Returns a synthetic request reference and delivery status. It must not return a realistic clickable payment URL. A display value such as `https://payments.invalid/demo/...` is acceptable only if clearly non-routable.

### Transfer service

Accepts route, reason, priority, verification state, and a structured summary. It can respond `accepted`, `queue_unavailable`, or `callback_created`.

## 3. Required fixtures

| Customer | Designed path | Important data |
|---|---|---|
| `cust-001` Alex Morgan | Happy-path PTP | Verified answers, one overdue balance, valid PTP range |
| `cust-002` Jordan Lee | Payment plan | Two approved offers; one expires during a test fixture |
| `cust-003` Casey Brown | Already-paid claim | No assistant confirmation allowed |
| `cust-004` Taylor Smith | Hardship escalation | Human queue available |
| `cust-005` Morgan Reed | Stop-contact | Suppression write must occur |
| `cust-006` Jamie Wilson | Wrong party/failed identity | No protected context may be fetched |
| `cust-007` Riley Davis | Technical failure | Context endpoint configured to fail |

Fixture values should be obviously synthetic and easy to pronounce. Use `.invalid` domains and non-routable telephone examples.

## 4. Example protected context

```json
{
  "customer_ref": "cust-001",
  "account_ref": "demo-account-001",
  "balance": {"amount": "275.40", "currency": "GEL"},
  "due_date": "2026-08-10",
  "days_past_due": 4,
  "ptp_policy": {
    "minimum_amount": "25.00",
    "maximum_date": "2026-09-13"
  },
  "offer_refs": ["offer-001"],
  "context_version": "ctx-3"
}
```

## 5. Failure injection

The operator panel can enable failures per session or globally:

```text
identity_timeout
context_timeout
context_500
offers_timeout
outcome_fail_once
outcome_permanent_failure
payment_link_rejected
transfer_queue_unavailable
high_latency
```

`outcome_fail_once` is mandatory because it demonstrates retry plus idempotency. Failure injection must be disabled by default and clearly visible in the UI.

## 6. State and reset

The mock stores outcomes, payment requests, transfers, suppression requests, and idempotency records in SQLite or memory. `POST /v1/admin/reset` restores the committed fixture baseline.

The reset operation is local-development-only and must not be exposed when a non-local bind address is used.

## 7. Mock authentication

Use a static development bearer token between the voice API and mock TBC, loaded from `.env`. This is only to exercise authentication plumbing. The web browser must never call protected mock endpoints directly or receive the token.

## 8. Contract tests

Contract tests must verify:

- Pre-call context contains no protected fields.
- Protected endpoints reject invalid verification tokens.
- Tokens cannot be reused for a different session/customer.
- Outcomes are idempotent.
- Conflicting idempotent writes return a conflict.
- Offer validity is enforced.
- Failure modes return stable error codes and retry guidance.
- Reset restores fixture data and clears writes.
