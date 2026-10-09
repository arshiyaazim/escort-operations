# Future Integration Contracts (Unimplemented)

No production endpoints, credentials or service APIs were inferred. These are adapter boundaries only and remain disabled.

| Adapter | Proposed contract scope | Required future verification |
|---|---|---|
| Identity/directory | Read verified employee/client identity, aliases, contact roles and source links | Field mapping, mobile ownership history, authorization and conflict resolution. |
| Message evidence | Read message ID, sender/recipient role, direction, timestamp, content/media reference | Authenticated origin, deduplication, retention, privacy and authorized read scope. No listener is proposed. |
| Release media | Resolve an authorized stored media reference | Access control, integrity hash, retention and allowed file types. |
| Cash Control | Submit approved settlement through the authorized financial authority | Exact API, idempotency, approval chain, reversal and production authorization. Never write directly to a competing ledger. |
| Payroll | Request/show authorized salary calculation or payment status | Payroll authority, calculation policy, reconciliation and duplicate-post protection. |

All future write adapters must default disabled, require explicit production authorization, record immutable source/actor references, support idempotency, and be tested against isolated fakes before any live use.
