# H5A Turnover-Like Activity Proxy Feasibility Audit

## Technical summary

**TURNOVER_PROXY_READY_WITH_LINEAGE_LIMITATION.** Local data are computationally sufficient for the Priority-A definition `VT20_DAILY`: the mean of `Amount_t / TotalMarketCap_t` over the exact 20 market dates ending at each signal date. No network download is required. Median Primary-period coverage is **99.98%**, minimum coverage is **99.95%**, and p10 coverage is **99.96%**.

The ratio is economically closer to shares traded / shares outstanding than raw amount, but it is not true turnover. Amount and market-cap magnitudes are consistent with CNY and their ratio is consistent with the local vendor turnover scale; however, units are inferred rather than source-certified and historical market-cap/share-vintage lineage remains `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`.

## Daily local inputs support Priority A

| field                                        | available   | daily   |   stock_coverage | date_min            | date_max            | unit                                     | time_status                                                      | used_in_primary_proxy   |
|:---------------------------------------------|:------------|:--------|-----------------:|:--------------------|:--------------------|:-----------------------------------------|:-----------------------------------------------------------------|:------------------------|
| daily_amount                                 | True        | True    |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 | CNY_INFERRED_NOT_SOURCE_CERTIFIED        | DAILY_HISTORICAL                                                 | True                    |
| daily_total_market_cap                       | True        | True    |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 | CNY_INFERRED_NOT_SOURCE_CERTIFIED        | DAILY_HISTORICAL_MARKET_CAP;HISTORICAL_DATED_NOT_VINTAGE_AUDITED | True                    |
| daily_circulating_market_cap                 | True        | True    |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 | CNY_INFERRED_NOT_SOURCE_CERTIFIED        | DAILY_HISTORICAL_NOT_VINTAGE_AUDITED                             | False                   |
| raw_daily_close                              | True        | True    |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 | CNY_PER_SHARE_INFERRED                   | DAILY_HISTORICAL                                                 | False                   |
| vendor_turnover                              | True        | True    |             5193 | 2020-01-02 00:00:00 | 2026-06-16 00:00:00 | DATABASE_NATIVE_UNDOCUMENTED_DENOMINATOR | DAILY_HISTORICAL_DENOMINATOR_UNRESOLVED                          | False                   |
| historical_total_shares_with_effective_dates | False       | False   |                0 |                     |                     | SHARES                                   | SCHEMA_OR_ALGEBRAIC_INFERENCE_ONLY                               | False                   |
| historical_free_float_shares                 | False       | False   |                0 |                     |                     | SHARES                                   | UNAVAILABLE                                                      | False                   |

The cache contains daily, historically dated and time-varying total market cap, not merely signal-date values or a single current snapshot copied backward. No auditable historical shares-outstanding series with effective/announcement/change dates exists, so direct D03 turnover cannot be reconstructed.

### Unit contract

- `amount_unit = CNY_INFERRED_NOT_SOURCE_CERTIFIED`
- `market_cap_unit = CNY_INFERRED_NOT_SOURCE_CERTIFIED`
- `conversion_applied = 1.0 / 1.0`
- `ratio_unit = dimensionless`

No source metadata formally certifies these units. This is an important lineage limitation, not a reason to rescale the ratio after seeing its values.

## Proxy definition and coverage

For each stock and Primary signal date, `VT20_DAILY = mean(Amount_t / TotalMarketCap_t)` on exactly the signal date and previous 19 CSI300 market dates. Every amount and denominator must be positive and finite. Missing dates, zero denominators and nonfinite observations invalidate the stock-period; no forward fill, backfill or earlier-date substitution is allowed.

|   period_index | signal_as_of_date   |   h5a_signal_members |   vt20_valid_members |   coverage |
|---------------:|:--------------------|---------------------:|---------------------:|-----------:|
|              1 | 2021-04-28 00:00:00 |                 3878 |                 3878 |     1.0000 |
|              2 | 2021-05-31 00:00:00 |                 3893 |                 3893 |     1.0000 |
|              3 | 2021-06-29 00:00:00 |                 3972 |                 3972 |     1.0000 |
|              4 | 2021-07-27 00:00:00 |                 4032 |                 4032 |     1.0000 |
|              5 | 2021-08-24 00:00:00 |                 4095 |                 4095 |     1.0000 |
|              6 | 2021-09-23 00:00:00 |                 4132 |                 4132 |     1.0000 |
|              7 | 2021-10-28 00:00:00 |                 4166 |                 4165 |     0.9998 |
|              8 | 2021-11-25 00:00:00 |                 4230 |                 4229 |     0.9998 |
|              9 | 2021-12-23 00:00:00 |                 4249 |                 4247 |     0.9995 |
|             10 | 2022-01-21 00:00:00 |                 4289 |                 4287 |     0.9995 |
|             11 | 2022-02-25 00:00:00 |                 4328 |                 4326 |     0.9995 |
|             12 | 2022-03-25 00:00:00 |                 4372 |                 4371 |     0.9998 |
|             13 | 2022-04-26 00:00:00 |                 4377 |                 4375 |     0.9995 |
|             14 | 2022-05-27 00:00:00 |                 4358 |                 4357 |     0.9998 |
|             15 | 2022-06-27 00:00:00 |                 4441 |                 4441 |     1.0000 |
|             16 | 2022-07-25 00:00:00 |                 4473 |                 4472 |     0.9998 |
|             17 | 2022-08-22 00:00:00 |                 4505 |                 4504 |     0.9998 |
|             18 | 2022-09-20 00:00:00 |                 4526 |                 4525 |     0.9998 |
|             19 | 2022-10-25 00:00:00 |                 4550 |                 4548 |     0.9996 |
|             20 | 2022-11-22 00:00:00 |                 4572 |                 4570 |     0.9996 |
|             21 | 2022-12-20 00:00:00 |                 4626 |                 4624 |     0.9996 |
|             22 | 2023-01-18 00:00:00 |                 4653 |                 4651 |     0.9996 |
|             23 | 2023-02-22 00:00:00 |                 4696 |                 4694 |     0.9996 |
|             24 | 2023-03-22 00:00:00 |                 4716 |                 4714 |     0.9996 |
|             25 | 2023-04-20 00:00:00 |                 4731 |                 4729 |     0.9996 |
|             26 | 2023-05-23 00:00:00 |                 4706 |                 4704 |     0.9996 |
|             27 | 2023-06-20 00:00:00 |                 4758 |                 4756 |     0.9996 |
|             28 | 2023-07-20 00:00:00 |                 4800 |                 4798 |     0.9996 |
|             29 | 2023-08-17 00:00:00 |                 4830 |                 4828 |     0.9996 |
|             30 | 2023-09-14 00:00:00 |                 4849 |                 4847 |     0.9996 |
|             31 | 2023-10-20 00:00:00 |                 4890 |                 4889 |     0.9998 |
|             32 | 2023-11-17 00:00:00 |                 4910 |                 4909 |     0.9998 |
|             33 | 2023-12-15 00:00:00 |                 4935 |                 4935 |     1.0000 |
|             34 | 2024-01-15 00:00:00 |                 4933 |                 4933 |     1.0000 |
|             35 | 2024-02-20 00:00:00 |                 4959 |                 4959 |     1.0000 |
|             36 | 2024-03-19 00:00:00 |                 4969 |                 4969 |     1.0000 |
|             37 | 2024-04-18 00:00:00 |                 4978 |                 4977 |     0.9998 |
|             38 | 2024-05-21 00:00:00 |                 4937 |                 4936 |     0.9998 |
|             39 | 2024-06-19 00:00:00 |                 4980 |                 4979 |     0.9998 |
|             40 | 2024-07-17 00:00:00 |                 4990 |                 4989 |     0.9998 |
|             41 | 2024-08-14 00:00:00 |                 5002 |                 5001 |     0.9998 |
|             42 | 2024-09-11 00:00:00 |                 5003 |                 5002 |     0.9998 |
|             43 | 2024-10-18 00:00:00 |                 5000 |                 5000 |     1.0000 |
|             44 | 2024-11-15 00:00:00 |                 4988 |                 4988 |     1.0000 |
|             45 | 2024-12-13 00:00:00 |                 5003 |                 5003 |     1.0000 |
|             46 | 2025-01-13 00:00:00 |                 5005 |                 5005 |     1.0000 |
|             47 | 2025-02-18 00:00:00 |                 5015 |                 5015 |     1.0000 |
|             48 | 2025-03-18 00:00:00 |                 5016 |                 5016 |     1.0000 |
|             49 | 2025-04-16 00:00:00 |                 5019 |                 5019 |     1.0000 |
|             50 | 2025-05-19 00:00:00 |                 4951 |                 4951 |     1.0000 |
|             51 | 2025-06-17 00:00:00 |                 5022 |                 5022 |     1.0000 |
|             52 | 2025-07-15 00:00:00 |                 5046 |                 5046 |     1.0000 |
|             53 | 2025-08-12 00:00:00 |                 5060 |                 5060 |     1.0000 |
|             54 | 2025-09-09 00:00:00 |                 5073 |                 5073 |     1.0000 |
|             55 | 2025-10-15 00:00:00 |                 5070 |                 5070 |     1.0000 |
|             56 | 2025-11-12 00:00:00 |                 5079 |                 5079 |     1.0000 |

## Size contamination is materially reduced, not eliminated

| characteristic   |   old_amount_activity |   VT20_DAILY |   VT20_high_low_standardized_difference |
|:-----------------|----------------------:|-------------:|----------------------------------------:|
| log market cap   |                0.6639 |      -0.2671 |                                 -0.6719 |
| VOL20            |                0.4360 |       0.6710 |                                  1.6397 |
| raw price        |                0.2220 |       0.0246 |                                  0.0248 |
| RETURN60         |                0.2435 |       0.2844 |                                  0.6100 |

Mean period-level Spearman with log total market cap changes from **0.664** for old ACTIVITY_PCT to **-0.267** for VT20_DAILY: the signed change is **-0.931**, while absolute correlation falls by **0.397**. The sign reversal means smaller stocks tend to have higher VT20, so size exposure remains rather than disappearing. The VT20 HIGH_PROXY−LOW_PROXY standardized log-cap difference averages **-0.672σ**. This is a signal-time contamination result, not evidence about returns.

VOL20 correlation is **0.671** versus **0.436** previously, so volatility contamination increases rather than falls. Raw-price correlation is **0.025** versus **0.222**. RETURN60 correlation is **0.284**. Return-state-specific correlations are retained in `turnover_like_proxy_characteristics.csv`; no future outcome was accessed. VT20 is economically closer to turnover, but these remaining exposures prohibit describing it as a pure activity measure.

## The proxy retains cross-sectional spread

Across all valid stock-periods, VT20_DAILY has median **0.013764**, p1 **0.001580**, p99 **0.122442**, and maximum **0.389740**. These are flagged for economic-scale review only; no observation was removed based on performance.

Within signal-date size terciles, spread remains:

| scope    |   periods |   median_proxy |   median_iqr |   median_p10 |   median_p90 |
|:---------|----------:|---------------:|-------------:|-------------:|-------------:|
| LARGE    | 56.000000 |       0.009547 |     0.011420 |     0.002924 |     0.029072 |
| MID_SIZE | 56.000000 |       0.013961 |     0.017845 |     0.005034 |     0.047331 |
| SMALL    | 56.000000 |       0.014397 |     0.016763 |     0.006194 |     0.045879 |

The denominator therefore does not collapse VT20 into a near-constant cross-section. Deterministic LOW/MID/HIGH proxy terciles are used only for this characteristic audit, never for performance.

## Relationship to D03

D03 turnover is shares traded divided by shares outstanding. The present value-turnover proxy satisfies only the approximation `Amount / TotalMarketCap ≈ (VWAP / Close) × ShareTurnover`. It is closer to the target economic concept than raw amount but is not an exact replication, true turnover or reconstructed D03 turnover.

## Limitations and next step

- The universe is current rather than historical point-in-time and retains survivorship bias.
- Market cap is daily historical but its archived vendor vintage and historical share-effective-date lineage are not audited.
- Unit identity is strongly plausible from magnitudes and cross-field consistency, not formally documented by the source.
- This audit does not establish that VT20 is an Alpha, a better predictor or an economically superior trading rule.

It is worth drafting a separate H5B-style preregistration for this single fixed `VT20_DAILY` proxy because local coverage and cross-sectional spread are adequate, the raw price-level relationship is nearly removed, and no new download is required. The preregistration must retain the material negative size exposure and stronger VOL20 exposure as named limitations, and must freeze state construction and outcomes before any performance is inspected. This audit stops before H5B.

## Direct answers to the 15 feasibility questions

1. **Daily amount exists:** yes, in the local raw price cache.
2. **Amount coverage:** 5,193 stocks, dated 2020-01-02 through 2026-06-16.
3. **Daily historical total market cap exists:** yes, with the same 5,193-stock coverage.
4. **Signal-date only:** no; the field is daily and time-varying.
5. **Market-cap time status:** `DAILY_HISTORICAL_MARKET_CAP;HISTORICAL_DATED_NOT_VINTAGE_AUDITED`.
6. **Network download required:** no.
7. **Selected proxy:** `VT20_DAILY`, the highest-priority locally feasible definition.
8. **Exact formula:** for each signal, average `Amount_t / TotalMarketCap_t` over the signal date and preceding 19 exact CSI300 market dates; all 20 ratios must be positive and finite, with no fill or date substitution.
9. **Primary coverage:** 56/56 periods; median 99.98%, minimum 99.95%, p10 99.96%.
10. **New proxy versus size:** mean period Spearman -0.267.
11. **Change from old 0.664:** signed change -0.931; absolute correlation is lower by 0.397, but size exposure remains with the opposite sign.
12. **New proxy versus VOL20:** mean period Spearman 0.671, higher than the old 0.436; this exposure worsens.
13. **New proxy versus raw price:** mean period Spearman 0.025, substantially below the old 0.222.
14. **Spread within size terciles:** yes; all three size strata cover 56 periods and retain positive median IQR and p90−p10 spread.
15. **Worth a separately preregistered H5B diagnostic:** yes, as a descriptive turnover-like diagnostic with explicit size, VOL20, lineage and survivorship limitations; no H5B performance is run here.

## Further questions

- Can the upstream database owner document currency units and historical market-cap revision policy?
- Can future work source dated shares outstanding if an exact D03-style replication becomes necessary?

## Audit identity

analysis_type=turnover_like_proxy_feasibility_audit; sample_role=historical_seen; future_outcome_used=false; future_return_accessed=false; causal_claim_allowed=false; alpha_claim_allowed=false; H5A_performance_rerun=false; alternative_proxy_performance_compared=false; network_download_performed=false; MCTS_run=false; Phase_B_run=false
