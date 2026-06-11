import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from config.allocation_config import FUTURE_SNAPSHOT_PATHS
from core.health_evaluator import evaluate_snapshot_health
from core.snapshot_reader import read_bot_snapshot


class SnapshotReaderAndHealthTests(unittest.TestCase):
    def test_valid_snapshot_read_handles_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "done",
                        "dry_run": True,
                        "completed_at": "2026-06-06T10:00:00+00:00",
                        "unexpected_future_field": {"kept": True},
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)

        self.assertTrue(result.exists)
        self.assertTrue(result.valid)
        self.assertEqual(result.snapshot.status, "done")
        self.assertTrue(result.snapshot.dry_run)
        self.assertIn("unexpected_future_field", result.snapshot.raw_fields)

    def test_report_only_is_not_treated_as_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "project": "NovaBotV2",
                        "status": "done",
                        "report_only": True,
                        "completed_at": "2026-06-11T10:39:41+00:00",
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)

        self.assertIsNone(result.snapshot.dry_run)

    def test_novabotv2_live_state_reads_armed_state_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "project": "NovaBotV2",
                        "status": "done",
                        "report_only": True,
                        "completed_at": "2026-06-11T10:39:41+00:00",
                        "live_trading_active": True,
                        "armed_state": {
                            "allow_live_trades": True,
                            "require_double_arm": True,
                            "live_arm_present": True,
                            "recent_live_execution": None,
                            "live_trading_active": True,
                            "source": "derived_reporting_only",
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 11, 12, tzinfo=timezone.utc),
            )

        self.assertTrue(result.snapshot.live_trading_active)
        self.assertIsNone(result.snapshot.dry_run)
        self.assertEqual(summary.health_score, 90)
        self.assertEqual(summary.health_status, "HEALTHY")
        self.assertNotIn("live_state_contradiction", summary.warnings)

    def test_live_state_reads_top_level_when_armed_state_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "done",
                        "dry_run": False,
                        "completed_at": "2026-06-11T10:39:41+00:00",
                        "live_trading_active": True,
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 11, 12, tzinfo=timezone.utc),
            )

        self.assertTrue(result.snapshot.live_trading_active)
        self.assertFalse(result.snapshot.dry_run)
        self.assertEqual(summary.health_score, 90)
        self.assertEqual(summary.health_status, "HEALTHY")

    def test_dry_run_and_live_state_contradiction_warns_and_caps_health(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "project": "NovaBotV2",
                        "status": "done",
                        "dry_run": True,
                        "report_only": True,
                        "completed_at": "2026-06-11T10:39:41+00:00",
                        "live_trading_active": True,
                        "armed_state": {
                            "allow_live_trades": True,
                            "require_double_arm": True,
                            "live_arm_present": True,
                            "recent_live_execution": None,
                            "live_trading_active": True,
                            "source": "derived_reporting_only",
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 11, 12, tzinfo=timezone.utc),
            )

        self.assertIn("live_state_contradiction", summary.warnings)
        self.assertLessEqual(summary.health_score, 59)
        self.assertEqual(summary.health_status, "DEGRADED")

    def test_missing_snapshot_returns_warning(self):
        result = read_bot_snapshot("NovaBotV2Options", Path("missing-result.json"))
        self.assertFalse(result.exists)
        self.assertFalse(result.valid)
        self.assertEqual(result.warnings, ("NovaBotV2Options snapshot missing",))

    def test_invalid_json_returns_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text("{bad json", encoding="utf-8")
            result = read_bot_snapshot("NovaBotV2", path)

        self.assertTrue(result.exists)
        self.assertFalse(result.valid)
        self.assertEqual(result.warnings, ("NovaBotV2 snapshot invalid JSON",))

    def test_stale_snapshot_generates_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "done",
                        "dry_run": True,
                        "completed_at": "2026-01-01T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 6, tzinfo=timezone.utc),
            )

        self.assertIn("NovaBotV2 snapshot stale", summary.warnings)
        self.assertLess(summary.health_score, 80)

    def test_health_score_generation_for_fresh_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "done",
                        "dry_run": True,
                        "completed_at": "2026-06-06T10:00:00+00:00",
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            )

        self.assertEqual(summary.health_score, 100)
        self.assertEqual(summary.health_status, "HEALTHY")
        self.assertEqual(summary.warnings, ())

    def test_unknown_status_generates_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps({"dry_run": True, "completed_at": "2026-06-06T10:00:00+00:00"}),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2Options", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            )

        self.assertIn("NovaBotV2Options status unknown", summary.warnings)

    def test_options_snapshot_shape_reads_updated_at_utc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result_snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "project": "NovaBotV2Options",
                        "status": "DRY_RUN_COMPLETE",
                        "dry_run": True,
                        "updated_at_utc": "2026-06-06T10:00:00+00:00",
                        "broker_execution_enabled": False,
                        "order_placement_enabled": False,
                        "money_movement_enabled": False,
                    }
                ),
                encoding="utf-8",
            )
            result = read_bot_snapshot("NovaBotV2Options", path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            )

        self.assertEqual(result.snapshot.updated_at, "2026-06-06T10:00:00+00:00")
        self.assertEqual(result.snapshot.status, "DRY_RUN_COMPLETE")
        self.assertEqual(summary.health_status, "HEALTHY")
        self.assertNotIn("NovaBotV2Options update timestamp missing", summary.warnings)

    def test_missing_market_regime_future_snapshot_is_warning_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing_market_regime.json"
            result = read_bot_snapshot("MarketRegimeBot", missing_path)
            summary = evaluate_snapshot_health(
                result,
                now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            )

        self.assertIn("MarketRegimeBot", FUTURE_SNAPSHOT_PATHS)
        self.assertFalse(result.exists)
        self.assertEqual(summary.health_status, "UNKNOWN")
        self.assertEqual(summary.warnings, ("MarketRegimeBot snapshot missing",))


if __name__ == "__main__":
    unittest.main()
