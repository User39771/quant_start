# H8 Final CA-Clean Sample / History Threshold Readiness

**H8_readiness=H8_READY_FOR_HUMAN_FREEZE**. This is data/contract readiness, not an H8 result. Primary threshold remains a human choice. No Eq.9 fit or preregistration was run.

## Price contract and start

Source status=BAOSTOCK_CA_SOURCE_ACCEPTED_WITH_LIMITATIONS; candidate count=2790. Cache status={"SUCCESS_WITH_EVENTS": 2611, "SUCCESS_NO_EVENTS": 179}. Price source=BAOSTOCK_RAW_OHLC; `PRICE_CONTRACT_READY_WITH_LIMITATION` for successful event-cache stocks only. Rule: a formation row is invalid if t or t+1 is an explicit CA event date. Conditioning r_t and future cc/out boundary contamination are both excluded; P2 intraday shares the matched exclusion. No adjusted OHLC, synthetic open, price substitution or ratio-based events.

CA source queried 2020-01-01..2026-05-12; successful stock-specific covered starts are recorded in h8_final_clean_stock_rows.csv. Natural boundaries: raw common calendar begins 2020-01-02; first exact22 formation is 2020-02-11; old QFQ overlap begins 2020-12-28 but no longer constrains this explicit source. **RECOMMENDED_H8_ANALYSIS_START=2020-02-11** (earliest final matched formation; individual starts differ). Formation cutoff=2026-05-11, next endpoint=2026-05-12; no extension to August.

## GARCH chronology — fixed before event probe

`final_sample_contract=PER_STOCK_LONGEST_CA_CLEAN_CONSECUTIVE_SEGMENT`. Choose each stock's longest sequence of adjacent valid raw close-to-close decimal returns after CA-day invalidation; ties choose earliest. Estimate one zero-mean GARCH(1,1), normal, rescale=False using arch8.0.0 on that sequence. Reset begins at its own first date using the package default in-sample backcast. Other segments are not concatenated, not separately fitted, and not used to rescue a failure. The fitted parameters/backcast are in-sample, not prospective estimates.

This choice prioritizes the simple single-stock single-estimation implementation. Multiple separately reinitialized segment models would retain more observations but introduce multiple parameter estimates or a new shared-parameter likelihood. Neither is silently introduced. Consequence: 2723982 otherwise clean current-return observations are outside the chosen longest segments. Thus minimum-history comparisons refer to **one contiguous GARCH segment**, not accumulated disconnected history. This tradeoff was fixed before any final row counts, and not based on H8 effects.

Specification status={"GARCH_SUCCESS": 2784, "GARCH_NUMERIC_FAILURE": 6}. Only successful finite-positive variance paths count. All failed models remain GARCH_NUMERIC_FAILURE without rescue. GARCH final contract resolved under this stated adaptation; numerical success is not statistical identification or paper equivalence, and very short converged segments do not pass the stock-level minimum-history candidates.

## Final matched rows

Stocks with any rows=2782; across these stocks median=266.0, p10=243.0, p90=1035.0. Across all 2790 candidates median=266.0, p10=242.0, p90=1035.0. Final P1/P2/matched totals all equal 1282962. Per-stock counts, source failures and GARCH failures are preserved in the companion CSV. Zero final rows mean unavailable under this implemented contract, not no economic effect.

Exact22 turnover validity, current/next active OHLC, positive finite values, weekday and sample membership use the existing H8 helpers. V is constructible without future information; zero-truncated V and zero returns remain eligible. GARCH inputs stop at the conditioning cutoff; no future-return relation or Eq.9 outcome analysis is performed.

Before longest-segment/GARCH restriction, CA-clean matched presence totals 3931451; final retained share is 32.6333%. Median source event records per candidate=6.0; among stocks meeting750 rows=1.0. These are sample-composition measures, not return attribution.

## Threshold comparison — final rows only

| min_rows | eligible_stocks | candidate_share | median_rows | SH_MAIN | SZ_MAIN | size_inclusion_spread |
|---|---|---|---|---|---|---|
| 750 | 434 | 0.155556 | 1177 | 190 | 244 | 0.147776 |
| 1000 | 287 | 0.102867 | 1406 | 121 | 166 | 0.113343 |
| 1250 | 182 | 0.065233 | 1514 | 77 | 105 | 0.0789096 |
| 1500 | 121 | 0.0433692 | 1514 | 50 | 71 | 0.0530846 |

Size quartiles are fixed within the 2790 pre-threshold candidates; two missing-size stocks stay UNKNOWN. CSV provides quartile inclusion rates, size means/medians, p10/p90 rows and Spearman(final_rows,log_size) within each retained subset. This is sample-selection evidence only. 1500 is tabulated only if some final stock history makes it feasible; otherwise 1500 eligibility is zero under this contract and is not introduced as another active candidate.

Smaller absolute inclusion-rate spreads at tighter thresholds must not be read as proof of improved balance: overall retention falls sharply, and the largest-size quartile remains less represented. This final selection pattern is materially different from the old pre-CA upper-bound comparison.

**recommended_primary_min_rows=HUMAN_JUDGMENT; recommended_long_history_sensitivity=UNRESOLVED; threshold_selection_requires_human_judgment=true.** Paper's 2400-day intent cannot be replicated; neither maximum retention nor nearest-to-2400 is an automatic choice. Event exclusion plus longest-segment selection may strongly favor stocks with fewer dividends/actions, so human review must weigh that structural selection alongside size and SH/SZ coverage. Do not inherit the old pre-CA upper bounds or H7's750 rule.

## Boundaries and human decision

P1_SIGN_READY=true (data only, threshold not frozen); P2_TIMING_READY=true (same matched sample); P3_INSTITUTION=NOT_FEASIBLE. PRICE_LIMIT_ROBUSTNESS=UNAVAILABLE_IN_V1; PRICE_LIMIT_BLOCKS_PRIMARY=false.

H7_rerun=false; H7_modified=false; H8_results_opened=false; gamma31_estimated=false; gamma32_estimated=false; Eq9_fit=false; H5/H6/MCTS/Phase_B_run=false; strategy_backtest_run=false.

Next: human choice of minimum history and review of longest-segment selection limitations, before any separate H8 preregistration or Eq.9 run. No automatic continuation. Data-quality skill separates external validations, source-only plausible records and unknown coverage; minimal implementation reuses H8 helpers and keeps one fixed GARCH fit per stock. STOP BEFORE PREREGISTRATION / EQ9 FIT.
