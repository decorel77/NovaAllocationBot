"""Phase 3 tests: regime-based allocation from MarketRegimeBot snapshot."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.market_regime_adapter import read_market_regime_snapshot
from core.regime_allocation_engine import (
    FALLBACK_ALLOCATION,
    REGIME_ALLOCATIONS,
    build_regime_allocation,
)
from workflow import allocation_cycle


def _write_snapshot(tmp: Path, data: dict) -> Path:
    p = tmp / "result_snapshot.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestRegimeAdapter(unittest.TestCase):
    NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)

    def test_bull_regime_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(Path(d), {"market_regime": "BULL", "confidence": 80, "project": "MarketRegimeBot"})
            result = read_market_regime_snapshot(p)
        self.assertEqual(result.market_regime, "BULL")
        self.assertEqual(result.confidence, 80)
        self.assertEqual(result.input_source, "MarketRegimeBot")
        self.assertFalse(result.is_fallback)

    def test_missing_snapshot_fallback(self):
        result = read_market_regime_snapshot(Path("/nonexistent/path/result_snapshot.json"))
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.market_regime, "UNKNOWN")
        self.assertEqual(result.input_source, "fallback")
        self.assertIn("snapshot_missing", result.warnings)

    def test_corrupt_json_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "result_snapshot.json"
            p.write_text("{not valid json{{", encoding="utf-8")
            result = read_market_regime_snapshot(p)
        self.assertTrue(result.is_fallback)
        self.assertIn("snapshot_corrupt", result.warnings)

    def test_unknown_regime_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(Path(d), {"market_regime": "SUPER_BULLISH", "confidence": 90})
            result = read_market_regime_snapshot(p)
        self.assertTrue(result.is_fallback)
        self.assertTrue(any("unknown_regime" in w for w in result.warnings))

    def test_missing_regime_field_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(Path(d), {"confidence": 70})
            result = read_market_regime_snapshot(p)
        self.assertTrue(result.is_fallback)
        self.assertIn("regime_missing", result.warnings)

    def test_missing_confidence_defaults_to_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(Path(d), {"market_regime": "BEAR"})
            result = read_market_regime_snapshot(p)
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.confidence, 0)

    def test_fresh_timestamp_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(
                Path(d),
                {
                    "market_regime": "SIDEWAYS",
                    "confidence": 71,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "2026-06-11T10:00:00Z",
                    "fresh_until": "2026-06-11T14:00:00+00:00",
                },
            )
            result = read_market_regime_snapshot(p, now=self.NOW)

        self.assertTrue(result.data_is_real)
        self.assertTrue(result.regime_is_real)
        self.assertEqual(result.produced_at, "2026-06-11T10:00:00Z")
        self.assertEqual(result.fresh_until, "2026-06-11T14:00:00+00:00")
        self.assertNotIn("regime_stale", result.warnings)

    def test_stale_timestamp_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(
                Path(d),
                {
                    "market_regime": "SIDEWAYS",
                    "confidence": 71,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "2026-06-09T11:00:00+00:00",
                    "fresh_until": "2026-06-10T12:00:00+00:00",
                },
            )
            result = read_market_regime_snapshot(p, now=self.NOW)

        self.assertFalse(result.data_is_real)
        self.assertFalse(result.regime_is_real)
        self.assertIn("regime_stale", result.warnings)
        self.assertEqual(result.market_regime, "SIDEWAYS")

    def test_missing_timestamp_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(
                Path(d),
                {
                    "market_regime": "BULL",
                    "confidence": 80,
                    "data_is_real": True,
                    "input_source": "yfinance",
                },
            )
            result = read_market_regime_snapshot(p, now=self.NOW)

        self.assertFalse(result.data_is_real)
        self.assertFalse(result.regime_is_real)
        self.assertIn("regime_timestamp_missing", result.warnings)
        self.assertEqual(result.market_regime, "BULL")

    def test_unparseable_timestamp_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(
                Path(d),
                {
                    "market_regime": "BEAR",
                    "confidence": 70,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "not-a-time",
                    "fresh_until": "2026-06-11T14:00:00+00:00",
                },
            )
            result = read_market_regime_snapshot(p, now=self.NOW)

        self.assertFalse(result.data_is_real)
        self.assertFalse(result.regime_is_real)
        self.assertIn("regime_timestamp_unparseable", result.warnings)
        self.assertEqual(result.market_regime, "BEAR")

    def test_future_timestamp_accepted_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_snapshot(
                Path(d),
                {
                    "market_regime": "HIGH_VOLATILITY",
                    "confidence": 65,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "2026-06-11T13:00:00",
                    "fresh_until": "2026-06-11T15:00:00",
                },
            )
            result = read_market_regime_snapshot(p, now=self.NOW)

        self.assertTrue(result.data_is_real)
        self.assertTrue(result.regime_is_real)
        self.assertIn("regime_timestamp_future", result.warnings)


class TestRegimeAllocationEngine(unittest.TestCase):
    def _allocation_for(self, regime: str, confidence: int = 80) -> dict:
        from core.market_regime_adapter import RegimeReadResult
        regime_result = RegimeReadResult(
            market_regime=regime,
            confidence=confidence,
            input_source="MarketRegimeBot",
            reason=f"test {regime}",
            is_fallback=False,
        )
        result = build_regime_allocation(regime_result)
        result.validate()
        return result.to_dict()

    def test_bull_allocation(self):
        d = self._allocation_for("BULL")
        self.assertEqual(d["recommended_allocation"]["NovaBotV2"], 90)
        self.assertEqual(d["recommended_allocation"]["NovaBotV2Options"], 10)
        self.assertEqual(d["recommended_allocation"]["Cash"], 0)
        self.assertEqual(d["market_regime"], "BULL")
        self.assertEqual(d["input_source"], "MarketRegimeBot")
        self.assertEqual(d["status"], "SAFE_DRY_RUN_ALLOCATION")
        self.assertTrue(d["dry_run"])

    def test_sideways_allocation(self):
        d = self._allocation_for("SIDEWAYS")
        self.assertEqual(d["recommended_allocation"]["NovaBotV2"], 80)
        self.assertEqual(d["recommended_allocation"]["NovaBotV2Options"], 10)
        self.assertEqual(d["recommended_allocation"]["Cash"], 10)

    def test_bear_allocation(self):
        d = self._allocation_for("BEAR")
        self.assertEqual(d["recommended_allocation"]["NovaBotV2"], 70)
        self.assertEqual(d["recommended_allocation"]["NovaBotV2Options"], 5)
        self.assertEqual(d["recommended_allocation"]["Cash"], 25)

    def test_high_volatility_allocation(self):
        d = self._allocation_for("HIGH_VOLATILITY")
        self.assertEqual(d["recommended_allocation"]["NovaBotV2"], 50)
        self.assertEqual(d["recommended_allocation"]["NovaBotV2Options"], 0)
        self.assertEqual(d["recommended_allocation"]["Cash"], 50)

    def test_all_allocations_total_100(self):
        for regime in ("BULL", "SIDEWAYS", "BEAR", "HIGH_VOLATILITY"):
            with self.subTest(regime=regime):
                d = self._allocation_for(regime)
                self.assertEqual(sum(d["recommended_allocation"].values()), 100)

    def test_fallback_allocation(self):
        from core.market_regime_adapter import RegimeReadResult
        regime_result = RegimeReadResult(
            market_regime="UNKNOWN",
            confidence=0,
            input_source="fallback",
            reason="snapshot missing",
            is_fallback=True,
            warnings=("snapshot_missing",),
        )
        result = build_regime_allocation(regime_result)
        d = result.to_dict()
        self.assertEqual(d["recommended_allocation"]["NovaBotV2"], 90)
        self.assertEqual(d["recommended_allocation"]["NovaBotV2Options"], 10)
        self.assertEqual(d["recommended_allocation"]["Cash"], 0)
        self.assertEqual(d["input_source"], "fallback")
        self.assertIn("Fallback", d["reason"])

    def test_fallback_reason_is_explicit(self):
        from core.market_regime_adapter import RegimeReadResult
        regime_result = RegimeReadResult(
            market_regime="UNKNOWN",
            confidence=0,
            input_source="fallback",
            reason="MarketRegimeBot snapshot missing",
            is_fallback=True,
        )
        result = build_regime_allocation(regime_result)
        self.assertIn("Fallback", result.reason)

    def test_all_safety_flags_false(self):
        d = self._allocation_for("BULL")
        for flag in (
            "broker_execution_enabled",
            "order_placement_enabled",
            "money_movement_enabled",
            "live_trading_enabled",
            "allocation_export_enabled",
            "writes_to_other_projects_enabled",
        ):
            self.assertFalse(d[flag], f"{flag} must be False")

    def test_project_field(self):
        d = self._allocation_for("BULL")
        self.assertEqual(d["project"], "NovaAllocationBot")


class TestRegimeAllocationCycleIntegration(unittest.TestCase):
    def test_cycle_includes_regime_allocation(self):
        with tempfile.TemporaryDirectory() as d:
            regime_path = _write_snapshot(Path(d), {"market_regime": "BULL", "confidence": 80})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False,
                regime_snapshot_path=regime_path,
            )
        self.assertIn("regime_allocation", result)
        ra = result["regime_allocation"]
        self.assertEqual(ra["market_regime"], "BULL")
        self.assertEqual(ra["status"], "SAFE_DRY_RUN_ALLOCATION")

    def test_cycle_regime_fallback_on_missing_snapshot(self):
        result = allocation_cycle.run_allocation_cycle(
            write_snapshot=False,
            regime_snapshot_path=Path("/nonexistent/snapshot.json"),
        )
        ra = result["regime_allocation"]
        self.assertEqual(ra["input_source"], "fallback")
        self.assertTrue(ra["dry_run"])

    def test_snapshot_contains_regime_allocation(self):
        with tempfile.TemporaryDirectory() as d:
            regime_path = _write_snapshot(Path(d), {"market_regime": "SIDEWAYS", "confidence": 60})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=True,
                regime_snapshot_path=regime_path,
            )
        written = json.loads(Path(result["result_snapshot_path"]).read_text(encoding="utf-8-sig"))
        self.assertIn("regime_allocation", written)
        ra = written["regime_allocation"]
        self.assertEqual(ra["market_regime"], "SIDEWAYS")
        self.assertEqual(ra["recommended_allocation"]["NovaBotV2"], 80)
        self.assertEqual(ra["recommended_allocation"]["Cash"], 10)

    def test_no_writes_outside_novaallocationsbot(self):
        with tempfile.TemporaryDirectory() as d:
            regime_path = _write_snapshot(Path(d), {"market_regime": "BEAR", "confidence": 70})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=True,
                regime_snapshot_path=regime_path,
            )
        written_path = Path(result["result_snapshot_path"]).resolve()
        project_root = allocation_cycle.PROJECT_ROOT.resolve()
        self.assertIn(project_root, written_path.parents)

    def test_no_broker_order_trading_imports(self):
        allocation_cycle.run_allocation_cycle(write_snapshot=False)
        forbidden_fragments = ("broker", "order", "trading")
        imported = [
            name for name in sys.modules
            if any(fragment in name.lower() for fragment in forbidden_fragments)
            and not name.startswith("unittest")
            and not name.startswith("test")
            and "allocation" not in name.lower()
        ]
        self.assertEqual(imported, [])


if __name__ == "__main__":
    unittest.main()
