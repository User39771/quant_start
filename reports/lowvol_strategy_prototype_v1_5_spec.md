# LOWVOL20 Long-Only Strategy Prototype v1.5 Specification

## Status and scope

- status: `specification_frozen`
- freeze_date: `2026-07-11`
- generated_at: `2026-07-11T23:05:10+08:00`
- implementation status: `not_started`
- strategy code created by this stage: `false`
- formal performance conclusion allowed: `false`
- execution simulation ready: `false`
- no investment conclusion: `true`

This document locks the research prototype only. It does not implement code, simulate executable fills, or establish an investable strategy.

## Primary objective

Lower portfolio volatility and drawdown while retaining as much of the contemporaneous frozen-universe equal-weight return as possible.

## Frozen portfolio definition

| Item | Frozen rule |
|---|---|
| Universe | Exactly 56 unique codes in `data/processed/research_universe_lowvol_freeze_20260711.csv` |
| Membership | Fixed on `2026-07-11`; no post-freeze price or news may add, remove, or relabel a member |
| Signal | `LOWVOL20=-VOL20` |
| VOL20 input | 21 exact qfq closes forming 20 simple returns |
| Signal timing | `T-1`, the authoritative market trading day before rebalance |
| Reliability | `unique_close_count >= 3`; `nonzero_return_count >= 5`; `longest_zero_return_run <= 5` |
| Selection | Q5, the lowest-volatility 20% of the reliable signal sample |
| Quantile timing | Fixed before future-label availability is evaluated |
| Weighting | Equal weight among selected Q5 names |
| Rebalance | Existing approximately 20-trading-day boundaries |
| Return assumption | Close-to-close research return |
| Missing prices | No forward-fill, backfill, or raw-close substitution for qfq |
| Costs | `0`, `0.001`, and `0.002` per unit of turnover |

A name requires a valid price at the rebalance start to enter the target. A missing period-end price must not trigger retrospective removal and reweighting. Any resulting evaluability treatment must be declared and applied without future-label lookahead.

## Turnover and costs

Turnover uses drifted pre-trade weights against new target weights, with absent names assigned zero weight. First-period turnover is `1`. Gross returns do not include costs; net returns deduct `transaction_cost * turnover`. No market-impact, spread, limit-up/down, or fill model is claimed.

## Required comparisons

The primary comparator is the contemporaneous equal-weight portfolio of reliable and evaluable stocks from the same frozen universe and on the same period endpoints.

Secondary diagnostics are:

- Q5 versus Q1;
- CSI 300 (`000300`);
- CSI 1000 (`000852`);
- ChiNext Index (`399006`).

Q5-Q1 is a factor diagnostic only. It is not an executable A-share long-short portfolio and must not be presented as one.

## Required outputs and measures for a later implementation

A later, separately approved implementation may produce versioned period, NAV, summary, QA, and narrative outputs. It must report cumulative return, CAGR, annualized volatility, Sharpe with `rf=0`, downside deviation, Sortino diagnostic, period-end maximum drawdown, Calmar, average turnover, total cost drag, terminal NAV, valid-period count, Q5 minus universe, relative wealth versus universe and benchmarks, tracking error, and information ratio.

The analysis must answer separately whether Q5 lowers risk, retains or sacrifices return, improves risk-adjusted return, remains directionally similar after costs, and depends on a small number of periods. Period-end drawdown is not daily maximum drawdown and must be labelled accordingly.

## Prohibited adaptation

The prototype must not use inverse-volatility weights or add momentum, reversal, liquidity, stop-loss, timing, or multifactor rules. It must not search Top N, window length, group proportion, reliability thresholds, cost scenarios, or benchmarks based on observed results. Revised-history or prospective results cannot change membership, factor construction, Q5 selection, or thresholds.

## Sample and reporting boundaries

Every later period output must include `sample_regime`, `freeze_date`, and `prospective_flag` under `reports/lowvol20_prospective_protocol_v1_5.md`. Revised history and pipeline-unseen retrospective extension are not prospective confirmation. Prospective records are append-only, and incomplete future periods remain in `waiting_for_complete_period` status without inferred performance.

All reporting is research-only and must retain `formal_performance_conclusion_allowed=false`, `execution_sim_ready=false`, and `no_investment_conclusion=true`.
