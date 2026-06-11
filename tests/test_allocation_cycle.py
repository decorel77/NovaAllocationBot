import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from workflow import allocation_cycle

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _healthy_bot_snapshot(path: Path, *, status: str = "done") -> Path:
    return _write_json(
        path,
        {
            "status": status,
            "dry_run": True,
            "completed_at": "2026-06-11T11:00:00+00:00",
            "errors": [],
        },
    )


def _real_regime_snapshot(
    path: Path,
    *,
    produced_at: str = "2026-06-11T11:00:00+00:00",
    fresh_until: str = "2026-06-11T13:00:00+00:00",
    data_is_real: bool = True,
) -> Path:
    return _write_json(
        path,
        {
            "market_regime": "BULL",
            "confidence": 80,
            "data_is_real": data_is_real,
            "input_source": "yfinance",
            "produced_at": produced_at,
            "fresh_until": fresh_until,
        },
    )


class AllocationCycleTests(unittest.TestCase):
    def test_dry_run_cycle_writes_only_own_result_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_snapshot = _healthy_bot_snapshot(root / "stock.json")
            options_snapshot = _healthy_bot_snapshot(root / "options.json")
            regime_snapshot = _real_regime_snapshot(root / "regime.json")
            original_root = allocation_cycle.PROJECT_ROOT
            original_result = allocation_cycle.RESULT_SNAPSHOT_PATH
            try:
                allocation_cycle.PROJECT_ROOT = root
                allocation_cycle.RESULT_SNAPSHOT_PATH = root / "data" / "system" / "result_snapshot.json"
                result = allocation_cycle.run_allocation_cycle(
                    write_snapshot=True,
                    snapshot_paths={
                        "NovaBotV2": stock_snapshot,
                        "NovaBotV2Options": options_snapshot,
                    },
                    regime_snapshot_path=regime_snapshot,
                    history_path=root / "allocation_history.json",
                    produced_at=NOW,
                )
                result_path = Path(result["result_snapshot_path"]).resolve()
                expected_path = allocation_cycle.RESULT_SNAPSHOT_PATH.resolve()
                expected_path_exists = expected_path.exists()
                payload = json.loads(expected_path.read_text(encoding="utf-8-sig"))
            finally:
                allocation_cycle.PROJECT_ROOT = original_root
                allocation_cycle.RESULT_SNAPSHOT_PATH = original_result

        self.assertEqual(result_path, expected_path)
        self.assertTrue(expected_path_exists)
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


class AllocationSnapshotEnvelopeTests(unittest.TestCase):
    def _run_with_inputs(
        self,
        root: Path,
        *,
        stock_payload: dict | None = None,
        options_payload: dict | None = None,
        regime_payload: dict | None = None,
        missing_stock: bool = False,
        missing_regime: bool = False,
        write_snapshot: bool = False,
    ) -> dict:
        stock_path = root / "stock.json"
        options_path = root / "options.json"
        regime_path = root / "regime.json"

        if not missing_stock:
            _write_json(
                stock_path,
                stock_payload
                or {
                    "status": "done",
                    "dry_run": True,
                    "completed_at": "2026-06-11T11:00:00+00:00",
                    "errors": [],
                },
            )
        _write_json(
            options_path,
            options_payload
            or {
                "status": "done",
                "dry_run": True,
                "completed_at": "2026-06-11T11:00:00+00:00",
                "errors": [],
            },
        )
        if not missing_regime:
            _write_json(
                regime_path,
                regime_payload
                or {
                    "market_regime": "BULL",
                    "confidence": 80,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "2026-06-11T11:00:00+00:00",
                    "fresh_until": "2026-06-11T13:00:00+00:00",
                },
            )

        original_root = allocation_cycle.PROJECT_ROOT
        original_result = allocation_cycle.RESULT_SNAPSHOT_PATH
        try:
            allocation_cycle.PROJECT_ROOT = root
            allocation_cycle.RESULT_SNAPSHOT_PATH = root / "data" / "system" / "result_snapshot.json"
            return allocation_cycle.run_allocation_cycle(
                write_snapshot=write_snapshot,
                snapshot_paths={
                    "NovaBotV2": stock_path,
                    "NovaBotV2Options": options_path,
                },
                regime_snapshot_path=(root / "missing_regime.json") if missing_regime else regime_path,
                history_path=root / "allocation_history.json",
                produced_at=NOW,
            )
        finally:
            allocation_cycle.PROJECT_ROOT = original_root
            allocation_cycle.RESULT_SNAPSHOT_PATH = original_result

    def test_written_snapshot_has_canonical_envelope_and_old_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self._run_with_inputs(root, write_snapshot=True)
            payload = json.loads(Path(result["result_snapshot_path"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["producer_id"], "NovaAllocationBot")
        self.assertEqual(payload["schema_version"], "allocation_result.v2")
        self.assertIn("produced_at", payload)
        self.assertIn("fresh_until", payload)
        self.assertIn("data_is_real", payload)
        for old_key in (
            "status",
            "dry_run",
            "plan",
            "recommendation",
            "regime_allocation",
            "allocation_compliance",
            "authoritative_allocation",
        ):
            self.assertIn(old_key, payload)

    def test_data_is_real_true_when_all_inputs_real_and_fresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_with_inputs(Path(tmpdir))

        envelope = result["snapshot_envelope"]
        self.assertTrue(envelope["data_is_real"])
        self.assertEqual(envelope["data_is_real_reasons"], [])

    def test_fresh_until_is_parseable_and_after_produced_at(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_with_inputs(Path(tmpdir))

        envelope = result["snapshot_envelope"]
        produced_at = datetime.fromisoformat(envelope["produced_at"])
        fresh_until = datetime.fromisoformat(envelope["fresh_until"])
        self.assertGreater(fresh_until, produced_at)

    def test_data_is_real_false_when_regime_stale_fake_or_missing(self):
        cases = [
            {
                "market_regime": "BULL",
                "confidence": 80,
                "data_is_real": True,
                "input_source": "yfinance",
                "produced_at": "2026-06-09T11:00:00+00:00",
                "fresh_until": "2026-06-10T13:00:00+00:00",
            },
            {
                "market_regime": "BULL",
                "confidence": 80,
                "data_is_real": False,
                "input_source": "fixture",
                "produced_at": "2026-06-11T11:00:00+00:00",
                "fresh_until": "2026-06-11T13:00:00+00:00",
            },
            None,
        ]
        for regime_payload in cases:
            with self.subTest(regime_payload=regime_payload):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = self._run_with_inputs(
                        Path(tmpdir),
                        regime_payload=regime_payload,
                        missing_regime=regime_payload is None,
                    )

                envelope = result["snapshot_envelope"]
                self.assertFalse(envelope["data_is_real"])
                self.assertTrue(envelope["data_is_real_reasons"])

    def test_data_is_real_false_when_bot_snapshot_stale_missing_or_unknown(self):
        cases = [
            {
                "status": "done",
                "dry_run": True,
                "completed_at": "2026-06-01T11:00:00+00:00",
                "errors": [],
            },
            {
                "dry_run": True,
                "completed_at": "2026-06-11T11:00:00+00:00",
                "errors": [],
            },
            None,
        ]
        for stock_payload in cases:
            with self.subTest(stock_payload=stock_payload):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = self._run_with_inputs(
                        Path(tmpdir),
                        stock_payload=stock_payload,
                        missing_stock=stock_payload is None,
                    )

                envelope = result["snapshot_envelope"]
                self.assertFalse(envelope["data_is_real"])
                self.assertTrue(envelope["data_is_real_reasons"])

    def test_data_is_real_false_when_options_snapshot_stale_missing_or_unknown(self):
        cases = [
            {
                "status": "done",
                "dry_run": True,
                "completed_at": "2026-06-01T11:00:00+00:00",
                "errors": [],
            },
            {
                "dry_run": True,
                "completed_at": "2026-06-11T11:00:00+00:00",
                "errors": [],
            },
            None,
        ]
        for options_payload in cases:
            with self.subTest(options_payload=options_payload):
                if options_payload is None:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        root = Path(tmpdir)
                        stock_path = _healthy_bot_snapshot(root / "stock.json")
                        regime_path = _real_regime_snapshot(root / "regime.json")
                        result = allocation_cycle.run_allocation_cycle(
                            write_snapshot=False,
                            snapshot_paths={
                                "NovaBotV2": stock_path,
                                "NovaBotV2Options": root / "missing_options.json",
                            },
                            regime_snapshot_path=regime_path,
                            history_path=root / "allocation_history.json",
                            produced_at=NOW,
                        )
                else:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        result = self._run_with_inputs(
                            Path(tmpdir),
                            options_payload=options_payload,
                        )

                envelope = result["snapshot_envelope"]
                self.assertFalse(envelope["data_is_real"])
                self.assertTrue(envelope["data_is_real_reasons"])


if __name__ == "__main__":
    unittest.main()
