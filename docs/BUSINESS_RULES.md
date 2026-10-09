# Owner Rules and Safety Behavior

This application implements the complete owner-provided Bengali business-rules document at `Pasted markdown(20261008-231332).md` as reconciled with the explicit project directives. Historical audit statistics in that document are not demo data and have not been independently verified by this application.

## Identity

- Explicit, normalized Escort Mobile is the operational matching key.
- `employee_id` retains the project directive's operational mobile-number meaning; immutable internal key is separately named `person_uid`.
- Same normalized mobile and varying names may create aliases. Same name on different mobile numbers is separate.
- Sender, Master, Client, payout and WhatsApp JID/LID are separate contact roles and never infer Escort Mobile.
- Historical source references are retained. Reassigned-number ownership remains unresolved and must go to manual identity review; no history rewrite or automatic reassignment occurs.

The attached rules document suggests an immutable internal `employee_id`, while the project directive explicitly preserves operational `employee_id` as mobile. This implementation reconciles them by retaining operational `employee_id` and adding `person_uid` as the internal immutable identifier. The two fields are not interchangeable.

## Orders, confirmation and programs

- Client order creates Draft; incomplete extraction persists as Draft/Review.
- Admin Confirmation requires authenticated Admin/Superadmin role, explicit Escort Name/Mobile, Mother/Lighter, Duty Start Date and Shift. Message syntax alone confers no authority.
- Message Date is separate from Duty Start Date.
- One Mother Vessel can have many separate Lighter programs.
- Exact repeat, up-to-three-day matching details, and under-five-day repeated lighter are review classifications only. They do not auto-cancel or delete.
- A new confirmed assignment under a mobile with an open prior assignment creates a closure-review candidate. It does not invent prior end date, duty days or salary.
- Corrections, cancellation, replacement and restart retain prior evidence and require explicit review/evidence.

## Release and completion

- Upload/manual slip intake creates a pending review and does not verify release.
- Original local upload and source reference are preserved. Current implementation does not run OCR.
- Verified Release, Program Completion, Settlement Approval and Payment Completion are separate statuses.
- Program completion requires prior Released status and explicit verified completion date.

## Ghat Duty and settlement

- BDT 200 evidence creates a review candidate; three consecutive calendar days raise priority.
- Payment instruction and verified-transfer labels remain distinct. The pattern does not finalize attendance, cash, payroll or settlement.
- No BDT 400 daily rate or other default salary policy is assumed. Settlement requires explicitly provided days and rate; missing values stay review-required.
- Demo settlement/payment data never posts to a financial ledger.

## Configuration and unresolved policy

Phone reassignment, OCR engine/accuracy, exact date-window inclusivity outside code's conservative ranges, duty day/shift counting, salary rounding/deduction policy, and full production role mapping need owner confirmation before operational integration. Current date matching treats exact date as duplicate candidate, 1-3 days as correction review, and 4 days as under-five-day restart review; five or more days may be new. These are configurable-domain decisions to review, not authoritative cancellation commands.
