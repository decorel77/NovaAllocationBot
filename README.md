# NovaAllocationBot

NovaAllocationBot is the capital and budget allocation bot for the NOVA ecosystem.
It is designed to decide how available capital should be allocated between:

- NovaBotV2 equity trading bot
- NovaBotV2Options options bot
- future NovaCryptoBot
- future tactical and market regime bots
- cash reserve

## Current Phase

Phase 2.5 recommendation-only allocation guidance is complete.

NovaAllocationBot does not trade. It does not place orders, call brokers, move
money, write to other bot repositories, export allocation decisions downstream,
or enable autonomous trading. It only produces a dry-run allocation decision and
advisory recommendation in its own local result snapshot.

NovaAllocationBot reads NovaBotV2 and NovaBotV2Options result snapshots in
read-only mode, evaluates simple deterministic health, records advisory warnings,
and generates a recommendation-only allocation suggestion. The actual/current
allocation remains unchanged.

Future bots may read an approved NovaAllocationBot output, and future NovaBridge
work may orchestrate allocation cycles across the ecosystem. That orchestration is
not implemented in this phase.

## Current Allocation

Phase 2.5 keeps current allocation fixed:

- NovaBotV2: 90%
- NovaBotV2Options: 10%
- NovaCryptoBot: 0%
- CashReserve: 0%

Recommendation examples may suggest 95/5, 80/20, or 100/0 between the active
bots based on health, but this is advisory only. No capital movement exists.

## Structure

- `config/` - static allocation defaults and configurable snapshot paths
- `core/` - typed allocation contracts, snapshot reader, health evaluator, and recommendation engine
- `workflow/` - dry-run allocation cycle
- `tools/` - CLI entrypoint
- `tests/` - safety and behavior tests
- `data/system/` - local agent state, task queue, and result snapshot
- `docs/handover/` - current state and savegame authority

## Dry-Run Commands

From this folder:

```powershell
python -m unittest discover tests
python -m tools.allocation_autocycle --once
```

The CLI is dry-run by default and writes only
`data/system/result_snapshot.json` inside this project.
