"""CLI entrypoint for the NovaAllocationBot dry-run allocation cycle."""

from __future__ import annotations

import argparse
import json

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
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("Only --once is supported in the skeleton phase.")
    result = run_allocation_cycle(write_snapshot=True)
    print(
        json.dumps(
            {
                "status": result["status"],
                "dry_run": True,
                "health_evaluated": result["health_evaluated"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
