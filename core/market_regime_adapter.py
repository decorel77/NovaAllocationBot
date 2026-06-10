"""Read-only adapter for MarketRegimeBot result snapshot.

Reads regime information from MarketRegimeBot's snapshot. Never writes to that
project. Falls back safely on missing file, corrupt JSON, or missing fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.allocation_config import FUTURE_SNAPSHOT_PATHS

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
) -> RegimeReadResult:
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

    confidence_raw = payload.get("confidence")
    confidence = int(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0

    # REPAIR-007: only a snapshot stamped data_is_real=true (REPAIR-005 contract)
    # may be treated as a verified-real regime. A fixture/unverified regime is
    # still surfaced for diagnostics but carries a warning and data_is_real=False
    # so the authoritative allocator refuses to let it steer the allocation.
    data_is_real = payload.get("data_is_real") is True
    source_raw = payload.get("input_source")
    upstream_source = (
        source_raw.strip() if isinstance(source_raw, str) and source_raw.strip() else "unknown"
    )

    warnings: tuple[str, ...] = ()
    reason = f"Regime '{regime}' read from MarketRegimeBot snapshot (confidence {confidence})"
    if not data_is_real:
        warnings = ("regime_unverified",)
        reason += f" — UNVERIFIED (data_is_real != true, input_source={upstream_source!r})"

    return RegimeReadResult(
        market_regime=regime,
        confidence=confidence,
        input_source="MarketRegimeBot",
        reason=reason,
        is_fallback=False,
        raw_data=dict(payload),
        warnings=warnings,
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
