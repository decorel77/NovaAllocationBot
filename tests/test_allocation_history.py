"""Phase 4 tests: allocation history, contract version, snapshot validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config.allocation_config import (
    ALLOCATION_CONTRACT_VERSION,
    ALLOCATION_HISTORY_MAX_ENTRIES,
    ALLOCATION_HISTORY_PATH,
)
from core.allocation_history import (
    append_allocation_history,
    read_allocation_history,
    reset_allocation_history,
)
from workflow import allocation_cycle


_SAMPLE_ALLOCATION = {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}


def _run_cycle_in_temp_project(root: Path, **kwargs):
    original_root = allocation_cycle.PROJECT_ROOT
    try:
        allocation_cycle.PROJECT_ROOT = root
        return allocation_cycle.run_allocation_cycle(**kwargs)
    finally:
        allocation_cycle.PROJECT_ROOT = original_root


class TestHistoryAppend(unittest.TestCase):
    def test_append_creates_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            append_allocation_history("BULL", 80, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            self.assertTrue(p.exists())
            entries = read_allocation_history(p)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["regime"], "BULL")

    def test_append_accumulates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            for regime in ("BULL", "SIDEWAYS", "BEAR"):
                append_allocation_history(regime, 70, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            entries = read_allocation_history(p)
            self.assertEqual(len(entries), 3)
            self.assertEqual([e["regime"] for e in entries], ["BULL", "SIDEWAYS", "BEAR"])

    def test_entry_has_required_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            append_allocation_history("BEAR", 60, {"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25}, "MarketRegimeBot", history_path=p)
            entry = read_allocation_history(p)[0]
            for field in ("timestamp", "regime", "confidence", "allocation", "input_source", "allocation_version"):
                self.assertIn(field, entry, f"Missing field: {field}")

    def test_entry_stores_allocation_version(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            append_allocation_history("BULL", 80, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            entry = read_allocation_history(p)[0]
            self.assertEqual(entry["allocation_version"], ALLOCATION_CONTRACT_VERSION)


class TestHistoryTrim(unittest.TestCase):
    def test_trim_to_max_entries(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            for i in range(ALLOCATION_HISTORY_MAX_ENTRIES + 20):
                append_allocation_history("BULL", i % 100, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            entries = read_allocation_history(p)
            self.assertEqual(len(entries), ALLOCATION_HISTORY_MAX_ENTRIES)

    def test_trim_keeps_most_recent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            regimes = ["BULL", "SIDEWAYS", "BEAR", "HIGH_VOLATILITY"]
            for i in range(ALLOCATION_HISTORY_MAX_ENTRIES + 4):
                r = regimes[i % len(regimes)]
                append_allocation_history(r, 50, _SAMPLE_ALLOCATION, "MarketRegimeBot", reason=f"entry_{i}", history_path=p)
            entries = read_allocation_history(p)
            self.assertEqual(len(entries), ALLOCATION_HISTORY_MAX_ENTRIES)
            last_reason = entries[-1]["reason"]
            self.assertIn(str(ALLOCATION_HISTORY_MAX_ENTRIES + 3), last_reason)


class TestCorruptHistoryRecovery(unittest.TestCase):
    def test_corrupt_json_resets_gracefully(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            p.write_text("{corrupt!!!", encoding="utf-8")
            append_allocation_history("BULL", 80, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            entries = read_allocation_history(p)
            self.assertEqual(len(entries), 1)

    def test_empty_file_treated_as_empty_history(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            p.write_text("", encoding="utf-8")
            append_allocation_history("SIDEWAYS", 60, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            self.assertEqual(len(read_allocation_history(p)), 1)

    def test_wrong_type_at_root_resets(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            append_allocation_history("BEAR", 55, _SAMPLE_ALLOCATION, "fallback", history_path=p)
            self.assertEqual(len(read_allocation_history(p)), 1)

    def test_missing_entries_key_resets(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            p.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
            append_allocation_history("BULL", 80, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            self.assertEqual(len(read_allocation_history(p)), 1)

    def test_reset_clears_history(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.json"
            append_allocation_history("BULL", 80, _SAMPLE_ALLOCATION, "MarketRegimeBot", history_path=p)
            reset_allocation_history(p)
            self.assertEqual(read_allocation_history(p), [])


class TestContractVersion(unittest.TestCase):
    def test_contract_version_defined(self):
        self.assertIsInstance(ALLOCATION_CONTRACT_VERSION, str)
        self.assertTrue(len(ALLOCATION_CONTRACT_VERSION) > 0)

    def test_regime_allocation_includes_version(self):
        result = allocation_cycle.run_allocation_cycle(
            write_snapshot=False,
            regime_snapshot_path=Path("/nonexistent/snapshot.json"),
        )
        ra = result["regime_allocation"]
        self.assertIn("allocation_version", ra)
        self.assertEqual(ra["allocation_version"], ALLOCATION_CONTRACT_VERSION)

    def test_snapshot_contains_allocation_version(self):
        with tempfile.TemporaryDirectory() as d:
            regime_file = Path(d) / "regime.json"
            history_file = Path(d) / "history.json"
            result_file = Path(d) / "result_snapshot.json"
            regime_file.write_text(json.dumps({"market_regime": "BULL", "confidence": 80}), encoding="utf-8")
            result = _run_cycle_in_temp_project(
                Path(d),
                write_snapshot=True,
                regime_snapshot_path=regime_file,
                history_path=history_file,
                result_path=result_file,
            )
            written = json.loads(Path(result["result_snapshot_path"]).read_text(encoding="utf-8-sig"))
        self.assertIn("allocation_version", written["regime_allocation"])
        self.assertEqual(written["regime_allocation"]["allocation_version"], ALLOCATION_CONTRACT_VERSION)


class TestHistoryCycleIntegration(unittest.TestCase):
    def test_cycle_writes_history(self):
        with tempfile.TemporaryDirectory() as d:
            regime_file = Path(d) / "regime.json"
            history_file = Path(d) / "history.json"
            regime_file.write_text(json.dumps({"market_regime": "BEAR", "confidence": 65}), encoding="utf-8")
            _run_cycle_in_temp_project(
                Path(d),
                write_snapshot=True,
                regime_snapshot_path=regime_file,
                history_path=history_file,
                result_path=Path(d) / "result_snapshot.json",
            )
            entries = read_allocation_history(history_file)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["regime"], "BEAR")
            self.assertEqual(entries[0]["confidence"], 65)

    def test_cycle_history_stays_within_max(self):
        with tempfile.TemporaryDirectory() as d:
            regime_file = Path(d) / "regime.json"
            history_file = Path(d) / "history.json"
            regime_file.write_text(json.dumps({"market_regime": "BULL", "confidence": 80}), encoding="utf-8")
            for _ in range(5):
                _run_cycle_in_temp_project(
                    Path(d),
                    write_snapshot=True,
                    regime_snapshot_path=regime_file,
                    history_path=history_file,
                    result_path=Path(d) / "result_snapshot.json",
                )
            entries = read_allocation_history(history_file)
            self.assertLessEqual(len(entries), ALLOCATION_HISTORY_MAX_ENTRIES)

    def test_history_write_refused_outside_project(self):
        outside = Path(tempfile.gettempdir()) / "bad_history.json"
        with self.assertRaises(ValueError):
            from core.allocation_history import _write_history
            _write_history(outside, [])

    def test_cycle_with_injected_paths_does_not_mutate_production_history(self):
        before = ALLOCATION_HISTORY_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            regime_file = root / "regime.json"
            regime_file.write_text(json.dumps({"market_regime": "BULL", "confidence": 80}), encoding="utf-8")
            _run_cycle_in_temp_project(
                root,
                write_snapshot=True,
                regime_snapshot_path=regime_file,
                history_path=root / "history.json",
                result_path=root / "result_snapshot.json",
            )
        after = ALLOCATION_HISTORY_PATH.read_text(encoding="utf-8")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
