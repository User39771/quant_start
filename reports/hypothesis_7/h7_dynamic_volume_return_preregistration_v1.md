# Hypothesis 7 — Dynamic Volume–Return Relation Diagnostic v1

## Preregistration status

This contract was saved before any H7 v1 C2, OLS coefficient, coefficient sign, or return–volume relation was computed. It is frozen for this run.

```text
research_type=mechanism_diagnostic
sample_role=historical_seen
frequency=daily
D05_inspired=true
D05_exact_replication=false
current_universe_historical_research=true
universe_point_in_time=false
human_interpretation_required=true
alpha_claim_allowed=false
strategy_claim_allowed=false
causal_claim_allowed=false
OOS_claim_allowed=false
```

The study is inspired by Llorente, Michaely, Saar and Wang (2002), but is not an exact replication. It is a descriptive, sample-internal mechanism diagnostic. It cannot identify private information or risk sharing and cannot support investment conclusions.

## Frozen population and time contract

- Universe: the existing 5,195-stock broader-A current universe. It is not rediscovered or filtered using H7 results.
- Primary eligibility: a stock enters only if its final valid Primary 1D regression-row count is at least 750.
- Long-history eligibility: the nested subset with at least 1,000 of the same valid Primary 1D rows.
- `PRIMARY_MIN_VALID_REGRESSION_ROWS=750`; this is the only Primary sample.
- `LONG_HISTORY_D05_FIDELITY_MIN_ROWS=1000`; this is robustness only and may never replace Primary.
- Formation/current-return cutoff: `COMMON_ANALYSIS_CUTOFF=2026-05-11`. No formation observation after this date is used.
- No QFQ tail refresh is performed. Turnover observations after the cutoff remain in cache but are outside H7 v1.

The 1,000-row result is never promoted because it looks stronger, and the threshold is never lowered because either result looks weak. No other history threshold is tested.

## Turnover, suspension, ST and baseline contract

Primary turnover is the canonical field `TOTAL_SHARE_TURNOVER = BaoStock volume_shares / CNINFO point-in-time total_shares` from `data/processed/h7_turnover_daily_panel_v1.csv`. Market-cap/close, BaoStock implied shares, old-vendor turnover, and other denominators may not fill Primary. Existing CNINFO lineage flags are retained; nonblocking flags do not automatically exclude stocks.

Secondary turnover is `BAOSTOCK_CIRCULATING_TURNOVER`, expressed as a decimal ratio. It is measurement robustness only and is not a replacement for Primary because its circulating-share denominator differs from total shares.

- Suspension rule: `ACTIVE_DAYS_ONLY`. Formation day `t` must have `trading_status=1`; suspended rows are never converted to zero turnover.
- ST rule: formation observations with `isST=1` are excluded, but the stock and all non-ST formation history remain eligible.
- Past active ST observations remain eligible inside the turnover baseline. No `baseline_without_ST` variant is created.
- Baseline: the mean log turnover over the stock's last 200 prior active observations with positive finite turnover. It is strictly `t`-exclusive, may span more than 200 market days, uses no fill, and uses no future information.
- Primary activity: `LOG_TURNOVER=ln(TOTAL_SHARE_TURNOVER)` with no epsilon, and `V_t=LOG_TURNOVER_t-mean(LOG_TURNOVER over prior 200 active observations)`.
- Secondary activity is rebuilt independently from the last 200 prior active positive finite Secondary observations; Primary `V_t` is never reused as Secondary `V_t`.

Historical authoritative price-limit status is unavailable. No limit-up/down field is fabricated and no OHLC inference is used.

## Return and valid-row contract

The CSI 300 market calendar determines exact adjacent dates. Prices are canonical QFQ closes and are never filled.

```text
R_i,t = QFQ_i,t / QFQ_i,previous_CSI300_market_date - 1
R_i,t_to_t+h = QFQ_i,t+h / QFQ_i,t - 1
primary_horizon=1D
microstructure_horizons=2D,5D
```

The previous/next endpoint must exist on the exact CSI 300 market date; a missing stock price is not bridged to another active stock date. A valid Primary 1D row requires: `t <= 2026-05-11`, active formation, non-ST formation, positive finite Primary turnover, a complete strictly prior 200-active-observation Primary baseline, and finite QFQ at `t-1`, `t`, and `t+1`. The 2D/5D rows use the same formation contract and exact `t+2`/`t+5` endpoints. Future missingness does not modify formation data.

## Primary individual-stock equation

For every Primary stock, estimate by OLS on its own valid 1D rows:

```text
R_i,t+1 = C0_i + C1_i R_i,t + C2_i (V_i,t * R_i,t) + error_i,t+1
```

The design contains only intercept, `R_t`, and `V_t*R_t`. It does not add `V_t`, market returns, size, volatility, momentum, industry factors, or other controls. Report `nobs`, C0, C1, C2, Newey–West/HAC standard errors and t-statistics with fixed `maxlags=5`. Individual p-value counts are not a success criterion.

For each stock's valid V distribution, compute p10/p50/p90 and effective slopes `C1+C2*V_p`. Cross-sectional reporting covers mean, median, p10, p90, and positive share. C2 above zero means the conditional slope moves in a more positive direction as relative turnover increases; C2 below zero means it moves in a more negative direction. C2 above zero does not automatically mean momentum.

Primary C2 reporting includes count, mean, median, standard deviation, p1/p5/p10/p25/p75/p90/p95/p99, positive/negative shares, and the HAC t-stat distribution. C2 is not winsorized and stocks are not deleted based on C2. The most extreme 1% by absolute C2 is only flagged for inspection.

## Frozen robustness analyses

1. **Long-history 1D:** rerun the identical Primary equation for the nested `>=1000` subset. Report the same C2/effective-slope summaries plus overlapping-stock correlation and sign agreement versus Primary 750. Describe preservation, attenuation, amplification, or directional difference without calling 1,000 more correct.
2. **2D and 5D:** retain the fixed Primary 750 stock set, V and R_t. Estimate the corresponding equation only for stocks with at least 750 valid rows at that horizon. Report C2 distributions, stock-level correlation/sign agreement with 1D, and mean/median comparisons. Attenuation may elevate a short-horizon microstructure explanation; persistence only means the relation is not obviously confined to one-day mechanical noise.
3. **Secondary turnover matched sample:** begin with Primary 750 and retain exact dates on which both turnover measures, the applicable independently constructed V, R_t and R_t+1 exist. A stock requires at least 750 exact matched rows. On those same dates, estimate one equation with Primary V and one with Secondary V, then compare C2 correlation, sign agreement, means/medians and differences. Sample composition may not be confounded with denominator choice.

No other turnover baseline, epsilon, proxy, threshold, horizon, cutoff, winsorization, factor, MCTS or machine-learning variant is tested.

## Size and board diagnostics

For each Primary stock, define `SIZE_i` as the median of `ln(historical total_market_cap_i,t)` over dates that are in its valid Primary 1D regression period, use only finite positive observations with `t <= 2026-05-11`, and never use a latest/future size. Missing size excludes a stock only from this secondary diagnostic.

Estimate the unweighted cross-sectional regression:

```text
C2_hat_i = a + b_size * standardized(SIZE_i) + u_i
```

Report `b_size`, HC3 standard error, 90%/95% confidence intervals, R-squared, N, Spearman(C2, SIZE), and C2 mean/median/positive share by `Q1_SMALL` through `Q4_LARGE`. The D05-consistent direction is `b_size < 0`, but this cannot confirm private information. C2 is a generated first-stage estimate; HC3 does not fully account for first-stage estimation error or cross-stock dependence.

Board composition and C2 mean/median/positive share are reported for `SH_MAIN`, `SZ_MAIN`, `CHINEXT`, and `STAR` only to describe sample selection, especially the 1,000-row subset. No board-specific model or significance search is conducted.

## Numerical QA and interpretation order

Each regression checks finite X/Y, nonconstant R, nonconstant interaction, matrix rank and condition number. A singular or seriously non-estimable design becomes `REGRESSION_NUMERIC_FAILURE`; no manual repair is allowed. `LONG_HISTORY_1000_MEMBER => PRIMARY_750_MEMBER` must hold for every stock.

Interpretation order is fixed: (1) Primary 750 1D, (2) long-history 1,000 1D, (3) 2D/5D robustness, (4) Secondary matched measurement robustness, (5) size heterogeneity. Later results never replace Primary.

The runner reports facts and leaves interpretation to a human. It must not emit `SUPPORTED`, `REJECTED`, `ALPHA`, `PRIVATE_INFORMATION`, or `RISK_SHARING`, and it must not compute portfolios, Sharpe, costs, a C2-ranked strategy, or future stock selection.

## Required limitations

The final report must disclose: current-universe historical sampling; survivorship and future-universe bias; current-adjustment-vintage QFQ; CNINFO total-share lineage exceptions; BaoStock circulating-denominator differences; unavailable authoritative historical price-limit status; China T+1 and market-structure differences from the U.S. D05 setting; no quoted bid–ask spread or direct analyst-coverage identification; size is not a pure information-asymmetry measure; first-stage C2 measurement error; cross-sectional dependence; and sample-internal historical evidence rather than OOS prediction.

```text
PRIMARY_750_ROLE_FIXED_BEFORE_C2=true
LONG_HISTORY_1000_ROLE_FIXED_BEFORE_C2=true
1000_ALLOWED_TO_REPLACE_PRIMARY=false
parameter_search_performed=false
winsorization_performed=false
strategy_backtest_run=false
MCTS_run=false
Phase_B_run=false
```
