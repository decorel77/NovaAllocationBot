"""QA-015 tests for the Allocation v2 design-only layer."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.allocation_v2_design import (
    DESIGN_SCHEMA_VERSION,
    MAX_RISKY_PCT_BY_REGIME,
    parse_regime_input_v3,
    propose_allocation_v2,
    risky_pct,
)
from workflow import allocation_cycle

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
BASELINE = {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}


def _regime_v3(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "regime_result.v3",
        "producer_id": "MarketRegimeBot",
        "model_version": "v1",
        "market_regime": "BULL",
        "confidence": 80,
        "raw_regime": "BULL",
        "raw_confidence": 80,
        "produced_at": "2026-06-11T11:00:00+00:00",
        "fresh_until": "2026-06-11T13:00:00+00:00",
        "data_is_real": True,
        "input_source": "yfinance",
    }
    payload.update(overrides)
    return payload


def _proposal_for(payload: object):
    regime_input = parse_regime_input_v3(payload, now=NOW)
    return regime_input, propose_allocation_v2(regime_input, BASELINE)


def test_missing_stale_and_fake_regime_data_fail_closed() -> None:
    cases = [
        ({k: v for k, v in _regime_v3().items() if k != "market_regime"}, "missing_field:market_regime"),
        (
            _regime_v3(
                produced_at="2026-06-09T11:00:00+00:00",
                fresh_until="2026-06-10T13:00:00+00:00",
            ),
            "regime_stale",
        ),
        (_regime_v3(data_is_real=False, input_source="fixture"), "regime_not_real"),
    ]

    for payload, expected_refusal in cases:
        regime_input, proposal = _proposal_for(payload)

        assert not regime_input.usable
        assert expected_refusal in regime_input.refusal_reasons
        assert proposal.source == "baseline_fail_closed"
        assert proposal.proposed_allocation == BASELINE
        assert proposal.to_dict()["schema_version"] == DESIGN_SCHEMA_VERSION


def test_unknown_model_version_fails_closed_with_diagnostic_reason() -> None:
    regime_input, proposal = _proposal_for(_regime_v3(model_version="v_next"))

    assert not regime_input.usable
    assert "model_version_unknown:'v_next'" in regime_input.refusal_reasons
    assert proposal.model_version == "v_next"
    assert proposal.source == "baseline_fail_closed"
    assert proposal.proposed_allocation == BASELINE


def test_research_model_version_is_diagnostic_only_until_trusted() -> None:
    regime_input, proposal = _proposal_for(_regime_v3(model_version="v2"))

    assert regime_input.usable
    assert "model_research_stage" in regime_input.warnings
    assert proposal.source == "baseline_model_not_trusted"
    assert proposal.proposed_allocation == BASELINE
    assert proposal.diagnostics["published_regime"] == "BULL"
    assert proposal.diagnostics["untrusted_model_would_propose"] == BASELINE


def test_raw_vs_published_regime_disagreement_uses_more_conservative_cap() -> None:
    regime_input, proposal = _proposal_for(
        _regime_v3(market_regime="BULL", raw_regime="HIGH_VOLATILITY")
    )

    assert regime_input.usable
    assert "raw_published_disagreement" in regime_input.warnings
    assert proposal.source == "regime_aware_v2_design"
    assert proposal.effective_regime == "HIGH_VOLATILITY"
    assert proposal.proposed_allocation == {"NovaBotV2": 50, "NovaBotV2Options": 0, "Cash": 50}
    assert risky_pct(proposal.proposed_allocation) <= MAX_RISKY_PCT_BY_REGIME["HIGH_VOLATILITY"]


def test_high_volatility_caps_and_reduces_risky_allocation() -> None:
    _, proposal = _proposal_for(
        _regime_v3(market_regime="HIGH_VOLATILITY", raw_regime="HIGH_VOLATILITY")
    )

    assert proposal.effective_regime == "HIGH_VOLATILITY"
    assert risky_pct(proposal.proposed_allocation) == 50
    assert risky_pct(proposal.proposed_allocation) < risky_pct(BASELINE)
    assert risky_pct(proposal.proposed_allocation) <= MAX_RISKY_PCT_BY_REGIME["HIGH_VOLATILITY"]


def test_unknown_regime_never_increases_risky_allocation() -> None:
    _, proposal = _proposal_for(_regime_v3(market_regime="UNKNOWN", raw_regime="UNKNOWN"))

    assert proposal.source == "baseline_fail_closed"
    assert proposal.proposed_allocation == BASELINE
    assert risky_pct(proposal.proposed_allocation) <= risky_pct(BASELINE)


def test_current_allocation_result_v2_behavior_remains_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        stock_path = root / "stock.json"
        options_path = root / "options.json"
        regime_path = root / "regime.json"
        stock_path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "dry_run": True,
                    "completed_at": "2026-06-11T11:00:00+00:00",
                    "errors": [],
                }
            ),
            encoding="utf-8",
        )
        options_path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "dry_run": True,
                    "completed_at": "2026-06-11T11:00:00+00:00",
                    "errors": [],
                }
            ),
            encoding="utf-8",
        )
        regime_path.write_text(
            json.dumps(
                {
                    "market_regime": "BULL",
                    "confidence": 80,
                    "data_is_real": True,
                    "input_source": "yfinance",
                    "produced_at": "2026-06-11T11:00:00+00:00",
                    "fresh_until": "2026-06-11T13:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        result = allocation_cycle.run_allocation_cycle(
            write_snapshot=False,
            snapshot_paths={
                "NovaBotV2": stock_path,
                "NovaBotV2Options": options_path,
            },
            regime_snapshot_path=regime_path,
            history_path=root / "allocation_history.json",
            produced_at=NOW,
        )

    assert result["snapshot_envelope"]["schema_version"] == "allocation_result.v2"
    assert "allocation_v2_proposal" not in result
    assert "allocation_proposal" not in result
    assert result["authoritative_allocation"]["source"] == "regime_aware"
    assert result["authoritative_allocation"]["allocation"] == {
        "NovaBotV2": 90,
        "NovaBotV2Options": 10,
        "Cash": 0,
    }
