# Advisory Quality Scorer — Hardening Notes (ALLOC-003D)

Repo: `Apps/NovaAllocationBot`
Module: `quality_metrics/advisory_quality_scorer.py` (pure, stdlib-only, advisory/recommendation only)
Status: **malformed-type hardening applied (2026-06-23).** The malformed-*type* gaps previously pinned as `assertRaises` markers are now **fixed in the scorer source** — they fail closed / degrade safely instead of raising. The change is pure stdlib only (no new imports), keeps every well-formed result unchanged, and re-runs green against the no-live-import guard. No runtime `allocation_history.json` was read.

## 1. What the scorer guarantees today

- **Advisory only.** `score_outcome` / `turnover_warning` size nothing, move no money, change no allocation. The no-live-import guard (`tests/test_quality_metrics_no_live_import.py`) pins that the package imports no broker/allocation module and references no runtime path.
- **Fail-closed on stale/missing freshness.** `freshness.status` of `STALE`/`MISSING` ⇒ `fail_closed=True`, null `quality_score`/`risk_adjusted_score`, `stale_data_penalty=1.0`, and the matching reason code.
- **Degrades to UNKNOWN, never fabricates.** Missing optional fields (forward return, confidence, regime) degrade the dependent metric to `None`/`UNKNOWN` with a `MISSING_*` reason code — never a made-up number.
- **Deterministic + JSON-serializable.** Identical inputs ⇒ identical `OutcomeScore`; `dataclasses.asdict(score)` is JSON-serializable.

## 2. Hardening covered by `tests/test_advisory_quality_scorer_hardening.py`

| Area | Pinned behavior |
|---|---|
| Empty / `None` input | degrades to UNKNOWN, null score, `MISSING_FORWARD_RETURN`/`MISSING_CONFIDENCE`/`MISSING_REGIME`; no crash |
| Missing forward returns | null `quality_score` + `MISSING_FORWARD_RETURN` |
| Unexpected confidence value | `NEUTRAL` bucket/alignment; no false `MISSING_CONFIDENCE` |
| Regime from equal fields | `regime_mismatch_flag=False`; no `MISSING_REGIME` |
| Zero forward return | scores exactly `0.0` (accepted and rejected) |
| Unknown decision | null score + `UNKNOWN_DECISION` |
| Rounding | scores round to 4 dp |
| JSON serializability | `json.dumps(asdict(score))` round-trips |
| Determinism | identical inputs ⇒ identical output |
| Turnover edges | `< 2` snapshots ⇒ `None`; strict `>` threshold; missing `weights` key ⇒ `{}` (no crash); identical weights ⇒ no turnover |

## 3. Malformed *types* now fail closed (FIXED 2026-06-23)

These were previously pinned with `assertRaises` as known gaps. The scorer now degrades safely instead of raising. `tests/test_advisory_quality_scorer_hardening.py::ScorerMalformedTypeTest` pins the new behavior.

| Malformed input | Old behavior | New (fail-closed) behavior |
|---|---|---|
| Non-dict top-level `outcome` (str/int/list/float) | `ValueError`/`TypeError` at `dict(outcome or {})` | coerced to `{}` ⇒ UNKNOWN/null scores + `MALFORMED_INPUT` reason code (no crash) |
| Non-`None` `outcome` vs `None` | — | `None` is the legitimate "absent" signal ⇒ behaves like `{}`, **not** flagged `MALFORMED_INPUT` |
| `freshness` is a string (not a dict) | `AttributeError` at `(o.get("freshness") or {}).get(...)` | untrusted ⇒ `fail_closed=True`, `stale_data_penalty=1.0`, null scores + `MALFORMED_INPUT` |
| `forward_returns` is a string (not a dict) | `AttributeError` at `fr.get("20d")` | treated as missing forward return ⇒ null `quality_score` + `MISSING_FORWARD_RETURN` + `MALFORMED_INPUT` |
| `turnover_warning` snapshot is not a dict | `AttributeError` | coerced to `{}` ⇒ no crash |
| `turnover_warning` `weights` is not a dict | `AttributeError` | coerced to `{}` ⇒ no crash |
| `turnover_warning` weight value is non-numeric | `TypeError` at subtraction | coerced to `0.0` ⇒ no crash |

### How it was fixed (pure stdlib, no new imports)

- top-level: `isinstance(outcome, dict)` guard — a non-`None`, non-mapping input becomes `{}` and appends `MALFORMED_INPUT`;
- nested fields read defensively: `freshness`/`forward_returns` are only `.get()`-ed when `isinstance(..., dict)`, else treated as untrusted/missing and flagged;
- a present-but-non-dict `freshness` is treated as *unverifiable freshness* and **fails closed** (safer than assuming fresh);
- `turnover_warning` coerces non-dict snapshots/`weights` via `_as_dict(...)` and non-numeric weights via `_num(...)`.

Every change only makes the scorer **more** fail-closed; no well-formed result changed (verified by the unchanged fixture/contract/scorer suites). The module stays pure (only `dataclasses`/`typing`) and the no-live-import guard re-runs green.

## 4. Out of scope (unchanged here)

No runtime `allocation_history.json` read/write, no downstream export/wiring, no allocation/broker/live import, no package install. Reading real allocation history or wiring any export remains HUMAN_GATED.
