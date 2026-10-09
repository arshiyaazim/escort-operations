import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.domain import can_complete, can_release, classify_program, consecutive_200_days, ghat_candidate, normalize_mobile, parse_order, role_allows, settlement_preview


class IdentityRules(unittest.TestCase):
    def test_normalizes_bd_mobile(self):
        self.assertEqual(normalize_mobile("+880 1800-000000"), "01800000000")

    def test_rejects_invalid_phone(self):
        with self.assertRaises(ValueError):
            normalize_mobile("0191234")

    def test_sender_mobile_is_not_inferred_as_escort_mobile(self):
        fields = parse_order("Sender Mobile: 01800000000\nMother Vessel: MV DEMO\nLighter Vessel: LIGHTER")
        self.assertIsNone(fields["escort_mobile"])

    def test_same_name_different_mobile_is_not_same_identity(self):
        self.assertNotEqual(normalize_mobile("01800000000"), normalize_mobile("01700000000"))

    def test_backend_role_thresholds(self):
        self.assertFalse(role_allows("operations_officer", "admin"))
        self.assertTrue(role_allows("superadmin", "admin"))
        self.assertFalse(role_allows("untrusted", "viewer"))

    def test_release_and_completion_are_separate_transitions(self):
        self.assertTrue(can_release("running"))
        self.assertFalse(can_complete("running"))
        self.assertTrue(can_complete("released"))


class ProgramClassification(unittest.TestCase):
    def setUp(self):
        self.existing = {"mother_vessel": "MV DEMO", "lighter_vessel": "LIGHTER A", "escort_mobile": "01800000000", "duty_start_date": "2026-10-01", "shift": "D"}

    def candidate(self, **updates):
        return {**self.existing, **updates}

    def test_same_mother_different_lighter_is_distinct(self):
        self.assertIsNone(classify_program(self.candidate(lighter_vessel="LIGHTER B"), self.existing))

    def test_exact_repeat_is_candidate_not_transition(self):
        self.assertEqual(classify_program(self.candidate(), self.existing), "exact_duplicate_candidate")

    def test_three_day_window_requires_correction_review(self):
        self.assertEqual(classify_program(self.candidate(duty_start_date="2026-10-04"), self.existing), "duplicate_or_correction_review")

    def test_four_day_lighter_repeat_requires_restart_review(self):
        self.assertEqual(classify_program(self.candidate(duty_start_date="2026-10-05"), self.existing), "cancellation_restart_replacement_review")

    def test_five_day_repeat_may_be_new(self):
        self.assertIsNone(classify_program(self.candidate(duty_start_date="2026-10-06"), self.existing))


class GhatAndSettlement(unittest.TestCase):
    def test_payment_instruction_is_review_only(self):
        self.assertEqual(ghat_candidate(200, False), "payment_instruction_review")

    def test_three_consecutive_days_detected(self):
        events = [(f"2026-10-0{i}", 200, False) for i in (1, 2, 3)]
        self.assertEqual(consecutive_200_days(events), 3)

    def test_gap_breaks_consecutive_pattern(self):
        events = [("2026-10-01", 200, True), ("2026-10-03", 200, True)]
        self.assertEqual(consecutive_200_days(events), 1)

    def test_missing_rate_never_invents_salary(self):
        self.assertEqual(settlement_preview(4, None), {"status": "review_required", "gross": None, "net": None})


if __name__ == "__main__":
    unittest.main()
