import json
import sys
import tempfile
import unittest
from pathlib import Path

from workflow import allocation_cycle


class AllocationCycleTests(unittest.TestCase):
    def test_dry_run_cycle_writes_only_own_result_snapshot(self):
        result = allocation_cycle.run_allocation_cycle(write_snapshot=True)
        result_path = Path(result["result_snapshot_path"]).resolve()
        expected_path = allocation_cycle.RESULT_SNAPSHOT_PATH.resolve()

        self.assertEqual(result_path, expected_path)
        self.assertTrue(expected_path.exists())
        payload = json.loads(expected_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_DECISION")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["health_evaluated"])
        self.assertTrue(payload["recommendation"]["recommendation_only"])
        self.assertFalse(payload["recommendation"]["downstream_export_enabled"])

    def test_cycle_integration_keeps_allocation_fixed_and_adds_recommendation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_snapshot = root / "stock.json"
            options_snapshot = root / "options.json"
            stock_snapshot.write_text(
                json.dumps(
                    {
                        "status": "done",
                        "report_only": True,
                        "live_trading_active": True,
                        "armed_state": {
                            "allow_live_trades": True,
                            "require_double_arm": True,
                            "live_arm_present": True,
                            "recent_live_execution": None,
                            "live_trading_active": True,
                            "source": "derived_reporting_only",
                        },
                        "completed_at": "2026-06-06T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            options_snapshot.write_text(
                json.dumps(
                    {
                        "status": "manual_review",
                        "dry_run": True,
                        "live_trading_active": False,
                        "completed_at": "2026-06-06T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False,
                snapshot_paths={
                    "NovaBotV2": stock_snapshot,
                    "NovaBotV2Options": options_snapshot,
                },
            )

        decision = result["decision"]
        allocations = {
            target["bot_name"]: target["target_percentage"]
            for target in decision["plan"]["targets"]
        }
        self.assertEqual(allocations["NovaBotV2"], 90.0)
        self.assertEqual(allocations["NovaBotV2Options"], 10.0)
        self.assertEqual(sum(allocations.values()), 100.0)
        self.assertTrue(result["health_evaluated"])
        self.assertIn("NovaBotV2", decision["bot_health"])
        self.assertIn("NovaBotV2Options", decision["bot_health"])
        self.assertTrue(decision["bot_health"]["NovaBotV2"]["live_trading_active"])
        self.assertFalse(decision["bot_health"]["NovaBotV2Options"]["live_trading_active"])
        recommendation = decision["recommendation"]
        self.assertEqual(recommendation["current_allocation"]["NovaBotV2"], 90)
        self.assertEqual(recommendation["current_allocation"]["NovaBotV2Options"], 10)
        self.assertEqual(sum(recommendation["recommended_allocation"].values()), 100)
        self.assertTrue(recommendation["recommendation_only"])

    def test_write_result_refuses_outside_project(self):
        decision = allocation_cycle.build_dry_run_decision()
        outside_path = Path(tempfile.gettempdir()) / "allocation_outside.json"
        with self.assertRaises(ValueError):
            allocation_cycle.write_result_snapshot(decision, outside_path)

    def test_no_broker_order_trading_modules_are_imported(self):
        allocation_cycle.run_allocation_cycle(write_snapshot=False)
        forbidden_fragments = ("broker", "order", "trading")
        imported = [
            name
            for name in sys.modules
            if any(fragment in name.lower() for fragment in forbidden_fragments)
        ]
        imported = [
            name
            for name in imported
            if not name.startswith("unittest")
            and not name.startswith("test")
            and "allocation" not in name.lower()
        ]
        self.assertEqual(imported, [])


if __name__ == "__main__":
    unittest.main()
