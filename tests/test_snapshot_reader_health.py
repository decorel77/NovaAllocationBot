import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
