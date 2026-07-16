# LOWVOL20 Factor Research v1.4

## Research status

- status: research_not_ready
- verdict: not_available
- research_only=true
- primary_factor=LOWVOL20
- current-universe historical research
- universe_point_in_time=false
- suspension_status_available=false
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true

The primary estimand is the low-volatility effect conditional on minimum observed
price activity. Flat-price rules are data-quality filters, not suspension
identification or proof of tradability. Results do not generalize to the entire
nominal universe.

## Calendar and horizon

- target_rebalance_step=20_baseline_calendar_entries
- forward interval min/median/max: 20/20.0/20
- interval distribution: 20:12
- approximate_annualization=false

## Readiness

| rebalance_date      |   signal_count |   evaluation_count | readiness_pass   | ic_valid   | quantile_valid   | risk_ic_valid   | period_phase   |
|:--------------------|---------------:|-------------------:|:-----------------|:-----------|:-----------------|:----------------|:---------------|
| 2020-07-06 00:00:00 |             48 |                 48 | True             | True       | True             | True            | main           |
| 2020-08-03 00:00:00 |             49 |                 49 | True             | True       | True             | True            | main           |
| 2020-08-31 00:00:00 |             50 |                 50 | True             | True       | True             | True            | main           |
| 2020-09-28 00:00:00 |             50 |                 50 | True             | True       | True             | True            | main           |
| 2020-11-03 00:00:00 |             50 |                 50 | True             | True       | True             | True            | main           |
| 2020-12-01 00:00:00 |             50 |                 50 | True             | True       | True             | True            | main           |
| 2020-12-29 00:00:00 |             50 |                 50 | True             | True       | True             | True            | main           |
| 2021-01-27 00:00:00 |             49 |                 49 | True             | True       | True             | True            | main           |

## Return effect and risk persistence

_No primary result: research not ready._

_No primary result: research not ready._

_No primary result: research not ready._

Future-return effects and forward realized-volatility persistence are reported
separately. A missing forward risk path never changes the original quantile.

## Primary versus diagnostic samples

LOWVOL20 primary results use lowvol20_primary_reliable_sample. The
lowvol20_all_exact_windows_diagnostic reports direction before flat-price
screening. LOWVOL10/20/40 use common_10_20_40_exact_sample only and cannot
replace the primary conclusion.

## Hypothesis assessment

_No primary result: research not ready._

Epsilon is only numerical zero handling, not an economic materiality threshold.
Confidence intervals are descriptive historical-sample uncertainty, not clean
out-of-sample confirmation.

## Limitations

- This is historical chronological validation, not clean preregistered OOS confirmation.
- Current-universe / survivorship-like bias remains.
- Close-only flat-price diagnostics cannot prove continuous tradability.
- Period-end drawdown is not daily maximum drawdown.
- Q5-Q1 is not an executable A-share long-short strategy.
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true
