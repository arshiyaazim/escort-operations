# Escort Operations

Independent, synthetic-data-first application for the Escort Service Order → Draft → Admin Confirmation → Program → Assignment → Duty → Release → Ghat Duty → Completion → Settlement Review lifecycle.

This repository is separate from Fazle-Core. It does not import Fazle-Core modules, connect to production services/databases, run a WhatsApp listener, or post financial transactions. All included demo records and demo role tokens are synthetic and unsuitable for production authentication.

## Requirements

- Python 3.11+ (CI currently uses Python 3.12)
- `pip`

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`. The app creates `data/escort-demo.sqlite3` and seeds synthetic employees, aliases, client, vessels, order, confirmed program and assignment. Choose a demo role in the sidebar. API documentation is at `/docs`.

The database can be reset by stopping the server and deleting the local ignored `data/escort-demo.sqlite3`; startup recreates it. Only use synthetic evidence/media in this demo. Uploads are retained locally under ignored `data/uploads/`.

## Demo roles

These static tokens are for isolated local demonstration only and must never be deployed or treated as secure credentials:

| Role | Token |
|---|---|
| Viewer | `demo-viewer` |
| Operations Officer | `demo-ops` |
| Accountant/Settlement Reviewer | `demo-accountant` |
| Admin | `demo-admin` |
| Superadmin | `demo-superadmin` |

Every API request requires `Authorization: Bearer <token>`. The backend enforces role thresholds. Admin confirmation, program decisions, release verification and completion approval require Admin or Superadmin. Settlement actions require Accountant or higher.

## Implemented workflows

- Labeled order intake preserves raw text/source reference and creates Draft even when fields are incomplete; incomplete details create a review item.
- Admin confirmation normalizes explicit Escort Mobile only, checks candidate program matches, records aliases on same-mobile name variation, and creates a separate program per lighter. Candidate collisions go to review; no date-window rule cancels or deletes a program.
- Assignment and duty start are persisted through API actions. New assignment confirmations generate closure-review candidates when the same employee has an open prior assignment.
- Program correction/cancellation/replacement are review workflows. Cancellation and correction require linked source evidence; replacement requires verified dates and evidence. A replacement does not infer salary or release.
- Release slip metadata/manual text and image/PDF upload are retained locally and create pending verification. Upload does not change program status. Admin release approval requires a verified date; completion is a separate approval and requires Released status and its own date.
- BDT 200/day evidence creates Ghat Duty review. Three consecutive calendar days raise priority. No attendance/payroll/cash posting occurs.
- Settlement preview has no default daily rate. Missing rate/days requires review. Approval requires a completed program and explicit calculated amount; synthetic payment completion remains separate and cannot post to production.
- Audit events link actions to source evidence IDs; source evidence is immutable by API design.

## Tests

```powershell
py -m unittest discover -s tests -v
```

Tests cover identity normalization/separation, Mother/Lighter program matching, three-/five-day classification, BDT 200 review pattern and no invented salary rate. API integration tests should run in a clean environment after installing the pinned-compatible requirements; verify authorization and transitions before any production consideration.

## Data and identity rules

The application uses normalized Escort Mobile as the operational matching key. It preserves the owner system's operational mobile-ID semantics in `employee_id`, with a separate immutable `person_uid` for internal references. This adopts the explicit project directive's field meaning while preserving the attached document's need for an immutable internal identifier. Phone reassignment remains unresolved and must be reviewed; this demo does not implement historical ownership periods. Names are aliases only when the same normalized Escort Mobile is explicit; matching names across numbers never merges people.

Message date and duty start date are separate fields. Program matching considers Mother Vessel, Lighter Vessel, Escort Mobile, Duty Start Date, Shift and status. Same Mother Vessel does not imply duplicate. Three-day and under-five-day rules classify review candidates only. No salary rate, duty dates, attendance or release date is inferred.

## Known limitations

- OCR extraction is not integrated. Image/PDF uploads preserve bytes and create a review; fields must be manually entered/verified.
- Demo role tokens are deliberately insecure and local-only. Production-grade authentication, secrets, rate limiting and deployment hardening are not implemented.
- SQLite is for isolated development/demo. Concurrency/multi-user operational deployment has not been verified.
- Domain rules are conservative and label parsing is not equivalent to Fazle-Core's complete bilingual production parser.
- Some review resolutions require explicit fields through API; the UI currently offers basic approve/defer and does not expose every correction/cancellation/replacement detail form.
- The owner document leaves phone-number reassignment policy unresolved; identity ownership periods are not implemented.
- Integration adapter interfaces/contracts are proposals only; no production endpoints or adapters are enabled.

See `docs/` for business rules, data model and future adapter boundaries.
