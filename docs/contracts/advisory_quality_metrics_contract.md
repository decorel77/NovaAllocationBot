# NovaAllocationBot — Advisory Quality-Metrics Contract

Status: contract/design document (docs-only); **advisory / reporting only**
Scope: define how advisory *quality* is measured across the Nova advisory layer (NovaBotV2 / Options / Allocation) — were signals good, were recommendations stable and well-calibrated — without changing any allocation, weight, or live behavior.
Implementation status: this document changes no percentage value, moves no money, alters no allocation logic, reads no real allocation history, and touches no runtime data. It is a contract; it carries no capital authority. The pure metrics module is `ALLOC-003D` (gated on `ALLOC-003A/B/C`); live use is HUMAN_GATED.

Card: `ALLOC-003A` (unblocks the deferred `ALLOC-003`). Companion to `cash_reserve_dashboard_contract.md` and `allocation_snapshot_contract.md`; cross-references the NovaBotV2 `PERFORMANCE_LEDGER_SCHEMA.md` (`PERF-LEDGER-001A`), which supplies the *realized* outcomes these forward metrics are scored against.

## Principle

This contract measures the **quality of advice**, never issues advice. Nothing here sizes a position, sets a weight, moves cash, or enables an automatic action — those stay HUMAN_GATED (ALLOC-006/007). Every metric is **deterministic** given its inputs and **fails closed to `UNKNOWN`** when an input is missing or stale; an absent forward return is never reported as `0`.

## Sources (one taxonomy across the advisory layer)

| Source tag | Produces | Notes |
|---|---|---|
| `NOVABOTV2` | per-candidate buy/sell signals + RiskGovernor verdicts | accept/reject reason codes already exist (`RG_*`) |
| `OPTIONS` | options paper/advisory signals | PAPER/ADVISORY only |
| `ALLOCATION` | target-weight / cash-reserve recommendations | recommendation-only |

Metrics are computed **per source** and may be combined; a missing source is omitted, never zero-filled.

## Metric families

Each metric lists its definition, inputs, and missing/stale behavior. All are read-only and deterministic.

### A. Decision metrics (acceptance)

| Metric | Definition | Missing/stale |
|---|---|---|
| `signals_accepted` / `signals_rejected` / `signals_skipped` | counts of each `decision` | absent decision ⇒ excluded, flagged |
| `acceptance_rate` | `accepted / total` over the window | `total = 0` ⇒ `UNKNOWN` (never `0`) |
| `reason_code_histogram` | count per `reason_code` (e.g. `RG_REJECT_QUOTE_DEVIATION`) | unknown code ⇒ bucketed as `UNKNOWN_REASON` |

### B. Outcome metrics (was the signal good?)

| Metric | Definition | Missing/stale |
|---|---|---|
| `forward_return[window]` | realized return at `1d / 5d / 20d` after the signal, per source-defined window | missing forward price ⇒ `UNKNOWN`, metric withheld |
| `drawdown_after_signal` | max adverse excursion within the window after the signal (negative) | missing path ⇒ `UNKNOWN` |
| `missed_opportunity` | bool: a **non-accepted** signal whose forward return would have exceeded a documented threshold | only set for `REJECTED`/`SKIPPED`; missing forward ⇒ `UNKNOWN` |
| `risk_adjusted_score` | forward return per unit of adverse risk (e.g. `forward_return / max(|drawdown_after_signal|, ε)`), or a Sharpe-like ratio over the signal series | any missing/stale input ⇒ `null` + `UNKNOWN` (never fabricated) |

### C. Recommendation-stream metrics (Allocation)

| Metric | Definition | Missing/stale |
|---|---|---|
| `stability` | inverse of recommendation churn over the window (low churn ⇒ stable) | < 2 snapshots ⇒ `UNKNOWN` |
| `turnover` | `Σ |wₜ(i) − wₜ₋₁(i)|` over the union of names between consecutive recommendation snapshots | < 2 snapshots ⇒ `UNKNOWN` |
| `calibration` | predicted confidence bucket vs realized hit-rate (reliability) | no paired predicted/realized ⇒ `UNKNOWN` |
| `recommendation_quality` | realized contribution of recommended weights vs an ex-post benchmark/neutral split (descriptive, not a grade) | missing realized outcome ⇒ `UNKNOWN` |

### D. Freshness metric (staleness)

| Metric | Definition | Missing/stale |
|---|---|---|
| `staleness.fresh_share` | `fresh_signals / total_signals` (a signal is fresh when its input freshness is `FRESH`) | `total = 0` ⇒ `UNKNOWN` |
| `staleness.status` | `OK` if `fresh_share` ≥ a documented floor, else `STALE` | absent freshness ⇒ `UNKNOWN` |

## Public-safe fields (allowlist / deny-by-default)

The dashboard projection may show only: source tag, the metric names above, counts, rates/scores as numbers or `UNKNOWN`, `reason_code` strings, window labels, freshness status, and `recommendation_only = true`. Anything not on this allowlist is dropped.

## Forbidden fields (deny-by-default)

Never include: account numbers, real balances/positions, order/exec/perm/client ids, broker ids, capital totals, secrets, API keys, file paths, or any `*_apply`/`*_enforce`/execution flag. The metrics describe quality; they grant no authority.

## States (fail closed)

| Status | When | Rule |
|---|---|---|
| `OK` | metric computed from present, fresh inputs | only when all inputs hold |
| `STALE` | inputs past their freshness floor | old ⇒ `STALE`, never `OK` |
| `INSUFFICIENT` | not enough samples/snapshots to compute (e.g. < 2 snapshots, `total = 0`) | show `INSUFFICIENT`/`UNKNOWN`, withhold a number |
| `UNKNOWN` | missing/malformed/unreadable input | **absence ⇒ `UNKNOWN`, never a fabricated metric** |

## Hard boundaries

1. **No allocation behavior change.** This contract sets/modifies no weight, percentage, cash reserve, or risk setting; it changes no allocation logic.
2. **No money movement / no capital steering.** Reporting only; applying anything is ALLOC-006/007 (HUMAN_GATED).
3. **Recommendation-only label is constant.** `recommendation_only = true` always.
4. **Deterministic + fail-closed.** Identical inputs ⇒ identical metrics; missing/stale ⇒ `UNKNOWN`, never `0` or a guess.
5. **No real wiring here.** Real source wiring (reading `allocation_history.json`, ledger outcomes, dashboard feed) is HUMAN_GATED; this is the contract only. The pure module is `ALLOC-003D` (gated on A/B/C).

## Validation (docs-only / synthetic)

- `tests/fixtures/quality_metrics/advisory_quality_examples.json` — synthetic-only signal outcomes across all three sources plus two allocation recommendation snapshots, exercising: an accepted profitable signal, a rejected `missed_opportunity`, a stale signal whose outcome metrics are withheld (`UNKNOWN`), a skipped signal, and a turnover/stability/staleness aggregate with `calibration = UNKNOWN`. No account/balance/order/broker/secret/path data.
- `tests/test_advisory_quality_metrics_contract.py` — a **static schema-conformance** test (pure stdlib `json`/`unittest`/`pathlib`, imports no allocation/broker module): required fields + enums per record; the deterministic `acceptance_rate`, `turnover`, and `staleness.fresh_share` recomputed as reference oracles and matched against the declared aggregate; stale inputs withhold outcome metrics (`UNKNOWN`/null); `missed_opportunity` only on non-accepted signals; `recommendation_only = true`; a leak scan finds no forbidden token. Broker-free under `python -S -m unittest tests.test_advisory_quality_metrics_contract`.

## Safety confirmation

This contract was written from the existing allocation contract docs and the NovaBotV2 performance-ledger schema only. It changed no percentage, weight, or allocation logic; moved no money; read or modified no runtime/generated data (`data/system/allocation_history.json` was left untouched and unstaged); and touched no `.env`/secret, broker, or order path. It added only a synthetic fixture and a pure static schema test. It is advisory/reporting-only; this document grants no authority and lifts no gate.
