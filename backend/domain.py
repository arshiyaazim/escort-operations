"""Pure domain rules for the standalone synthetic Escort Operations app."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime


def normalize_mobile(value: str) -> str:
    digits = "".join(str(unicodedata.digit(c)) if c.isdigit() else "" for c in (value or ""))
    if digits.startswith("00880"):
        digits = digits[2:]
    if digits.startswith("880"):
        digits = "0" + digits[3:]
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    if not re.fullmatch(r"01[3-9]\d{8}", digits):
        raise ValueError("Expected a valid Bangladesh mobile number")
    return digits


def classify_program(candidate: dict, existing: dict) -> str | None:
    """Return a review classification; never perform a status transition."""
    same_mv = (candidate.get("mother_vessel") or "").strip().casefold() == (existing.get("mother_vessel") or "").strip().casefold()
    same_lv = (candidate.get("lighter_vessel") or "").strip().casefold() == (existing.get("lighter_vessel") or "").strip().casefold()
    if not same_mv or not same_lv:
        return None
    same_escort = bool(candidate.get("escort_mobile") and candidate.get("escort_mobile") == existing.get("escort_mobile"))
    same_shift = bool(candidate.get("shift") and candidate.get("shift") == existing.get("shift"))
    try:
        days = abs((date.fromisoformat(candidate["duty_start_date"]) - date.fromisoformat(existing["duty_start_date"])).days)
    except (ValueError, KeyError, TypeError):
        return "program_identity_review"
    if days == 0 and same_escort and same_shift:
        return "exact_duplicate_candidate"
    if days <= 3:
        return "duplicate_or_correction_review"
    if days < 5:
        return "cancellation_restart_replacement_review"
    return None


def ghat_candidate(amount: int, transfer_verified: bool) -> str:
    if amount == 200:
        return "verified_transfer_review" if transfer_verified else "payment_instruction_review"
    return "not_ghat_indicator"


def consecutive_200_days(events: list[tuple[str, int, bool]]) -> int:
    """Count consecutive calendar days with BDT 200 evidence, regardless of verification."""
    daily = {day: amount for day, amount, _verified in events if amount == 200}
    dates = sorted(date.fromisoformat(day) for day in daily)
    best = run = 0
    previous = None
    for current in dates:
        run = run + 1 if previous and (current - previous).days == 1 else 1
        best = max(best, run)
        previous = current
    return best


def settlement_preview(duty_days: float | None, daily_rate: float | None, deductions: float = 0) -> dict:
    if duty_days is None or daily_rate is None:
        return {"status": "review_required", "gross": None, "net": None}
    gross = round(duty_days * daily_rate, 2)
    return {"status": "synthetic_preview", "gross": gross, "net": max(round(gross - deductions, 2), 0)}


ROLE_LEVELS = {"viewer": 0, "operations_officer": 1, "accountant": 2, "admin": 3, "superadmin": 4}


def role_allows(role: str, minimum: str) -> bool:
    return ROLE_LEVELS.get(role, -1) >= ROLE_LEVELS[minimum]


def can_release(status: str) -> bool:
    return status in ("confirmed", "running")


def can_complete(status: str) -> bool:
    return status == "released"


def parse_order(text: str) -> dict:
    """Conservative labeled-field extraction; never treats a sender as Escort Mobile."""
    def field(label: str) -> str | None:
        match = re.search(rf"(?im)^\s*{label}\s*:\s*(.*?)\s*$", text or "")
        return match.group(1).strip() if match and match.group(1).strip() else None
    return {
        "mother_vessel": field("Mother Vessel"),
        "lighter_vessel": field("Lighter Vessel"),
        "master_mobile": field("Master Mobile"),
        "escort_name": field("Escort Name"),
        "escort_mobile": field("Escort Mobile"),
        "duty_start_date": field("Duty Start Date"),
        "shift": field("Shift"),
    }
