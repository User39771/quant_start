# LOWVOL20 Prospective Protocol v1.5

## Registration

- status: `frozen`
- freeze_date: `2026-07-11`
- generated_at: `2026-07-11T23:05:10+08:00`
- frozen universe: `data/processed/research_universe_lowvol_freeze_20260711.csv`
- universe count: `56` unique six-digit A-share codes
- membership rule: membership is fixed from the existing research universe and must not change because of prices, news, filings, or outcomes observed after the freeze date
- purpose: prospectively evaluate a research-only LOWVOL20 long-only prototype; this is not an investment recommendation or a formal performance conclusion

## Frozen research question

Can the lowest-volatility quintile reduce portfolio volatility and drawdown while retaining as much of the contemporaneous full-universe return as possible?

The primary comparison is the equal-weight return of the contemporaneously reliable and evaluable stocks in the frozen universe. Q5-Q1 is a factor diagnostic only and must not be represented as an executable A-share long-short portfolio.

## Frozen factor and selection rules

1. `primary_factor=LOWVOL20` and `LOWVOL20=-VOL20`.
2. VOL20 uses exactly 21 qfq closes to form 20 simple daily returns.
3. The signal date is the authoritative market trading day immediately before the rebalance date (`T-1`).
4. Prices are never forward-filled or backfilled, and raw close never substitutes for qfq close.
5. A signal is reliable only when `unique_close_count >= 3`, `nonzero_return_count >= 5`, and `longest_zero_return_run <= 5`.
6. Quantiles are assigned from the reliable signal sample before future-label availability is inspected.
7. Q5 is the lowest-volatility 20% of that sample. Ties and quantile assignment retain the frozen v1.4 implementation contract.
8. The long-only target holds Q5 at equal weights. Inverse-volatility weighting is prohibited.
9. Rebalancing follows the existing approximately 20-trading-day period boundaries.
10. Returns use the close-to-close research assumption; this is not a fill or execution simulation.
11. Transaction-cost scenarios are exactly `0`, `0.001`, and `0.002` per unit of turnover.
12. No momentum, reversal, liquidity, stop-loss, timing, or multifactor overlay is permitted.
13. No search over Top N, lookback, group proportion, or reliability threshold is permitted.

## Comparisons and diagnostics

- Primary: frozen-universe equal weight using the same period endpoints and the contemporaneously reliable and evaluable names.
- Secondary: Q5 versus Q1, CSI 300 (`000300`), CSI 1000 (`000852`), and ChiNext Index (`399006`).
- Q5-Q1 remains diagnostic and non-executable.
- Benchmark identity must be validated; a same-code stock must never substitute for an index.

## Sample-regime classification

Each period receives one immutable classification:

- `revised_history`: the period end is no later than the old panel's last date; this is historical reconstruction, not out-of-sample evidence.
- `pipeline_unseen_retrospective_extension`: the period contains data after the old panel cutoff, but its rebalance date is on or before `2026-07-11`; this is not prospective confirmation.
- `prospective_holdout`: the rebalance date is strictly after `2026-07-11`, the complete period has ended, and the frozen rules were used.

The prospective observation window begins on the first authoritative `000300` trading date strictly after the freeze date. A period is prospective only when its rebalance date is strictly after the freeze date and all observations required for the complete approximately 20-trading-day period are available. A period cannot later be relabelled across regimes.

## Append-only contract

Future prospective results are append-only.

1. Existing result rows, period identifiers, regime labels, hashes, and narrative log entries must never be updated, reordered, truncated, or deleted.
2. A new run may append only previously unrecorded complete periods, keyed by the frozen strategy version and rebalance/period-end dates.
3. Duplicate period keys are a critical QA failure and must not be silently skipped or overwritten.
4. Corrections are new records that identify the superseded record and state the reason; the original record remains intact.
5. Each append records generation time, source paths, source hashes, frozen-universe hash, code version when available, and QA status.
6. If no complete prospective period exists, retain the schema with zero rows and record `status=waiting_for_complete_period` and `prospective_period_count=0`.
7. The waiting state is not a failure. It must not produce Sharpe, significance, support, or investment conclusions.

## Gates and conclusion boundaries

Prospective evaluation stops when the authoritative `000300` calendar is unavailable, frozen membership or hashes differ, signal lookahead is found, duplicate stock/date keys cannot be resolved, or qfq semantics conflict. Ordinary single-symbol gaps are recorded rather than hidden.

All outputs must state `formal_performance_conclusion_allowed=false`, `execution_sim_ready=false`, and `no_investment_conclusion=true`. Historical or future observations may be reported descriptively without changing the universe, factor, Q5 rule, thresholds, or this protocol.

