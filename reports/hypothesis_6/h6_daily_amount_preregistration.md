# H6 — Daily Amount Own-History Abnormal Activity Diagnostic v1

## Fixed research identity and sequence

Saved before H6 outcome analysis on 2026-08-26. This document implements the user-approved H6 contract; it is not an additional approval gate. After this file and signal-time QA are saved, this task may evaluate historical outcomes. No result-dependent changes are allowed.

```text
sample_role=historical_seen
research_type=mechanism_diagnostic
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
causal_claim_allowed=false
strategy_claim_allowed=false
execution_claim_allowed=false
D04_replication_claim_allowed=false
human_interpretation_required=true
```

Question: does past RETURN60 state together with own-history abnormal daily trading amount correspond to different subsequent 5/10/20-market-day price paths? 20D is Primary; 5D/10D describe the path. This is D04-inspired, not a share-volume replication and not H5C.

## Inputs, universe and periods

- Read existing `data/cache/price/*.csv` amount, using `reports/hypothesis_5a_broader_a/source_resolution_report.csv` for canonical paths; no network or source replacement.
- Reuse H5 signal-time `RETURN60` and `RETURN_STATE` from the corresponding columns of `reports/hypothesis_5b/h5b_vt20_signal_panel.csv`. Read no VT fields and do not filter on VT validity. This file contains all H5 signal members.
- CSI300 dates: `data/processed/hybrid_benchmark_panel_v1_5.csv`, benchmark 000300.
- Outcome and formation-return prices: existing canonical `data/cache/h5a_broader_a_qfq_v1/*.csv`, as resolved by the source-resolution report. RAW close is not a substitute.
- Primary: period_index 3–56 inclusive, 54 periods. Periods 1/2 retain `early_history_diagnostic_only`, reason `insufficient_pre_signal_50d_activity_history`; period 0 remains outside Primary. This choice is fixed from readiness, not outcomes.
- Current-universe historical backfill is not point-in-time and has survivorship/composition and adjustment-vintage limitations. Existing reports and data remain unchanged.

## Primary signal: daily amount, date-neutral midrank

At formation date t use exactly the CSI300 dates t−49 through t, including t. No future date, earlier substitute, fill or interpolation. All 50 records must exist and amount must be finite and >=0. Existing zero values are retained, counted and flagged; negative/nonfinite/missing invalidates the stock-period. A constant window is permitted: its midrank is 25.5, hence NORMAL.

For A_t, `midrank = n_less + (n_equal + 1)/2`, where counts use all 50 observations including t. `own_history_percentile=(midrank-0.5)/50`. Dates never break ties. LOW_SHOCK if midrank<=5; HIGH_SHOCK if midrank>=46; otherwise NORMAL. No cross-sectional shock ranks, z-scores, percentage changes, means ratios or alternative thresholds.

RETURN60, orientation, ordinal terciles and membership are inherited without reassignment. Grid: LOW/MID/HIGH_RETURN × LOW_SHOCK/NORMAL/HIGH_SHOCK. Before any outcome analysis, save signal states and signal-only QA (per-period eligible/valid/coverage and three shock counts; all nine cells' median/min/p10). If any Primary period coverage<80%, stop before future analysis. Small cells do not change shock rules.

## Outcome timing and cell statistics

Formation amount is available after t close. Entry is **not** t close: return_start_date is the next CSI300 market date, using that day's QFQ close. Endpoint_h is h market dates after return_start_date, h in {5,10,20}; return=P(endpoint_h)/P(return_start_date)−1. These are nested cumulative raw returns, not continuation-aligned returns. No other horizons or strategy returns.

Signal membership is fixed before outcomes. Missing endpoints leave outcome invalid without changing signal state/member count or substituting another stock. Every period × RETURN_STATE × SHOCK_STATE × horizon reports membership, valid outcomes, coverage, arithmetic mean, descriptive median and IQR. A cell is valid only if membership>=25 and outcome coverage>=80%. Both extreme cells must be valid to form G_(R,h)=mean(HIGH_SHOCK)−mean(LOW_SHOCK). All three return states are reported, including MID. Interaction is `Loser_vs_Winner_Diff_h=G_LOW,h−G_HIGH,h`, paired within period; not causal.

## Period statistics and uncertainty

Equal weight each valid period contrast, never pool stocks for inference. Report mean, median, positive share, fraction with the full-sample mean's sign, valid-period count, missing-period list, LOO sign consistency and 90% circular moving-block bootstrap interval. Fixed block_length=3, repetitions=10000, seed=20260721. Apply the same method to all horizons and interaction contrasts. Reuse the project's convention: ordered valid period contrasts form the bootstrap series; disclose omitted periods and that gaps may reduce calendar-adjacency fidelity. No replacement of invalid periods, no stock-level p-values, no automatic supported/rejected or Alpha category. Intervals are descriptive uncertainty/stability evidence, not multiplicity-controlled, OOS or Alpha significance.

## Two fixed robustness checks

**A: normal formation return.** For the same dates t−49...t, construct 50 QFQ daily returns (therefore require 51 exact closes, t−50...t). All prices must be finite and positive; no fill. Rank r_t in those 50 returns using the same date-neutral midrank/percentile. Include only percentile in [0.30,0.70], inclusive (Middle40); no other threshold. Recompute the identical raw G contrasts at 5/10/20D using this signal-time subsample, same cell>=25/80% rules and period statistics. Preserve Primary shock and RETURN_STATE. Missing formation history invalidates only robustness A, never Primary.

**B: market-normalized amount.** For each required market date sum finite nonnegative canonical amount across the current 5,195-stock broader-A universe, not merely signal members; zero observations count as participants. The reference median participant count uses the union of exact 50-date windows for the 54 Primary periods. A daily denominator requires participants>=80% of that median and a finite strictly positive total. A window with any failing denominator is invalid for B; no lower threshold. Rank Amount_i,d/MarketTotalAmount_d over exactly 50 dates by the same midrank and shock rule. Preserve inherited RETURN_STATE. Report identical contrasts and coverage. This is only an approximate D04 market normalization and cannot change Primary classification (there is no automatic classification).

## Trend and interpretation

For each Primary valid amount observation, save Spearman(amount over 50 dates,time index 1...50), with average ranks. Constant amount implies undefined trend correlation. Report HIGH/LOW shares with |rho|>=0.50 and undefined-trend counts. Do not detrend, residualize, rerank or exclude trending observations. Slow local trend remains an alternative explanation, not an identified cause.

No authoritative historical limit/ST/suspension/next-day-tradability data exist. Do not infer such status from OHLC or drop possible limit stocks. Outcome returns are not guaranteed executable. Do not calculate strategy Sharpe, costs, turnover, equity curves or execution feasibility. No share-volume download, VT replacement, MCTS, Phase B, prospective/final test, parameter/horizon search or automatic follow-up.

The report provides facts and material for human interpretation: broadly visible association, state-concentrated association, weak/unstable association, or formation-return/marketwide/trend alternative explanations. Runner must not assign these labels automatically. H5 cross-sectional level and H6 own-history shock are different questions, not competing factors ranked by effect size.

## Outputs, checks and stop

Only the requested runner/test and six H6 files: this contract; `h6_signal_states.csv`; `h6_period_state_returns.csv`; `h6_primary_contrasts.csv`; `h6_robustness_summary.csv`; `h6_diagnostic_report.md`. CSVs carry research identity. Period returns retain all three variants; contrast CSVs include period rows and summary rows for auditability. Early periods have signal diagnostics only. Report is first written as signal-only QA before outcome loading and completed after analysis.

Tests cover exact windows, formation inclusion, no future information, missing/no-fill, zero flags, ties/boundaries, inherited states, Primary period set, next-day timing and endpoint offsets, frozen membership, 25/80 rules, equal-period weighting, fixed bootstrap reproducibility, Middle40, market participant threshold, allowed signal inputs and absence of MCTS/Phase B execution. Run focused unittest and Ruff only; do not invoke generic data-fetching/research commands. Stop for technical contract/QA failures; otherwise stop after the report, with human_interpretation_required=true.
