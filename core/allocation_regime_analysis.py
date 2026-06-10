"""
Regime-based allocation evaluation for NovaAllocationBot.

Groups allocation_history.json entries by regime and computes per-regime
recommendation quality. Writes output to data/reports/allocation_regime_analysis.md.

Input:  data/system/allocation_history.json  (canonical AllocationHistoryTracker
        location — REPAIR-007 fixed an earlier data/reports vs data/system mismatch)
Output: data/reports/allocation_regime_analysis.md

ADVISORY_ONLY. Read-only input. No broker. Writes to data/reports/ only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json

from config.allocation_config import ALLOCATION_HISTORY_PATH

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
# REPAIR-007: read from the canonical history location the tracker actually writes.
_HISTORY_FILE = ALLOCATION_HISTORY_PATH
_OUTPUT_FILE = _DEFAULT_REPORTS_DIR / "allocation_regime_analysis.md"


@dataclass
class RegimeAllocationStats:
    regime: str
    entry_count: int = 0
    avg_equity_pct: Optional[float] = None
    avg_cash_pct: Optional[float] = None
    warning_count: int = 0
    entries: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def finalize(self) -> None:
        if not self.entries:
            return
        # REPAIR-007: read the real history schema — each entry has an
        # ``allocation`` dict {NovaBotV2, NovaBotV2Options, Cash}.
        equity_vals = [
            e["allocation"].get("NovaBotV2", 0.0)
            for e in self.entries
            if isinstance(e.get("allocation"), dict)
        ]
        cash_vals = [
            e["allocation"].get("Cash", 0.0)
            for e in self.entries
            if isinstance(e.get("allocation"), dict)
        ]
        if equity_vals:
            self.avg_equity_pct = sum(equity_vals) / len(equity_vals)
        if cash_vals:
            self.avg_cash_pct = sum(cash_vals) / len(cash_vals)
        self.warning_count = sum(
            len(e.get("warnings", [])) for e in self.entries
        )


def load_history(path: Path = _HISTORY_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else data.get("entries", [])


def analyse(entries: list[dict[str, Any]]) -> list[RegimeAllocationStats]:
    buckets: dict[str, RegimeAllocationStats] = {}

    for e in entries:
        # REPAIR-007: the real history schema carries ``regime`` at top level.
        regime = str(e.get("regime") or "UNKNOWN")
        if regime not in buckets:
            buckets[regime] = RegimeAllocationStats(regime=regime)
        s = buckets[regime]
        s.entry_count += 1
        s.entries.append(e)

    for s in buckets.values():
        s.finalize()

    return sorted(buckets.values(), key=lambda s: -s.entry_count)


def render_report(stats: list[RegimeAllocationStats], total: int) -> str:
    lines = [
        "# NovaAllocationBot — Regime-Based Allocation Evaluation",
        "",
        f"**Total history entries:** {total}",
        "",
        "## Per-Regime Summary",
        "",
        "| Regime | Entries | Avg Equity % | Avg Cash % | Warnings |",
        "|---|---|---|---|---|",
    ]
    for s in stats:
        eq = f"{s.avg_equity_pct:.1f}%" if s.avg_equity_pct is not None else "—"
        ca = f"{s.avg_cash_pct:.1f}%" if s.avg_cash_pct is not None else "—"
        lines.append(f"| {s.regime} | {s.entry_count} | {eq} | {ca} | {s.warning_count} |")

    if not stats:
        lines.append("| — | 0 | — | — | — |")

    lines += [
        "",
        "## Notes",
        "",
        "- All recommendations are advisory only (no broker execution)",
        "- Avg Equity % = average NovaBotV2 weight; Avg Cash % = average Cash weight",
        "- Source: data/system/allocation_history.json",
    ]
    return "\n".join(lines) + "\n"


def generate(
    history_path: Path = _HISTORY_FILE,
    output_path: Path = _OUTPUT_FILE,
) -> Path:
    entries = load_history(history_path)
    stats = analyse(entries)
    report = render_report(stats, len(entries))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    out = generate()
    print(f"Written: {out}")
