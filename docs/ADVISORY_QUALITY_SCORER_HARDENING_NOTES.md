# Advisory Quality Scorer — Hardening Notes (ALLOC-003D)

Repo: `Apps/NovaAllocationBot`
Module: `quality_metrics/advisory_quality_scorer.py` (pure, stdlib-only, advisory/recommendation only)
Status: **tests + docs only.** This note documents what the synthetic hardening loop covered and the malformed-input gaps that remain for a separate, *reviewed* hardening card. No scorer source was changed in this loop; no runtime `allocation_history.json` was read.

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

## 3. KNOWN GAPS — malformed *types* currently raise instead of failing closed

These are pinned with `assertRaises` in `ScorerKnownGapTest` so a future fix is detected. They are **not** fixed here (this loop is tests/docs only; the fix is a code change that warrants its own reviewed card):

| Malformed input | Current behavior | Desired (future card) |
|---|---|---|
| Non-dict top-level `outcome` (str/int) | `ValueError`/`TypeError` at `dict(outcome or {})` | fail closed to UNKNOWN |
| `freshness` is a string (not a dict) | `AttributeError` at `(o.get("freshness") or {}).get(...)` | treat as MISSING ⇒ fail closed |
| `forward_returns` is a string (not a dict) | `AttributeError` at `fr.get("20d")` | treat as missing forward return |
| `turnover_warning` snapshot or `weights` is not a dict | `AttributeError` | treat as `{}` / skip ⇒ no crash |

### Suggested fix shape (for the future reviewed card)

- coerce a non-dict top-level input to `{}` (mirror the existing `dict(outcome or {})` intent but guard non-mapping types);
- read nested fields defensively: `fresh = o.get("freshness"); status = fresh.get("status") if isinstance(fresh, dict) else None` (same for `forward_returns`);
- in `turnover_warning`, skip non-dict snapshots and coerce non-dict `weights` to `{}`.

Each would only make the scorer **more** fail-closed; none changes a well-formed result. The fix belongs in `quality_metrics/advisory_quality_scorer.py` and must keep the module pure (no new imports) and re-run the no-live-import guard.

## 4. Out of scope (unchanged here)

No runtime `allocation_history.json` read/write, no downstream export/wiring, no allocation/broker/live import, no package install, no scorer source change. Reading real allocation history or wiring any export remains HUMAN_GATED.
