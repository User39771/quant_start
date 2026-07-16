# Quant Research v1.5 Coordinated Execution Summary

## Status

- Overall: completed with conditional branches blocked by frozen research gates.
- Data refresh: passed.
- Revised baseline and attribution: generated, but baseline terminates on an end-price gap at 2021-03-31.
- LOWVOL20 revised history: `research_not_ready`.
- Long-only prototype: not implemented because its prerequisite gate failed.
- Prospective evidence: `waiting_for_complete_period`.
- Commercial-space event study: `blocked_waiting_for_event_window`.
- `formal_performance_conclusion_allowed=false`.
- `execution_sim_ready=false`.

## Coordination

- Protocol and freeze: Sol High.
- Repository/data-lineage audit: Terra Medium.
- Refresh inventory/design: Terra Medium.
- Refresh and gated implementation: main coordinator.
- Independent final review: Sol High.

## Data Refresh

- Frozen universe: 56 unique stocks.
- Fresh stock fetch: 56/56 from `ak.stock_zh_a_daily`; no v1.2 seed used.
- Fresh benchmark fetch: 3/3 from `ak.stock_zh_index_daily_tx`.
- Adjusted panel: 85,207 rows, 2020-01-02 to 2026-07-10.
- Duplicate stock/date keys: 0.
- Refresh failures: 0.
- Critical refresh QA: passed.
- Old rows: 70,145; new rows: 85,207; newly added keys: 15,078; old-only keys: 16.
- Overlap rows changed by more than 1e-8: 3,768. This is disclosed as source/version revision, not silently treated as extension-only data.

## Revised History

- v1.5 baseline starts earlier than v1.2 because fresh full history expands availability.
- It terminates when 000063 lacks the 2021-03-31 endpoint after being eligible at the period start.
- Valid periods: 14; terminal full period end: 2021-03-03.
- LOWVOL20 receives only a short continuous main interval and returns `research_not_ready` with zero critical QA failures.
- The v1.4 frozen verdict remains unchanged and reproducible; v1.5 does not replace it.

## Conditional Branches

- Prototype files were not generated. The specification is frozen, but implementation requires a successful revised-history LOWVOL20 gate.
- Prospective table is header-only with zero periods; it is append-preserving on reruns.
- Event readiness covers the 12 frozen commercial-space stocks. The +5 trading-day window after 2026-07-10 is unavailable, so returns and CAR were not calculated.

## Verification

- Regression command:
  `python -m unittest tests.test_refresh_research_data_v1_5 tests.test_revised_history_pipeline_v1_5 tests.test_adjusted_price_panel_QA_v1_2 tests.test_adjusted_stock_pool_baseline_v1_2 tests.test_baseline_attribution_v1_2 tests.test_mom60_hypothesis_v1_3 tests.test_lowvol20_hypothesis_v1_4 -v`
- Exit code: 0.
- Tests: 64 passed, 0 failures, 0 errors.
- Frozen manifest paths: 162.
- Frozen hash differences: 0.
- v1.5 CSV files parsed: 29.
- Refresh manifest rows: 59.

## Changed Files

- `scripts/refresh_research_data_v1_5.py`
- `scripts/run_revised_history_pipeline_v1_5.py`
- `scripts/build_v1_5_gate_reports.py`
- `tests/test_refresh_research_data_v1_5.py`
- `tests/test_revised_history_pipeline_v1_5.py`
- Versioned v1.5 cache, processed data, QA, revised-history, comparison, prospective, event-readiness and review reports.

## Remaining Decisions

- No user approval can override the frozen `research_not_ready` gate without defining a new version and protocol.
- Continue collecting append-only prospective evidence after complete post-freeze periods exist.
- Recheck event readiness only after the full +5 market-day window exists.
- Do not describe the current prototype as implemented or validated.
