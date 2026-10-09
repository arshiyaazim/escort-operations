from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.domain import can_complete, can_release, classify_program, consecutive_200_days, ghat_candidate, normalize_mobile, parse_order, role_allows, settlement_preview

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("ESCORT_DB", ROOT / "data" / "escort-demo.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Escort Operations", version="1.0.0", description="Standalone synthetic Escort Operations lifecycle")

ROLES = {"viewer": 0, "operations_officer": 1, "accountant": 2, "admin": 3, "superadmin": 4}
TOKENS = {"demo-viewer": "viewer", "demo-ops": "operations_officer", "demo-accountant": "accountant", "demo-admin": "admin", "demo-superadmin": "superadmin"}


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees(person_uid TEXT PRIMARY KEY, employee_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS employee_aliases(id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(employee_id), name TEXT NOT NULL, evidence_id TEXT, UNIQUE(employee_id,name));
CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY,name TEXT NOT NULL,mobile TEXT,synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS vessels(id TEXT PRIMARY KEY,name TEXT NOT NULL,vessel_type TEXT NOT NULL CHECK(vessel_type IN ('mother','lighter')),synthetic INTEGER NOT NULL DEFAULT 1,UNIQUE(name,vessel_type));
CREATE TABLE IF NOT EXISTS source_evidence(id TEXT PRIMARY KEY,kind TEXT NOT NULL,source_ref TEXT NOT NULL,occurred_at TEXT NOT NULL,actor_ref TEXT,raw_text TEXT,media_name TEXT,synthetic INTEGER NOT NULL DEFAULT 1,UNIQUE(kind,source_ref));
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,client_id TEXT REFERENCES clients(id),mother_vessel TEXT,lighter_vessel TEXT,master_mobile TEXT,message_date TEXT,duty_start_date TEXT,shift TEXT,requested_count INTEGER,details TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'draft',created_at TEXT NOT NULL,source_evidence_id TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS order_evidence_links(order_id TEXT NOT NULL REFERENCES orders(id),evidence_id TEXT NOT NULL REFERENCES source_evidence(id),role TEXT NOT NULL,PRIMARY KEY(order_id,evidence_id));
CREATE TABLE IF NOT EXISTS programs(id TEXT PRIMARY KEY,order_id TEXT REFERENCES orders(id),mother_vessel TEXT NOT NULL,lighter_vessel TEXT NOT NULL,escort_mobile TEXT,escort_name TEXT,duty_start_date TEXT,shift TEXT,master_mobile TEXT,status TEXT NOT NULL,release_date TEXT,completion_date TEXT,settlement_status TEXT NOT NULL DEFAULT 'not_started',payment_status TEXT NOT NULL DEFAULT 'not_paid',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assignments(id TEXT PRIMARY KEY,program_id TEXT NOT NULL REFERENCES programs(id),employee_id TEXT NOT NULL REFERENCES employees(employee_id),start_date TEXT,shift TEXT,end_date TEXT,status TEXT NOT NULL,predecessor_id TEXT REFERENCES assignments(id));
CREATE TABLE IF NOT EXISTS duty_evidence(id TEXT PRIMARY KEY,program_id TEXT NOT NULL REFERENCES programs(id),evidence_id TEXT NOT NULL REFERENCES source_evidence(id),evidence_type TEXT NOT NULL,occurred_at TEXT NOT NULL,verification_status TEXT NOT NULL DEFAULT 'pending_review');
CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',summary TEXT NOT NULL,evidence_id TEXT,program_id TEXT,details TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS release_slips(id TEXT PRIMARY KEY,program_id TEXT,escort_mobile TEXT,release_date TEXT,shift TEXT,total_duty TEXT,salary TEXT,conveyance TEXT,location TEXT,ocr_text TEXT,confidence REAL,verification_status TEXT NOT NULL DEFAULT 'pending_review',evidence_id TEXT NOT NULL REFERENCES source_evidence(id),created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ghat_evidence(id TEXT PRIMARY KEY,employee_id TEXT,day TEXT NOT NULL,amount INTEGER NOT NULL,evidence_id TEXT NOT NULL REFERENCES source_evidence(id),evidence_kind TEXT NOT NULL,review_status TEXT NOT NULL DEFAULT 'pending_review');
CREATE TABLE IF NOT EXISTS settlements(id TEXT PRIMARY KEY,program_id TEXT NOT NULL REFERENCES programs(id),duty_days REAL,daily_rate REAL,deductions REAL,preview_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'review_required',synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,action TEXT NOT NULL,actor_role TEXT NOT NULL,occurred_at TEXT NOT NULL,details TEXT NOT NULL,evidence_id TEXT);
"""


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            seed(conn)


def seed(conn):
    now = datetime.now(timezone.utc).isoformat()
    demo = [
        ("p_demo_1", "01800000000", "Synthetic Hridoy"),
        ("p_demo_2", "01700000000", "Synthetic Hridoy"),
        ("p_demo_3", "01900000000", "Synthetic Rafi"),
    ]
    conn.executemany("INSERT INTO employees(person_uid,employee_id,name) VALUES(?,?,?)", demo)
    conn.execute("INSERT INTO employee_aliases(employee_id,name) VALUES('01800000000','Synthetic Md Hridoy')")
    conn.executemany("INSERT INTO clients(id,name,mobile) VALUES(?,?,?)", [("client-demo", "Synthetic River Trading", "01900000001")])
    conn.executemany("INSERT INTO vessels(id,name,vessel_type) VALUES(?,?,?)", [("mv-demo", "MV DEMO STAR", "mother"), ("lv-demo-a", "DEMO LIGHTER A", "lighter"), ("lv-demo-b", "DEMO LIGHTER B", "lighter")])
    conn.execute("INSERT INTO orders(id,client_id,mother_vessel,lighter_vessel,master_mobile,message_date,duty_start_date,shift,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("order-demo", "client-demo", "MV DEMO STAR", "DEMO LIGHTER A", "01600000000", now[:10], "2026-10-10", "D", "confirmed", now))
    conn.execute("INSERT INTO programs(id,order_id,mother_vessel,lighter_vessel,escort_mobile,escort_name,duty_start_date,shift,master_mobile,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("program-demo", "order-demo", "MV DEMO STAR", "DEMO LIGHTER A", "01800000000", "Synthetic Hridoy", "2026-10-10", "D", "01600000000", "confirmed", now))
    conn.execute("INSERT INTO assignments(id,program_id,employee_id,start_date,shift,status) VALUES(?,?,?,?,?,?)", ("assignment-demo", "program-demo", "01800000000", "2026-10-10", "D", "assigned"))
    conn.execute("INSERT INTO orders(id,client_id,mother_vessel,lighter_vessel,master_mobile,message_date,duty_start_date,shift,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("order-demo-b", "client-demo", "MV DEMO STAR", "DEMO LIGHTER B", "01600000001", now[:10], "2026-10-11", "N", "confirmed", now))
    conn.execute("INSERT INTO programs(id,order_id,mother_vessel,lighter_vessel,escort_mobile,escort_name,duty_start_date,shift,master_mobile,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("program-demo-b", "order-demo-b", "MV DEMO STAR", "DEMO LIGHTER B", "01700000000", "Synthetic Hridoy", "2026-10-11", "N", "01600000001", "confirmed", now))
    conn.execute("INSERT INTO assignments(id,program_id,employee_id,start_date,shift,status) VALUES(?,?,?,?,?,?)", ("assignment-demo-b", "program-demo-b", "01700000000", "2026-10-11", "N", "assigned"))
    conn.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), "program", "program-demo", "synthetic_seed", "system", now, json.dumps({"synthetic": True}), None))


init_db()


def actor(authorization: str | None = Header(default=None)) -> str:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    role = TOKENS.get(token)
    if not role:
        raise HTTPException(401, "Use a documented standalone demo role token")
    return role


def require(minimum: str):
    def dependency(role: str = Depends(actor)):
        if not role_allows(role, minimum):
            raise HTTPException(403, f"{minimum} role required")
        return role
    return dependency


def audit(conn, entity_type, entity_id, action, role, details=None, evidence_id=None):
    conn.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), entity_type, entity_id, action, role, datetime.now(timezone.utc).isoformat(), json.dumps(details or {}, ensure_ascii=False), evidence_id))


class OrderIn(BaseModel):
    raw_text: str = ""
    client_id: str | None = None
    mother_vessel: str | None = None
    lighter_vessel: str | None = None
    master_mobile: str | None = None
    message_date: str | None = None
    duty_start_date: str | None = None
    shift: str | None = None
    requested_count: int | None = Field(default=None, ge=1)
    source_ref: str = Field(min_length=1)


class ConfirmIn(BaseModel):
    escort_name: str = Field(min_length=1)
    escort_mobile: str
    duty_start_date: str
    shift: str
    mother_vessel: str = Field(min_length=1)
    lighter_vessel: str = Field(min_length=1)
    master_mobile: str | None = None
    source_ref: str
    message_date: str | None = None


class ReleaseIn(BaseModel):
    source_ref: str
    release_date: str | None = None
    shift: str | None = None
    total_duty: str | None = None
    salary: str | None = None
    conveyance: str | None = None
    location: str | None = None
    ocr_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    media_name: str | None = None


class GhatIn(BaseModel):
    employee_mobile: str
    day: str
    amount: int = 200
    evidence_ref: str
    evidence_kind: str = "payment_instruction"


class SettlementIn(BaseModel):
    duty_days: float | None = Field(default=None, ge=0)
    daily_rate: float | None = Field(default=None, ge=0)
    deductions: float | None = Field(default=None, ge=0)


class DutyEvidenceIn(BaseModel):
    evidence_ref: str
    occurred_at: str
    evidence_type: str = "attendance_or_movement"


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "standalone_synthetic", "production_integrations": False}


@app.get("/api/overview")
def overview(role=Depends(actor)):
    with db() as conn:
        return {"orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], "programs": conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0], "reviews": conn.execute("SELECT COUNT(*) FROM reviews WHERE status='pending'").fetchone()[0], "ghat_reviews": conn.execute("SELECT COUNT(*) FROM ghat_evidence WHERE review_status='pending_review'").fetchone()[0], "synthetic": True}


@app.get("/api/orders")
def orders(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY created_at DESC")]


@app.get("/api/orders/{order_id}/evidence")
def order_evidence(order_id: str, role=Depends(actor)):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM orders WHERE id=?", (order_id,)).fetchone():
            raise HTTPException(404, "Order not found")
        return [dict(r) for r in conn.execute("SELECT e.*,l.role link_role FROM order_evidence_links l JOIN source_evidence e ON e.id=l.evidence_id WHERE l.order_id=? ORDER BY e.occurred_at", (order_id,))]


@app.post("/api/orders", status_code=201)
def create_order(body: OrderIn, role=Depends(require("operations_officer"))):
    parsed = parse_order(body.raw_text)
    data = body.model_dump()
    data["message_date"] = data["message_date"] or datetime.now(timezone.utc).date().isoformat()
    for field in ("mother_vessel", "lighter_vessel", "master_mobile", "duty_start_date", "shift"):
        data[field] = data[field] or parsed.get(field)
    oid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        prior = conn.execute("SELECT id,status FROM orders WHERE source_evidence_id=?", (body.source_ref,)).fetchone()
        if prior:
            return {"id": prior["id"], "status": prior["status"], "duplicate_source": True}
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.source_ref, "client_order", body.source_ref, body.message_date or now, None, body.raw_text, None, 1))
        conn.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (oid, data["client_id"], data["mother_vessel"], data["lighter_vessel"], data["master_mobile"], data["message_date"], data["duty_start_date"], data["shift"], data["requested_count"], json.dumps({"synthetic": True}), "draft", now, body.source_ref))
        conn.execute("INSERT INTO order_evidence_links VALUES(?,?,?)", (oid, body.source_ref, "client_order"))
        audit(conn, "order", oid, "draft_created", role, {"has_raw_text": bool(body.raw_text)}, body.source_ref)
        missing = [key for key in ("mother_vessel", "lighter_vessel", "master_mobile", "duty_start_date", "shift") if not data.get(key)]
        if missing:
            conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), "incomplete_order", "pending", "Required order details need review: " + ", ".join(missing), body.source_ref, None, "{}", now))
    return {"id": oid, "status": "draft", "review_required": bool(missing), "missing": missing}


@app.post("/api/orders/{order_id}/messages")
def add_order_message(order_id: str, body: OrderIn, role=Depends(require("operations_officer"))):
    parsed = parse_order(body.raw_text)
    now = datetime.now(timezone.utc).isoformat()
    fields = ("mother_vessel", "lighter_vessel", "master_mobile", "duty_start_date", "shift")
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        prior_link = conn.execute("SELECT 1 FROM order_evidence_links WHERE order_id=? AND evidence_id=?", (order_id, body.source_ref)).fetchone()
        if prior_link:
            return {"order_id": order_id, "linked": True, "duplicate_source": True}
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.source_ref, "client_clarification", body.source_ref, body.message_date or now, role, body.raw_text, None, 1))
        conn.execute("INSERT OR IGNORE INTO order_evidence_links VALUES(?,?,?)", (order_id, body.source_ref, "clarification"))
        conflicts, updates = [], {}
        for field in fields:
            incoming = parsed.get(field)
            current = order[field]
            if incoming and current and incoming.casefold() != current.casefold():
                conflicts.append({"field": field, "current": current, "incoming": incoming})
            elif incoming and not current:
                updates[field] = incoming
        if updates:
            conn.execute("UPDATE orders SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?", (*updates.values(), order_id))
        if conflicts:
            rid = str(uuid.uuid4())
            conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (rid, "order_clarification_conflict", "pending", "Conflicting clarification values need an authorized decision.", body.source_ref, None, json.dumps({"order_id": order_id, "conflicts": conflicts}), now))
            audit(conn, "order", order_id, "clarification_conflict_queued", role, {"conflicts": conflicts}, body.source_ref)
        else:
            audit(conn, "order", order_id, "clarification_linked", role, {"fields_filled": list(updates)}, body.source_ref)
    return {"order_id": order_id, "linked": True, "updated_fields": list(updates), "conflicts": conflicts}


@app.get("/api/programs")
def programs(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM programs ORDER BY created_at DESC")]


@app.get("/api/assignments")
def assignments(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT a.*,p.mother_vessel,p.lighter_vessel,p.status program_status,e.name escort_name FROM assignments a JOIN programs p ON p.id=a.program_id JOIN employees e ON e.employee_id=a.employee_id ORDER BY a.rowid DESC")]


@app.get("/api/vessels")
def vessels(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM vessels ORDER BY vessel_type,name")]


@app.get("/api/clients")
def clients(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM clients ORDER BY name")]


@app.post("/api/orders/{order_id}/confirm", status_code=201)
def confirm_order(order_id: str, body: ConfirmIn, role=Depends(require("admin"))):
    mobile = normalize_mobile(body.escort_mobile)
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        data = body.model_dump()
        data["escort_mobile"] = mobile
        for field in ("mother_vessel", "lighter_vessel", "master_mobile", "duty_start_date", "shift"):
            data[field] = data[field] or order[field]
        if not all(data.get(f) for f in ("mother_vessel", "lighter_vessel", "duty_start_date", "shift")):
            raise HTTPException(422, "Mother vessel, lighter vessel, duty start date and shift are required")
        try:
            data["duty_start_date"] = date.fromisoformat(data["duty_start_date"]).isoformat()
        except ValueError:
            raise HTTPException(422, "Duty start date must be ISO YYYY-MM-DD") from None
        data["shift"] = data["shift"].upper()
        if data["shift"] not in ("D", "N"):
            raise HTTPException(422, "Shift must be D or N")
        duplicate_event = conn.execute("SELECT entity_id FROM audit_events WHERE action='confirmed_and_assigned' AND evidence_id=?", (body.source_ref,)).fetchone()
        if duplicate_event:
            return {"status": "confirmed", "program_id": duplicate_event["entity_id"], "duplicate_source": True}
        duplicate_review = conn.execute("SELECT id,kind FROM reviews WHERE evidence_id=? AND kind IN ('exact_duplicate_candidate','duplicate_or_correction_review','cancellation_restart_replacement_review') ORDER BY created_at LIMIT 1", (body.source_ref,)).fetchone()
        if duplicate_review:
            return {"status": "review_required", "classification": duplicate_review["kind"], "review_id": duplicate_review["id"], "duplicate_source": True}
        candidate = {k: data[k] for k in ("mother_vessel", "lighter_vessel", "escort_mobile", "duty_start_date", "shift")}
        existing = conn.execute("SELECT * FROM programs WHERE status!='cancelled'").fetchall()
        matches = [(row, classify_program(candidate, dict(row))) for row in existing]
        matches = [(row, cls) for row, cls in matches if cls]
        if matches:
            cls = matches[0][1]
            review_id = str(uuid.uuid4())
            conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (review_id, cls, "pending", f"Confirmation classified as {cls}; admin review required.", body.source_ref, matches[0][0]["id"], json.dumps({"candidate": candidate, "synthetic": True}), now))
            conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.source_ref, "admin_confirmation", body.source_ref, body.message_date or now, role, json.dumps(data), None, 1))
            audit(conn, "review", review_id, "confirmation_review_created", role, {"classification": cls}, body.source_ref)
            return {"status": "review_required", "classification": cls, "review_id": review_id}
        person = conn.execute("SELECT * FROM employees WHERE employee_id=?", (mobile,)).fetchone()
        if person:
            if person["name"].casefold() != body.escort_name.casefold():
                conn.execute("INSERT OR IGNORE INTO employee_aliases(employee_id,name,evidence_id) VALUES(?,?,?)", (mobile, body.escort_name, body.source_ref))
        else:
            conn.execute("INSERT INTO employees VALUES(?,?,?,1)", (str(uuid.uuid4()), mobile, body.escort_name))
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.source_ref, "admin_confirmation", body.source_ref, body.message_date or now, role, json.dumps(data, ensure_ascii=False), None, 1))
        conn.execute("INSERT OR IGNORE INTO order_evidence_links VALUES(?,?,?)", (order_id, body.source_ref, "admin_confirmation"))
        pid = str(uuid.uuid4())
        conn.execute("INSERT INTO programs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (pid, order_id, data["mother_vessel"], data["lighter_vessel"], mobile, body.escort_name, data["duty_start_date"], data["shift"].upper(), data["master_mobile"], "confirmed", None, None, "not_started", "not_paid", now))
        conn.execute("UPDATE orders SET status='confirmed' WHERE id=?", (order_id,))
        open_prior = conn.execute("SELECT a.id assignment_id,p.id program_id,p.lighter_vessel FROM assignments a JOIN programs p ON p.id=a.program_id WHERE a.employee_id=? AND a.status IN ('assigned','active') AND p.status IN ('confirmed','running')", (mobile,)).fetchall()
        for prior in open_prior:
            closure_id = str(uuid.uuid4())
            conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (closure_id, "assignment_closure", "pending", f"New confirmed assignment may close prior duty on {prior['lighter_vessel']}; date and release still require evidence.", body.source_ref, prior["program_id"], json.dumps({"assignment_id": prior["assignment_id"], "new_program_candidate": True, "new_lighter": data["lighter_vessel"]}), now))
            audit(conn, "review", closure_id, "prior_assignment_closure_candidate", role, {"new_lighter": data["lighter_vessel"]}, body.source_ref)
        aid = str(uuid.uuid4())
        conn.execute("INSERT INTO assignments VALUES(?,?,?,?,?,?,?,?)", (aid, pid, mobile, data["duty_start_date"], data["shift"].upper(), None, "assigned", None))
        audit(conn, "program", pid, "confirmed_and_assigned", role, {"escort_mobile": mobile}, body.source_ref)
        return {"status": "confirmed", "program_id": pid, "assignment_id": aid}


@app.post("/api/programs/{program_id}/duty-start")
def duty_start(program_id: str, body: DutyEvidenceIn, role=Depends(require("operations_officer"))):
    now = datetime.now(timezone.utc).isoformat()
    review_id = str(uuid.uuid4())
    with db() as conn:
        prior = conn.execute("SELECT r.id FROM reviews r WHERE r.kind='duty_start_verification' AND r.evidence_id=?", (body.evidence_ref,)).fetchone()
        if prior:
            return {"program_id": program_id, "status": "confirmed", "review_id": prior["id"], "duplicate_source": True}
        row = conn.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Program not found")
        if row["status"] != "confirmed":
            raise HTTPException(409, "Only confirmed programs can start duty")
        try:
            date.fromisoformat(body.occurred_at[:10])
        except ValueError:
            raise HTTPException(422, "Observed duty date must use ISO YYYY-MM-DD") from None
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.evidence_ref, "duty_start_evidence", body.evidence_ref, body.occurred_at, role, None, None, 1))
        evidence_id = str(uuid.uuid4())
        conn.execute("INSERT INTO duty_evidence VALUES(?,?,?,?,?,'pending_review')", (evidence_id, program_id, body.evidence_ref, body.evidence_type, body.occurred_at))
        conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (review_id, "duty_start_verification", "pending", "Duty start evidence requires authorized verification.", body.evidence_ref, program_id, json.dumps({"duty_evidence_id": evidence_id}), now))
        audit(conn, "duty_evidence", evidence_id, "attendance_evidence_received_pending_review", role, {"observed_at": body.occurred_at}, body.evidence_ref)
    return {"program_id": program_id, "status": "confirmed", "review_id": review_id, "duty_start": "pending_verification"}


@app.get("/api/duty-evidence")
def duty_evidence(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT d.*,p.mother_vessel,p.lighter_vessel,p.escort_mobile FROM duty_evidence d JOIN programs p ON p.id=d.program_id ORDER BY d.occurred_at DESC")]


@app.post("/api/programs/{program_id}/correction-review")
def correction_review(program_id: str, payload: dict, role=Depends(require("admin"))):
    return create_review("program_correction", program_id, payload, role)


@app.post("/api/programs/{program_id}/cancel-review")
def cancel_review(program_id: str, payload: dict, role=Depends(require("admin"))):
    return create_review("program_cancellation", program_id, payload, role)


@app.post("/api/programs/{program_id}/replacement-review")
def replacement_review(program_id: str, payload: dict, role=Depends(require("admin"))):
    return create_review("assignment_replacement", program_id, payload, role)


def create_review(kind, program_id, payload, role):
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM programs WHERE id=?", (program_id,)).fetchone():
            raise HTTPException(404, "Program not found")
        evidence_id = payload.get("evidence_id")
        if evidence_id:
            conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (evidence_id, "manual_review_reference", evidence_id, now, role, json.dumps({"synthetic": True}), None, 1))
        details = dict(payload)
        if kind == "assignment_replacement":
            previous = conn.execute("SELECT id FROM assignments WHERE program_id=? AND status IN ('assigned','active') ORDER BY rowid DESC LIMIT 1", (program_id,)).fetchone()
            if not previous:
                raise HTTPException(409, "No open assignment to replace")
            details["previous_assignment"] = previous["id"]
        conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (rid, kind, "pending", "Human decision required; no program state changed.", evidence_id, program_id, json.dumps(details), now))
        audit(conn, "review", rid, "review_created", role, {"kind": kind}, evidence_id)
    return {"review_id": rid, "status": "pending", "program_changed": False}


@app.get("/api/reviews")
def reviews(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM reviews ORDER BY created_at DESC")]


@app.post("/api/reviews/{review_id}/resolve")
def resolve_review(review_id: str, payload: dict, role=Depends(require("admin"))):
    decision = payload.get("decision")
    if decision not in ("approve", "reject", "defer"):
        raise HTTPException(422, "decision must be approve, reject or defer")
    status = {"approve": "approved", "reject": "rejected", "defer": "deferred"}[decision]
    with db() as conn:
        review = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not review:
            raise HTTPException(404, "Review not found")
        conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, review_id))
        audit(conn, "review", review_id, "review_resolved", role, {"decision": decision, "reason": payload.get("reason")}, review["evidence_id"])
        # Approval of a release review is the only operation that changes program release state.
        if status == "approved" and review["program_id"] and review["kind"] == "release_verification":
            if not payload.get("release_date"):
                raise HTTPException(422, "Verified release date is required; do not infer it")
            try:
                date.fromisoformat(payload["release_date"])
            except ValueError:
                raise HTTPException(422, "Release date must be ISO YYYY-MM-DD") from None
            prog = conn.execute("SELECT status FROM programs WHERE id=?", (review["program_id"],)).fetchone()
            if not prog or prog["status"] not in ("confirmed", "running", "closure_review"):
                raise HTTPException(409, "Program state is not eligible for release verification")
            conn.execute("UPDATE programs SET status='released', release_date=? WHERE id=?", (payload["release_date"], review["program_id"]))
            conn.execute("UPDATE release_slips SET verification_status='verified' WHERE evidence_id=?", (review["evidence_id"],))
            conn.execute("UPDATE assignments SET end_date=?,status='released' WHERE program_id=? AND status IN ('assigned','active')", (payload["release_date"], review["program_id"]))
            audit(conn, "program", review["program_id"], "release_verified", role, {"release_date": payload["release_date"]}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "duty_start_verification":
            prog = conn.execute("SELECT status FROM programs WHERE id=?", (review["program_id"],)).fetchone()
            if not prog or prog["status"] != "confirmed":
                raise HTTPException(409, "Duty start is no longer eligible")
            detail = json.loads(review["details"])
            observed = conn.execute("SELECT occurred_at FROM duty_evidence WHERE id=?", (detail["duty_evidence_id"],)).fetchone()
            conn.execute("UPDATE programs SET status='running' WHERE id=?", (review["program_id"],))
            conn.execute("UPDATE duty_evidence SET verification_status='verified' WHERE id=?", (detail["duty_evidence_id"],))
            conn.execute("UPDATE assignments SET status='active' WHERE program_id=? AND status='assigned'", (review["program_id"],))
            audit(conn, "program", review["program_id"], "duty_started_from_verified_evidence", role, {"observed_at": observed["occurred_at"] if observed else None}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "program_completion":
            if not payload.get("completion_date"):
                raise HTTPException(422, "Verified completion date is required; do not infer it")
            try:
                date.fromisoformat(payload["completion_date"])
            except ValueError:
                raise HTTPException(422, "Completion date must be ISO YYYY-MM-DD") from None
            prog = conn.execute("SELECT status FROM programs WHERE id=?", (review["program_id"],)).fetchone()
            if not prog or not can_complete(prog["status"]):
                raise HTTPException(409, "Program must have verified Released status before completion")
            conn.execute("UPDATE programs SET status='completed',completion_date=? WHERE id=?", (payload["completion_date"], review["program_id"]))
            audit(conn, "program", review["program_id"], "program_completed", role, {"completion_date": payload["completion_date"]}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "assignment_closure":
            if not review["evidence_id"] or not payload.get("previous_end_date"):
                raise HTTPException(422, "Evidence-supported prior assignment end date is required")
            try:
                date.fromisoformat(payload["previous_end_date"])
            except ValueError:
                raise HTTPException(422, "Prior end date must be ISO YYYY-MM-DD") from None
            assignment_id = json.loads(review["details"]).get("assignment_id")
            cur = conn.execute("UPDATE assignments SET end_date=?,status='ended_pending_release' WHERE id=? AND status IN ('assigned','active')", (payload["previous_end_date"], assignment_id))
            if cur.rowcount != 1:
                raise HTTPException(409, "Prior assignment is no longer open")
            conn.execute("UPDATE programs SET status='closure_review' WHERE id=? AND status IN ('confirmed','running')", (review["program_id"],))
            audit(conn, "assignment", assignment_id, "closure_confirmed_release_still_pending", role, {"end_date": payload["previous_end_date"]}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "program_cancellation":
            if not review["evidence_id"]:
                raise HTTPException(422, "Authoritative cancellation evidence is required")
            conn.execute("UPDATE programs SET status='cancelled' WHERE id=?", (review["program_id"],))
            conn.execute("UPDATE assignments SET status='cancelled' WHERE program_id=? AND status IN ('assigned','active')", (review["program_id"],))
            conn.execute("UPDATE orders SET status='cancelled' WHERE id=(SELECT order_id FROM programs WHERE id=?) AND NOT EXISTS (SELECT 1 FROM programs WHERE order_id=orders.id AND status!='cancelled')", (review["program_id"],))
            audit(conn, "program", review["program_id"], "cancelled_with_authoritative_evidence", role, {"reason": payload.get("reason")}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "program_correction":
            if not review["evidence_id"]:
                raise HTTPException(422, "Correction evidence is required")
            allowed = {k: payload[k] for k in ("mother_vessel", "lighter_vessel", "escort_name", "duty_start_date", "shift", "master_mobile") if payload.get(k)}
            if not allowed:
                raise HTTPException(422, "Provide at least one corrected field")
            columns = ",".join(f"{key}=?" for key in allowed)
            conn.execute(f"UPDATE programs SET {columns} WHERE id=?", (*allowed.values(), review["program_id"]))
            audit(conn, "program", review["program_id"], "corrected_with_evidence", role, allowed, review["evidence_id"])
        if status == "approved" and review["kind"] == "order_clarification_conflict":
            resolutions = payload.get("resolutions") or {}
            review_details = json.loads(review["details"])
            conflicts = review_details["conflicts"]
            accepted = {}
            for item in conflicts:
                choice = resolutions.get(item["field"])
                if choice == "incoming":
                    accepted[item["field"]] = item["incoming"]
                elif choice == "existing":
                    accepted[item["field"]] = item["current"]
            if len(accepted) != len(conflicts):
                raise HTTPException(422, "Choose existing or incoming for every conflicting field")
            conn.execute("UPDATE orders SET " + ",".join(f"{key}=?" for key in accepted) + " WHERE id=?", (*accepted.values(), review_details["order_id"]))
            audit(conn, "order", review_details["order_id"], "clarification_conflict_resolved", role, accepted, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] in ("exact_duplicate_candidate", "duplicate_or_correction_review"):
            audit(conn, "program", review["program_id"], "confirmation_linked_after_review", role, {"review_id": review_id, "no_duplicate_created": True}, review["evidence_id"])
        if status == "approved" and review["program_id"] and review["kind"] == "assignment_replacement":
            required = ("previous_end_date", "new_escort_mobile", "new_escort_name", "new_start_date", "new_shift")
            if not review["evidence_id"] or any(not payload.get(k) for k in required):
                raise HTTPException(422, "Replacement needs source evidence, verified prior end date, new Escort identity, start date and shift")
            new_mobile = normalize_mobile(payload["new_escort_mobile"])
            old = conn.execute("SELECT * FROM assignments WHERE id=?", (json.loads(review["details"])["previous_assignment"],)).fetchone()
            if not old or old["status"] not in ("assigned", "active"):
                raise HTTPException(409, "Prior assignment is no longer open")
            person = conn.execute("SELECT * FROM employees WHERE employee_id=?", (new_mobile,)).fetchone()
            if person:
                if person["name"].casefold() != payload["new_escort_name"].casefold():
                    conn.execute("INSERT OR IGNORE INTO employee_aliases(employee_id,name,evidence_id) VALUES(?,?,?)", (new_mobile, payload["new_escort_name"], review["evidence_id"]))
            else:
                conn.execute("INSERT INTO employees VALUES(?,?,?,1)", (str(uuid.uuid4()), new_mobile, payload["new_escort_name"]))
            conn.execute("UPDATE assignments SET end_date=?,status='replaced' WHERE id=?", (payload["previous_end_date"], old["id"]))
            conn.execute("UPDATE programs SET status='closure_review' WHERE id=?", (review["program_id"],))
            new_pid, new_aid = str(uuid.uuid4()), str(uuid.uuid4())
            prog = conn.execute("SELECT * FROM programs WHERE id=?", (review["program_id"],)).fetchone()
            conn.execute("INSERT INTO programs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (new_pid, prog["order_id"], prog["mother_vessel"], prog["lighter_vessel"], new_mobile, payload["new_escort_name"], payload["new_start_date"], payload["new_shift"].upper(), prog["master_mobile"], "confirmed", None, None, "not_started", "not_paid", datetime.now(timezone.utc).isoformat()))
            conn.execute("INSERT INTO assignments VALUES(?,?,?,?,?,?,?,?)", (new_aid, new_pid, new_mobile, payload["new_start_date"], payload["new_shift"].upper(), None, "assigned", old["id"]))
            audit(conn, "program", new_pid, "replacement_segment_created", role, {"predecessor_program": review["program_id"], "predecessor_assignment": old["id"]}, review["evidence_id"])
        if status == "approved" and review["kind"] in ("ghat_duty_payment", "ghat_duty_pattern") and review["evidence_id"]:
            conn.execute("UPDATE ghat_evidence SET review_status='reviewed' WHERE evidence_id=?", (review["evidence_id"],))
    return {"review_id": review_id, "status": status, "program_status_changed": bool(status == "approved" and review["kind"] in ("release_verification", "program_completion", "program_cancellation"))}


@app.post("/api/programs/{program_id}/release-slips", status_code=201)
def release_slip(program_id: str, body: ReleaseIn, role=Depends(require("operations_officer"))):
    now = datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())
    with db() as conn:
        prior = conn.execute("SELECT id FROM release_slips WHERE evidence_id=?", (body.source_ref,)).fetchone()
        if prior:
            review = conn.execute("SELECT id FROM reviews WHERE kind='release_verification' AND details LIKE ? ORDER BY created_at LIMIT 1", (f'%"slip_id": "{prior["id"]}"%',)).fetchone()
            return {"slip_id": prior["id"], "review_id": review["id"] if review else None, "verification_status": "pending_review", "duplicate_source": True}
        if not conn.execute("SELECT 1 FROM programs WHERE id=?", (program_id,)).fetchone():
            raise HTTPException(404, "Program not found")
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.source_ref, "release_media", body.source_ref, now, role, body.ocr_text, body.media_name, 1))
        conn.execute("INSERT INTO release_slips VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (sid, program_id, None, body.release_date, body.shift, body.total_duty, body.salary, body.conveyance, body.location, body.ocr_text, body.confidence, "pending_review", body.source_ref, now))
        rid = str(uuid.uuid4())
        conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (rid, "release_verification", "pending", "Uploaded slip requires field and program verification.", body.source_ref, program_id, json.dumps({"slip_id": sid, "synthetic": True}), now))
        audit(conn, "release_slip", sid, "uploaded_pending_verification", role, {"confidence": body.confidence, "program_status_unchanged": True}, body.source_ref)
    return {"slip_id": sid, "review_id": rid, "verification_status": "pending_review"}


@app.post("/api/programs/{program_id}/release-upload", status_code=201)
async def release_upload(program_id: str, file: UploadFile = File(...), role=Depends(require("operations_officer"))):
    signatures = {
        "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
        "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP",
        "application/pdf": lambda b: b.startswith(b"%PDF-"),
    }
    if file.content_type not in signatures:
        raise HTTPException(415, "Upload must be a PDF, JPEG, PNG or WEBP")
    payload = await file.read(10 * 1024 * 1024 + 1)
    if not payload or len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "File must be between 1 byte and 10 MiB")
    if not signatures[file.content_type](payload):
        raise HTTPException(415, "File bytes do not match the declared image/PDF type")
    now = datetime.now(timezone.utc).isoformat()
    evidence_id = f"synthetic-upload-{uuid.uuid4()}"
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}[file.content_type]
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    upload_dir = ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / stored_name).write_bytes(payload)
    slip_id, review_id = str(uuid.uuid4()), str(uuid.uuid4())
    with db() as conn:
        if not conn.execute("SELECT 1 FROM programs WHERE id=?", (program_id,)).fetchone():
            (upload_dir / stored_name).unlink(missing_ok=True)
            raise HTTPException(404, "Program not found")
        conn.execute("INSERT INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (evidence_id, "release_media", evidence_id, now, role, None, stored_name, 1))
        conn.execute("INSERT INTO release_slips VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (slip_id, program_id, None, None, None, None, None, None, None, None, None, "pending_review", evidence_id, now))
        conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (review_id, "release_verification", "pending", "Uploaded original retained; OCR and field verification required.", evidence_id, program_id, json.dumps({"slip_id": slip_id, "mime_type": file.content_type, "synthetic": True}), now))
        audit(conn, "release_slip", slip_id, "original_media_uploaded_pending_review", role, {"stored_name": stored_name, "mime_type": file.content_type}, evidence_id)
    return {"slip_id": slip_id, "review_id": review_id, "verification_status": "pending_review", "media_name": stored_name}


@app.get("/api/release-slips")
def release_slips(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT s.*,e.media_name FROM release_slips s LEFT JOIN source_evidence e ON e.id=s.evidence_id ORDER BY s.created_at DESC")]


@app.post("/api/ghat-duty")
def add_ghat(body: GhatIn, role=Depends(require("operations_officer"))):
    if body.evidence_kind == "verified_transfer" and ROLES[role] < ROLES["accountant"]:
        raise HTTPException(403, "Accountant or higher must record a transfer as verified")
    try:
        date.fromisoformat(body.day)
    except ValueError:
        raise HTTPException(422, "Ghat evidence date must be ISO YYYY-MM-DD") from None
    mobile = normalize_mobile(body.employee_mobile)
    now = datetime.now(timezone.utc).isoformat()
    eid = str(uuid.uuid4())
    with db() as conn:
        prior = conn.execute("SELECT id FROM ghat_evidence WHERE evidence_id=?", (body.evidence_ref,)).fetchone()
        if prior:
            return {"evidence_id": prior["id"], "duplicate_source": True, "posting": "not_performed"}
        conn.execute("INSERT OR IGNORE INTO source_evidence VALUES(?,?,?,?,?,?,?,?)", (body.evidence_ref, "ghat_payment_evidence", body.evidence_ref, body.day, role, json.dumps(body.model_dump()), None, 1))
        conn.execute("INSERT INTO ghat_evidence VALUES(?,?,?,?,?,?,?)", (eid, mobile, body.day, body.amount, body.evidence_ref, body.evidence_kind, "pending_review"))
        rows = conn.execute("SELECT day,amount,evidence_kind='verified_transfer' FROM ghat_evidence WHERE employee_id=? ORDER BY day", (mobile,)).fetchall()
        max_days = consecutive_200_days([(r["day"], r["amount"], bool(r[2])) for r in rows])
        high = max_days >= 3
        rid = str(uuid.uuid4())
        conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (rid, "ghat_duty_pattern" if high else "ghat_duty_payment", "pending", "Three consecutive BDT 200 evidence days; priority review." if high else ghat_candidate(body.amount, body.evidence_kind == "verified_transfer"), body.evidence_ref, None, json.dumps({"consecutive_days": max_days}), now))
        audit(conn, "ghat_evidence", eid, "candidate_created", role, {"amount": body.amount, "consecutive_days": max_days}, body.evidence_ref)
    return {"evidence_id": eid, "review_id": rid, "consecutive_days": max_days, "priority": "high" if high else "normal", "posting": "not_performed"}


@app.get("/api/ghat-duty")
def ghat_list(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ghat_evidence ORDER BY day DESC")]


@app.post("/api/programs/{program_id}/completion-review")
def completion_review(program_id: str, payload: dict, role=Depends(require("admin"))):
    return create_review("program_completion", program_id, payload, role)


@app.post("/api/programs/{program_id}/settlement")
def settlement(program_id: str, body: SettlementIn, role=Depends(require("accountant"))):
    sid = str(uuid.uuid4())
    preview = settlement_preview(body.duty_days, body.daily_rate, body.deductions or 0)
    with db() as conn:
        if not conn.execute("SELECT 1 FROM programs WHERE id=?", (program_id,)).fetchone():
            raise HTTPException(404, "Program not found")
        conn.execute("INSERT INTO settlements VALUES(?,?,?,?,?,?,?,1)", (sid, program_id, body.duty_days, body.daily_rate, body.deductions, json.dumps(preview), preview["status"]))
        conn.execute("UPDATE programs SET settlement_status=? WHERE id=?", (preview["status"], program_id))
        audit(conn, "settlement", sid, "synthetic_settlement_review_created", role, preview)
    return {"settlement_id": sid, **preview, "production_posting": False}


@app.get("/api/settlements")
def settlements(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM settlements ORDER BY rowid DESC")]


@app.post("/api/settlements/{settlement_id}/approve")
def approve_settlement(settlement_id: str, payload: dict, role=Depends(require("accountant"))):
    with db() as conn:
        row = conn.execute("SELECT * FROM settlements WHERE id=?", (settlement_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Settlement not found")
        preview = json.loads(row["preview_json"])
        prog = conn.execute("SELECT status FROM programs WHERE id=?", (row["program_id"],)).fetchone()
        if preview["status"] != "synthetic_preview" or prog["status"] != "completed":
            raise HTTPException(409, "Verified calculation and completed program are required")
        conn.execute("UPDATE settlements SET status='approved' WHERE id=?", (settlement_id,))
        conn.execute("UPDATE programs SET settlement_status='approved' WHERE id=?", (row["program_id"],))
        audit(conn, "settlement", settlement_id, "settlement_approved", role, {"reason": payload.get("reason"), "synthetic": True})
    return {"settlement_id": settlement_id, "status": "approved", "production_posting": False}


@app.post("/api/settlements/{settlement_id}/mark-paid")
def mark_paid(settlement_id: str, payload: dict, role=Depends(require("accountant"))):
    if not payload.get("synthetic_payment_reference"):
        raise HTTPException(422, "Synthetic payment reference is required")
    with db() as conn:
        row = conn.execute("SELECT * FROM settlements WHERE id=?", (settlement_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Settlement not found")
        if row["status"] != "approved":
            raise HTTPException(409, "Settlement approval is required before recording synthetic payment")
        conn.execute("UPDATE settlements SET status='payment_completed' WHERE id=?", (settlement_id,))
        conn.execute("UPDATE programs SET payment_status='completed' WHERE id=?", (row["program_id"],))
        audit(conn, "settlement", settlement_id, "synthetic_payment_completed", role, {"reference": payload["synthetic_payment_reference"], "production_posting": False})
    return {"settlement_id": settlement_id, "status": "payment_completed", "production_posting": False}


@app.post("/api/programs/{program_id}/assignments")
def replace_assignment(program_id: str, payload: dict, role=Depends(require("admin"))):
    mobile = normalize_mobile(payload.get("escort_mobile", ""))
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        program = conn.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
        if not program:
            raise HTTPException(404, "Program not found")
        previous = conn.execute("SELECT * FROM assignments WHERE program_id=? AND status IN ('assigned','active') ORDER BY rowid DESC LIMIT 1", (program_id,)).fetchone()
        if previous:
            conn.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (rid, "assignment_replacement", "pending", "Replacement proposed; prior assignment end date and program state remain unchanged until review.", payload.get("evidence_id"), program_id, json.dumps({"previous_assignment": previous["id"], "new_mobile": mobile}), now))
            return {"status": "review_required", "review_id": rid, "prior_assignment_unchanged": True}
        raise HTTPException(409, "No open assignment; use authorized program confirmation flow")


@app.get("/api/identity")
def identities(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT e.employee_id,e.person_uid,e.name,group_concat(a.name,' | ') aliases FROM employees e LEFT JOIN employee_aliases a USING(employee_id) GROUP BY e.employee_id")]


@app.get("/api/audit")
def audit_history(role=Depends(actor)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_events ORDER BY occurred_at DESC")]


@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id: str, role=Depends(actor)):
    with db() as conn:
        row = conn.execute("SELECT * FROM source_evidence WHERE id=? OR source_ref=?", (evidence_id, evidence_id)).fetchone()
        if not row:
            raise HTTPException(404, "Evidence not found")
        return dict(row)


@app.get("/api/evidence/{evidence_id}/media")
def evidence_media(evidence_id: str, role=Depends(actor)):
    with db() as conn:
        row = conn.execute("SELECT media_name FROM source_evidence WHERE id=? OR source_ref=?", (evidence_id, evidence_id)).fetchone()
        if not row or not row["media_name"]:
            raise HTTPException(404, "Evidence media not found")
        safe_name = Path(row["media_name"]).name
        path = ROOT / "data" / "uploads" / safe_name
        if not path.is_file():
            raise HTTPException(404, "Evidence media file is unavailable")
        return FileResponse(path)


@app.get("/api/reports")
def reports(role=Depends(actor)):
    with db() as conn:
        return {"program_status": [dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM programs GROUP BY status")], "review_status": [dict(r) for r in conn.execute("SELECT kind,status,COUNT(*) count FROM reviews GROUP BY kind,status")], "synthetic_only": True}


@app.get("/api/settings")
def settings(role=Depends(actor)):
    return {"mode": "standalone_synthetic", "daily_rate": None, "salary_policy": "unconfigured; settlement requires explicit rate", "production_integrations": False, "roles": list(ROLES)}


app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
