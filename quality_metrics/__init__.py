"""Broker-free advisory quality-metrics package.

Pure, deterministic, stdlib-only advisory/reporting scoring. This package imports
**no** allocation/broker/live module (no broker, no scheduler, no
``core``/``workflow``/``utils``/``config``, no network), reads no real allocation
history, and writes no runtime/generated file. A standing import-isolation guard
(``tests/test_quality_metrics_no_live_import.py``) pins that.

It measures the *quality of advice* (ALLOC-003D) and grants no capital authority;
it sizes nothing, moves no money, and changes no allocation. Reading real
``data/system/allocation_history.json`` or any downstream export is a separate
HUMAN_GATED step.
"""
