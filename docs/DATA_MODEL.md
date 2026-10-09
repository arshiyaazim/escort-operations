# Data Model

SQLite schema is defined in `backend/main.py` and initialized locally. Operational records are deliberately small and normalized for the standalone demo.

| Tables | Responsibility |
|---|---|
| `employees`, `employee_aliases` | Operational normalized mobile identifier and preserved name variations; `person_uid` is internal identity key. |
| `clients`, `vessels` | Synthetic client and vessel directories; vessel type distinguishes mother/lighter. |
| `source_evidence` | Source reference, timestamp, role, original text/media filename and synthetic provenance. Unique `(kind, source_ref)` prevents same-kind replay. |
| `orders` | Draft lifecycle, client, vessel/contact/date fields, extracted details and status. |
| `programs`, `assignments` | Confirmed operations and separately retained escort assignment intervals/replacement links. |
| `release_slips` | OCR/manual fields, confidence, original evidence link and verification state. |
| `ghat_evidence` | Amount/date/evidence classification and review state. |
| `reviews` | Shared review queue for incomplete, duplicate/correction, cancellation, replacement, release, completion and Ghat decisions. |
| `settlements` | Synthetic-only calculation preview and independent review status. |
| `audit_events` | Append-only actor/action/evidence trail for application operations. |

No payroll ledger, cash ledger or production migration is included. SQLite is a demo-only persistence choice and is not yet validated for concurrent production use.
