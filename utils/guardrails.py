"""Runtime guardrails for advisory-only NovaAllocationBot startup."""

from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger(__name__)

ADVISORY_ONLY: bool = True

BANNED_BROKER_PACKAGES: tuple[str, ...] = (
    "ib_insync",
    "ibapi",
    "alpaca_trade_api",
    "alpaca",
    "ccxt",
    "robin_stocks",
    "tastytrade",
    "tda",
    "schwab",
)


class GuardrailViolation(RuntimeError):
    """Raised when a hard advisory-mode guardrail is violated."""


def assert_advisory_only() -> None:
    if not ADVISORY_ONLY:
        raise GuardrailViolation("ADVISORY_ONLY has been set to False.")


def check_broker_imports() -> None:
    """Fail if broker-capable packages are importable in this environment."""
    found = [
        package
        for package in BANNED_BROKER_PACKAGES
        if importlib.util.find_spec(package) is not None
    ]
    if found:
        raise GuardrailViolation(
            "GUARDRAIL VIOLATION - banned broker packages are importable in "
            f"advisory NovaAllocationBot environment: {found}. Use a broker-free "
            "repo-local virtualenv."
        )
    logger.info("Broker package guardrail passed.")


def run_all_checks() -> None:
    """Run hard startup guardrails before any advisory cycle code executes."""
    assert_advisory_only()
    check_broker_imports()
