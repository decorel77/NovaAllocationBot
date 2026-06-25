"""Read-only adapter for MarketRegimeBot result snapshot.

Reads regime information from MarketRegimeBot's snapshot. Never writes to that
project. Falls back safely on missing file, corrupt JSON, or missing fields.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.allocation_config import FUTURE_SNAPSHOT_PATHS, REGIME_STALE_AFTER_HOURS

KNOWN_REGIMES = {"BULL", "SIDEWAYS", "BEAR", "HIGH_VOLATILITY"}

_DEFAULT_REGIME_SNAPSHOT_PATH: Path = FUTURE_SNAPSHOT_PATHS["MarketRegimeBot"]


@dataclass(frozen=True)
class RegimeReadResult:
    market_regime: str
    confidence: int
    input_source: str
    reason: str
    is_fallback: bool
    raw_data: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    produced_at: str | None = None
    fresh_until: str | None = None
    # REPAIR-007: realness of the upstream regime (REPAIR-005 canonical contract).
    # True only when MarketRegimeBot stamped data_is_real=true (live market data).
    # Fixture/unverified/stale regimes leave this False so the allocator refuses
    # to treat the regime as authoritative.
    data_is_real: bool = False

    @property
    def regime_is_real(self) -> bool:
        """Usable as an authoritative regime: real data and a known regime."""
        return self.data_is_real and not self.is_fallback


def read_market_regime_snapshot(
    path: Path | None = None,
    now: datetime | None = None,
) -> RegimeReadResult:
    now = now or datetime.now(timezone.utc)
    snapshot_path = Path(path) if path is not None else _DEFAULT_REGIME_SNAPSHOT_PATH

    if not snapshot_path.exists():
        return _fallback("MarketRegimeBot snapshot missing", warnings=("snapshot_missing",))

    try:
        text = snapshot_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return _fallback(f"MarketRegimeBot snapshot unreadable: {exc}", warnings=("snapshot_unreadable",))

    if not text:
        return _fallback("MarketRegimeBot snapshot empty", warnings=("snapshot_empty",))

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _fallback("MarketRegimeBot snapshot invalid JSON", warnings=("snapshot_corrupt",))

    if not isinstance(payload, dict):
        return _fallback("MarketRegimeBot snapshot root is not an object", warnings=("snapshot_corrupt",))

    regime = payload.get("market_regime")
    if not isinstance(regime, str) or not regime.strip():
        return _fallback("market_regime field missing or invalid", warnings=("regime_missing",), raw=payload)

    regime = regime.strip().upper()
    if regime not in KNOWN_REGIMES:
        return _fallback(
            f"Unknown market_regime '{regime}'; using fallback allocation",
            warnings=(f"unknown_regime:{regime}",),
            raw=payload,
        )

    confidence = _safe_confidence(payload.get("confidence"))

    # REPAIR-007: only a snapshot stamped data_is_real=true (REPAIR-005 contract)
    # may be treated as a verified-real regime. A fixture/unverified regime is
    # still surfaced for diagnostics but carries a warning and data_is_real=False
    # so the authoritative allocator refuses to let it steer the allocation.
    timestamp_warnings, timestamps_are_fresh = _freshness_warnings(payload, now)
    data_is_real = payload.get("data_is_real") is True and timestamps_are_fresh
    source_raw = payload.get("input_source")
    upstream_source = (
        source_raw.strip() if isinstance(source_raw, str) and source_raw.strip() else "unknown"
    )

    warnings: list[str] = list(timestamp_warnings)
    reason = f"Regime '{regime}' read from MarketRegimeBot snapshot (confidence {confidence})"
    if payload.get("data_is_real") is not True:
        warnings.append("regime_unverified")
        reason += f" — UNVERIFIED (data_is_real != true, input_source={upstream_source!r})"
    if not timestamps_are_fresh:
        reason += " — REFUSED (regime timestamp missing, unparseable, or stale)"

    return RegimeReadResult(
        market_regime=regime,
        confidence=confidence,
        input_source="MarketRegimeBot",
        reason=reason,
        is_fallback=False,
        raw_data=dict(payload),
        warnings=tuple(warnings),
        produced_at=_timestamp_string(payload, "produced_at"),
        fresh_until=_timestamp_string(payload, "fresh_until"),
        data_is_real=data_is_real,
    )


def _fallback(
    reason: str,
    warnings: tuple[str, ...] = (),
    raw: dict[str, Any] | None = None,
) -> RegimeReadResult:
    return RegimeReadResult(
        market_regime="UNKNOWN",
        confidence=0,
        input_source="fallback",
        reason=reason,
        is_fallback=True,
        raw_data=raw or {},
        warnings=warnings,
    )


def _freshness_warnings(
    payload: dict[str, Any],
    now: datetime,
) -> tuple[tuple[str, ...], bool]:
    warnings: list[str] = []
    produced_at_raw = _timestamp_string(payload, "produced_at")
    fresh_until_raw = _timestamp_string(payload, "fresh_until")

    if produced_at_raw is None or fresh_until_raw is None:
        return ("regime_timestamp_missing",), False

    produced_at = _parse_timestamp(produced_at_raw)
    fresh_until = _parse_timestamp(fresh_until_raw)
    if produced_at is None or fresh_until is None:
        return ("regime_timestamp_unparseable",), False

    if produced_at > now:
        warnings.append("regime_timestamp_future")
    elif now - produced_at > timedelta(hours=REGIME_STALE_AFTER_HOURS):
        warnings.append("regime_stale")

    if fresh_until < now:
        warnings.append("regime_stale")

    return tuple(dict.fromkeys(warnings)), "regime_stale" not in warnings


def _safe_confidence(value: Any) -> int:
    """Coerce a snapshot ``confidence`` field to a finite, non-negative int.

    Fail-closed to 0 on malformed input. ``json.loads`` parses bare ``NaN`` /
    ``Infinity`` / ``-Infinity`` by default, and ``int(nan)`` / ``int(inf)``
    raise ``ValueError`` / ``OverflowError`` -- so a corrupt upstream regime
    snapshot must never reach a raw ``int(...)`` cast. A bool (an ``int``
    subclass), a non-finite float, or a non-numeric value is treated as
    malformed and degrades to 0 rather than crashing or inflating confidence.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return max(int(value), 0)


def _timestamp_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
