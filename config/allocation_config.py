"""Static default allocation settings for the skeleton phase."""

from pathlib import Path

DEFAULT_ALLOCATION_PERCENTAGES = {
    "NovaBotV2": 90.0,
    "NovaBotV2Options": 10.0,
    "NovaCryptoBot": 0.0,
    "CashReserve": 0.0,
}

DEFAULT_CASH_RESERVE_MINIMUM_PERCENTAGE = 0.0

KNOWN_BOTS = {
    "NovaBotV2",
    "NovaBotV2Options",
    "NovaCryptoBot",
    "CashReserve",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = PROJECT_ROOT.parent

DEFAULT_SNAPSHOT_PATHS = {
    "NovaBotV2": APPS_ROOT / "NovaBotV2" / "data" / "system" / "result_snapshot.json",
    "NovaBotV2Options": APPS_ROOT
    / "NovaBotV2Options"
    / "data"
    / "system"
    / "result_snapshot.json",
}

FUTURE_SNAPSHOT_PATHS = {
    "MarketRegimeBot": APPS_ROOT
    / "MarketRegimeBot"
    / "data"
    / "system"
    / "result_snapshot.json",
}

SNAPSHOT_STALE_AFTER_HOURS = 48
REGIME_STALE_AFTER_HOURS = 24

ALLOCATION_CONTRACT_VERSION = "1.0"

ALLOCATION_HISTORY_PATH = PROJECT_ROOT / "data" / "system" / "allocation_history.json"
ALLOCATION_HISTORY_MAX_ENTRIES = 100

COMPLIANCE_TOLERANCE_PCT = 5.0
