# Quant Research v1.5 Independent Review

Reviewer: Sol High, read-only.

## Findings

- The refreshed panel is structurally valid, but the frozen baseline terminates early at the period ending 2021-03-31 because 000063 has a start price and no end price. Attribution therefore describes only the truncated baseline.
- LOWVOL20 revised history returns `research_not_ready`; strategy prototype implementation is correctly blocked and no prototype performance claim is allowed.
- Prospective outputs currently contain zero periods. The writer was hardened to preserve existing append-only files rather than reset them on rerun.
- Refresh QA was hardened to require all 56 stocks, all three named indices, positive prices, index identity, and duplicate-free keys.
- Sample-regime metadata is now applied to every v1.5 CSV carrying period endpoints. Copied Markdown titles are normalized to v1.5.

## Independent QA

- Frozen manifest: 162 files, 0 missing or hash differences.
- Adjusted panel: 85,207 rows, 56 stocks, 2020-01-02 through 2026-07-10, duplicate stock/date keys = 0.
- Benchmarks: 000300, 000852, 399006, latest date 2026-07-10.
- Event readiness: `blocked_waiting_for_event_window`; the +5 window has not occurred.
- Prospective status: `waiting_for_complete_period`, zero complete periods.

## Recommendation

The data refresh is accepted as a versioned research input. Revised-history LOWVOL20 and the long-only prototype are not approved because the frozen readiness gate fails on the truncated continuous sample. Retain `formal_performance_conclusion_allowed=false` and `execution_sim_ready=false`.
