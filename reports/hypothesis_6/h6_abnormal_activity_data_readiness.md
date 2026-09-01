# Hypothesis 6 — Abnormal Trading Activity Data Readiness Audit

## Technical summary

**H6_DATA_READY_WITH_EARLY_WINDOW_AND_EXECUTION_LIMITATIONS.** Local data can construct exact 50-market-day own-history shocks for daily amount and daily value turnover without a network download. Canonical broader-A share volume is unavailable, so a direct D04-style share-volume shock is not ready. Both usable candidates have median Primary-period coverage of **99.26%**; periods 1 and 2 have only about 1.7% coverage because their 50-day windows predate broad raw-activity history.

The recommended Primary measurement candidate is `DAILY_AMOUNT_OWN_HISTORY_RANK`: it is the most direct broadly available trading-activity field, and own-stock ranking removes permanent cross-stock scale without importing the market-cap lineage and strong VOL20 exposure already documented for VT. This recommendation uses only definition and signal-time data quality, never future performance. `MARKET_NORMALIZED_AMOUNT_OWN_HISTORY_RANK` is the secondary robustness candidate, subject to the same early-history limitation.

## Amount and VT are ready; share volume is not

| candidate                    | field_or_formula                | path                                                       | unit                               |   stock_coverage | date_min            | date_max            |   missing_rate | signal_time_legal   | network_download_needed   | notes                                                                                |
|:-----------------------------|:--------------------------------|:-----------------------------------------------------------|:-----------------------------------|-----------------:|:--------------------|:--------------------|---------------:|:--------------------|:--------------------------|:-------------------------------------------------------------------------------------|
| daily_share_volume           | volume                          | canonical broader-A raw cache                              | shares; unit unavailable           |                0 |                     |                     |    1           | False               | True                      | No canonical broader-A volume field; five legacy public-clean files are insufficient |
| daily_amount                 | amount                          | data/cache/price/*.csv                                     | CNY inferred; not source-certified |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 |    0.000178928 | True                | False                     | Direct trading-value field used by existing AMOUNT_MEAN20                            |
| daily_total_market_cap       | total_market_cap                | data/cache/price/*.csv                                     | CNY inferred; not source-certified |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 |    0.000164926 | True                | False                     | Daily historical dated; vintage lineage not audited                                  |
| daily_value_turnover         | amount / total_market_cap       | constructed from data/cache/price/*.csv                    | dimensionless                      |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 |  nan           | True                | False                     | Turnover-like; not D04 firm-specific volume or true turnover                         |
| market_total_amount          | sum(amount)                     | cross-sectional aggregate of canonical broader-A raw cache | CNY inferred                       |             5148 | 2021-02-10 00:00:00 | 2025-11-12 00:00:00 |  nan           | True                | False                     | Participant count median=4887, minimum=68; early history limitation retained         |
| market_total_volume          | sum(volume)                     | unavailable                                                | shares                             |                0 |                     |                     |    1           | False               | True                      | Cannot construct without broad daily share volume                                    |
| formation_day_qfq_return     | qfq_close_t / qfq_close_t-1 - 1 | data/processed/h5a_broader_a_daily_v1/*.csv                | decimal return                     |             5180 | 2020-12-28          | 2026-06-16          |  nan           | True                | False                     | Signal-time QFQ closes support a future normal-formation-return robustness audit     |
| price_limit_and_trade_status | limit/ST/tradability fields     | unavailable; raw cache has OHLC only                       | status                             |                0 |                     |                     |    1           | False               | True                      | OHLC cannot certify limit status, ST status or next-day tradability                  |

The raw `turnover` column is not selected because its denominator and unit are undocumented. VT is `Amount / TotalMarketCap`, not D04 firm-specific volume and not true shares turnover.

## Exact 50-day coverage retains two early-period shortfalls

| candidate | median coverage | minimum coverage | p10 coverage | median 3×3 cell | minimum 3×3 cell | p10 3×3 cell |
|---|---:|---:|---:|---:|---:|---:|
| Amount own-history rank | 99.26% | 1.72% | 98.49% | 276.5 | 0 | 59.0 |
| VT own-history rank | 99.23% | 1.72% | 98.47% | 251.5 | 0 | 61.2 |

Every window is the formation day plus its preceding 49 exact CSI300 market dates. Missing observations invalidate the stock-period; no earlier-date substitution or fill is used. The deterministic ordinal tie rule sorts by `(activity value ascending, trade_date ascending)`, then labels ranks 1–5 LOW_SHOCK, 46–50 HIGH_SHOCK and the remainder NORMAL.

## Shock states remain populated outside the two early incomplete periods

| candidate                     | shock_state   |   median_count |   minimum_count |   maximum_count |   median_percentage |
|:------------------------------|:--------------|---------------:|----------------:|----------------:|--------------------:|
| DAILY_AMOUNT_OWN_HISTORY_RANK | HIGH_SHOCK    |       424.5000 |              12 |            1610 |              0.0909 |
| DAILY_AMOUNT_OWN_HISTORY_RANK | LOW_SHOCK     |       703.0000 |               0 |            2853 |              0.1473 |
| DAILY_AMOUNT_OWN_HISTORY_RANK | NORMAL        |      3362.5000 |              47 |            4472 |              0.7307 |
| DAILY_VT_OWN_HISTORY_RANK     | HIGH_SHOCK    |       413.0000 |              11 |            1384 |              0.0915 |
| DAILY_VT_OWN_HISTORY_RANK     | LOW_SHOCK     |       686.5000 |               0 |            2564 |              0.1433 |
| DAILY_VT_OWN_HISTORY_RANK     | NORMAL        |      3378.5000 |              48 |            4470 |              0.7336 |

The full 56-period minimum includes the two early incomplete windows and is therefore not evidence that the shock rule itself produces empty states. Counts, percentages and all period × RETURN_STATE × shock-state cells are retained in `h6_shock_state_counts.csv` for review.

## Own-history extremes often coexist with local trends

| candidate                     | shock_state   |   observations |   median |   strong_trend_share |
|:------------------------------|:--------------|---------------:|---------:|---------------------:|
| DAILY_AMOUNT_OWN_HISTORY_RANK | HIGH_SHOCK    |          26070 |   0.2848 |               0.3126 |
| DAILY_AMOUNT_OWN_HISTORY_RANK | LOW_SHOCK     |          46252 |  -0.4501 |               0.4423 |
| DAILY_VT_OWN_HISTORY_RANK     | HIGH_SHOCK    |          25117 |   0.2454 |               0.2730 |
| DAILY_VT_OWN_HISTORY_RANK     | LOW_SHOCK     |          43628 |  -0.4166 |               0.4011 |

`strong_trend_share` is the descriptive share with `|Spearman(activity, time index)| >= 0.50`. This does not change the shock rule, but it makes slow local trend a worthwhile preregistered robustness concern. No recent-weighted, z-score or residual alternative is constructed here.

## Market-wide amount normalization is feasible with an early-history limitation

Across the required calendar span, daily broader-A amount aggregation has median participant count **4887**, minimum **68**, and **23** dates below 80% of the median participant count. Market-wide share-volume normalization is not feasible because canonical share volume is absent. The current-universe aggregate is not point-in-time and must retain survivorship/composition limitations.

## Formation-return robustness is supported; execution research is not

Daily QFQ closes can construct a formation-day return and locate it within a prior signal-time return history. This audit does not create a normal-return subsample. Reliable limit-up/down, ST, suspension/trading-status and next-day tradability fields are absent; OHLC alone is not an authoritative substitute.

```text
mechanism_research_ready=true_with_periods_1_2_50d_history_limitation
execution_research_ready=false
```

Formation-day activity is observable only after the close, and the locked calendar supports evaluation beginning no earlier than the next market day. No future outcome is read in this audit.

## Measurement recommendation

- **Primary:** `DAILY_AMOUNT_OWN_HISTORY_RANK`. It is directly observed, broadly covered and closer to abnormal trading activity than a market-cap-normalized proxy whose denominator adds lineage and covariate exposure.
- **Secondary robustness:** `MARKET_NORMALIZED_AMOUNT_OWN_HISTORY_RANK`, using stock amount divided by the same-day broader-A total amount before applying the same fixed 50-day own-history rank. It is closer to D04's market-normalization idea but inherits current-universe aggregation and early-history limitations.
- **Additional named candidate:** `DAILY_VT_OWN_HISTORY_RANK` remains feasible but is not selected as Primary; it is turnover-like rather than D04 firm-specific volume and retains size, VOL20 and market-cap-lineage limitations.

No performance comparison was used to make this recommendation. A future H6 preregistration must decide whether to retain all locked periods or formally treat periods 1 and 2 before opening any outcome.

## Further questions

- Can a source-certified share-volume field be added in a separate future data task if closer D04 replication becomes important?
- Should a future H6 contract include a non-result-driven slow-trend robustness diagnostic?
- Is execution research needed? If so, authoritative historical limit/ST/tradability fields are a separate data requirement.

## Audit identity

analysis_type=h6_abnormal_activity_data_readiness_audit; sample_role=historical_seen; future_return_accessed=false; H6_performance_run=false; proxy_selected_using_future_returns=false; network_download_performed=false; MCTS_run=false; Phase_B_run=false
