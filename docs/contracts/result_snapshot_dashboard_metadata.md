# Result Snapshot — Dashboard Trust Metadata

NovaAllocationBot's `data/system/result_snapshot.json` carries an explicit
public-safe trust/freshness envelope so a read-only consumer (NovaDashboard's
collector / approved-source contract) can gate on it. The envelope is built by
`workflow/allocation_cycle.build_result_snapshot_envelope()`.

## Fields

| Field | Source | Semantics |
|---|---|---|
| `produced_at` | cycle `produced_at` (UTC ISO-8601) | when the snapshot was produced |
| `fresh_until` | `produced_at + ALLOCATION_SNAPSHOT_FRESH_HOURS` | conservative freshness horizon |
| `schema_version` | `"allocation_result.v2"` | stable schema id |
| `producer_id` | `"NovaAllocationBot"` | producing process |
| `data_is_real` | `not realness_reasons` | **fail-closed**: False whenever any input (regime / NovaBotV2 / Options) is missing, invalid, stale, fake, or unknown; `data_is_real_reasons` lists why |
| `public_safe` | unconditional `True` (this change) | static marker: the snapshot carries only public-safe fields (allocation %, bot-health scores/status, warnings, regime context) — no account/order ids, secrets, or machine paths |

`public_safe` is **not** a realness claim. Realness stays fail-closed in
`data_is_real`; a snapshot built from a stale/fake/missing input is still
`public_safe: true` but `data_is_real: false`.

## Boundaries

Adding `public_safe` is a pure additive metadata change to the envelope builder.
It runs no live/scheduled/broker/order workflow, performs no network call, and
writes no runtime `result_snapshot.json` (envelope tests use
`run_allocation_cycle(write_snapshot=False, ...)` with synthetic temp inputs).
NovaAllocationBot stays dry-run.

## Remaining blockers before NovaDashboard can read this as an APPROVED REAL source

Per the dashboard readiness gate
(`Apps/NovaDashboard/docs/DASH_014E_REAL_SOURCE_READINESS_DECISION.md` +
`DASH_014F_REGIME_ALLOCATION_APPROVED_SOURCE.md`), the page stays
MISSING/UNVERIFIED until **Joeri** approves and:

1. A **fresh, real** snapshot exists — `data_is_real: true` requires all upstream
   inputs (regime + NovaBotV2 + Options) to be real and fresh. While
   `\NovaBot_Main` and the regime cycle are paused, those inputs are stale/fake,
   so the allocation snapshot stays `data_is_real: false` / UNVERIFIED.
2. The exact source path is human-approved as a read-only, generated artifact.
3. The current working-tree `result_snapshot.json` is regenerated under
   supervision so it carries these fields with real, fresh inputs.
4. No NovaDashboard wiring changes here: the dashboard's approved-source contract
   already requires `public_safe` + `data_is_real` + `produced_at` + `fresh_until`
   and fails closed without them.
