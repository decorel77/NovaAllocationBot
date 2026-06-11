# NovaAllocationBot Allocation v1 vs v2

## Status

Allocation v1 is the active production behavior. It publishes
`allocation_result.v2` from `workflow/allocation_cycle.py` and keeps all output
inside NovaAllocationBot. The single authoritative allocation remains the
REPAIR-007 result, with the existing safety flags set to dry-run and no broker,
order, money movement, live trading, downstream export, or cross-project writes.

Allocation v2 is design-only. The current `core/allocation_v2_design.py` module
does not run inside the allocation cycle, does not write snapshots, and does not
change `allocation_result.v2`. It exists to test a future consumer contract for
MarketRegimeBot `regime_result.v3` before that upstream schema is promoted.

## v1 behavior

Current v1 behavior:

- Reads NovaBotV2 and NovaBotV2Options snapshots in read-only mode.
- Reads the current MarketRegimeBot snapshot through the existing adapter.
- Produces `regime_allocation` as a diagnostic allocation block.
- Produces exactly one `authoritative_allocation`.
- Allows a regime to steer only when the regime is known, real, fresh, and meets
  the configured confidence threshold.
- Refuses missing, stale, fake, unverified, or low-confidence regime data and
  falls back to the health-based recommendation.
- Publishes `allocation_result.v2` only from NovaAllocationBot's own project
  directory.

## v2 design intent

Allocation v2 is intended to consume a future `regime_result.v3` envelope with
model metadata and hysteresis diagnostics:

- `schema_version`
- `producer_id`
- `model_version`
- published `market_regime`
- `raw_regime`
- confidence values
- freshness timestamps
- `data_is_real`

The design layer fails closed by default. Missing fields, stale timestamps,
fake data, unknown schemas, unknown producers, unknown regimes, and unknown
model versions all hold the caller's baseline allocation unchanged. Known
research-stage models are diagnostic only unless explicitly promoted to the
trusted model set.

When raw and published regimes disagree, v2 chooses the more conservative
regime by risky-allocation cap. Hysteresis may delay risk-on behavior, but it
must not delay risk-off behavior.

## Promotion Path

Before v2 can become active behavior:

1. MarketRegimeBot must promote `regime_result.v3` from design/research output
   to an active contract with real, fresh, non-fixture data.
2. NovaAllocationBot must add a read-only v3 adapter that validates the exact
   schema and producer identity.
3. QA must prove missing, stale, fake, unknown, low-confidence, and disagreeing
   regime inputs fail closed.
4. A migration test must prove `allocation_result.v2` remains backward
   compatible for existing consumers.
5. The trusted model list must be deliberately widened in code review; research
   model versions stay diagnostic until that happens.
6. Documentation and the allocation snapshot contract must be updated before any
   production cycle imports or calls the v2 proposal layer.

Until every step is complete, Allocation v2 remains design-only and v1 remains
the default behavior.
