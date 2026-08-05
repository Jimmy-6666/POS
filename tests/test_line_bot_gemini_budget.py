import tempfile
import unittest
from pathlib import Path

from line_bot.storage import BotStore


class GeminiBudgetStoreTests(unittest.TestCase):
    def test_reservations_are_atomic_idempotent_and_reset_by_calendar_month(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = BotStore(Path(temporary))
            first = store.reserve_gemini_request(
                job_id="job-a", attempt=1, budget_microusd=20, reserved_cost_microusd=10, month="2026-08",
            )
            self.assertTrue(first["allowed"])
            self.assertTrue(store.start_gemini_request(first["request_key"]))
            self.assertFalse(store.start_gemini_request(first["request_key"]))
            duplicate = store.reserve_gemini_request(
                job_id="job-a", attempt=1, budget_microusd=20, reserved_cost_microusd=10, month="2026-08",
            )
            self.assertEqual((duplicate["allowed"], duplicate["reason"]), (False, "duplicate"))
            store.settle_gemini_request(
                first["request_key"], actual_cost_microusd=3, input_tokens=8, output_tokens=1, thought_tokens=0,
            )
            second = store.reserve_gemini_request(
                job_id="job-b", attempt=1, budget_microusd=20, reserved_cost_microusd=17, month="2026-08",
            )
            self.assertTrue(second["allowed"])
            exhausted = store.reserve_gemini_request(
                job_id="job-c", attempt=1, budget_microusd=20, reserved_cost_microusd=1, month="2026-08",
            )
            self.assertEqual((exhausted["allowed"], exhausted["reason"]), (False, "budget_exhausted"))
            self.assertEqual(store.gemini_budget_diagnostics(20, month="2026-08"), {
                "month": "2026-08",
                "request_count": 2,
                "estimated_cost_usd": "0.000020",
                "actual_cost_usd": "0.000003",
                "remaining_budget_usd": "0.000000",
            })
            self.assertEqual(store.gemini_budget_diagnostics(20, month="2026-09")["request_count"], 0)


if __name__ == "__main__":
    unittest.main()
