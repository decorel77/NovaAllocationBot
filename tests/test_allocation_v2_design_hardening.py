"""HARDEN-SWEEP-008: fail-closed hardening for the v2 design layer's bucket math.

``risky_pct`` and ``AllocationV2Proposal.validate`` previously called ``int(pct)``
directly on bucket values, so a non-finite (``inf``/``nan``) or non-numeric
(``str``/``None``) bucket leaked a raw ``OverflowError`` / ``ValueError`` /
``TypeError`` instead of the module's own fail-closed ``AllocationV2DesignError``.
These tests pin the fail-closed behaviour and confirm valid allocations are
unchanged.
"""

from __future__ import annotations

import pytest

from core.allocation_v2_design import (
    AllocationV2DesignError,
    AllocationV2Proposal,
    risky_pct,
)

BASELINE = {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}


def test_risky_pct_valid_unchanged():
    assert risky_pct({"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}) == 100
    # finite floats still truncate exactly as int(pct) did
    assert risky_pct({"NovaBotV2": 60.0, "Cash": 40}) == 60


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan"), "x", None, object()])
def test_risky_pct_fails_closed_on_malformed_bucket(bad):
    with pytest.raises(AllocationV2DesignError):
        risky_pct({"NovaBotV2": bad, "Cash": 0})


@pytest.mark.parametrize("bad", [None, [], 42, "not-a-mapping"])
def test_risky_pct_fails_closed_on_non_mapping(bad):
    with pytest.raises(AllocationV2DesignError):
        risky_pct(bad)


def _proposal(proposed):
    return AllocationV2Proposal(
        proposed_allocation=proposed,
        baseline_allocation=dict(BASELINE),
        source="baseline_fail_closed",
        reason="test",
    )


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), "x", None])
def test_validate_fails_closed_on_non_finite_bucket(bad):
    # A non-finite/non-numeric bucket must raise the module's own error, not a
    # raw OverflowError/ValueError/TypeError.
    prop = _proposal({"NovaBotV2": bad, "NovaBotV2Options": 10, "Cash": 0})
    with pytest.raises(AllocationV2DesignError):
        prop.validate()


def test_validate_fails_closed_on_non_mapping_allocation():
    prop = _proposal("not-a-mapping")
    with pytest.raises(AllocationV2DesignError):
        prop.validate()


def test_validate_accepts_well_formed_baseline_proposal():
    # Non-steered proposal equal to baseline and totalling 100 stays valid.
    prop = _proposal(dict(BASELINE))
    prop.validate()  # must not raise
