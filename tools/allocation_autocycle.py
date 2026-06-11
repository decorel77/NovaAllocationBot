"""CLI entrypoint for the NovaAllocationBot dry-run allocation cycle."""

from __future__ import annotations

import argparse
import json

from utils.guardrails import run_all_checks
from workflow.allocation_cycle import run_allocation_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a safe NovaAllocationBot dry-run allocation cycle."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one dry-run allocation cycle and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    run_all_checks()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("Only --once is supported in the skeleton phase.")
    result = run_allocation_cycle(write_snapshot=True)
    ra = result.get("regime_allocation", {})
    print(
        json.dumps(
            {
                "status": result["status"],
                "dry_run": True,
                "health_evaluated": result["health_evaluated"],
                "regime_allocation": {
                    "project": ra.get("project"),
                    "status": ra.get("status"),
                    "input_source": ra.get("input_source"),
                    "market_regime": ra.get("market_regime"),
                    "confidence": ra.get("confidence"),
                    "recommended_allocation": ra.get("recommended_allocation"),
                    "reason": ra.get("reason"),
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
