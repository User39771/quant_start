# H7 Final Contract Readiness Audit

## Decision

The existing offline data are sufficient to draft a contract for human review without estimating H7. The dominant endpoint issue is a synchronized QFQ tail: 5,175/5,180 existing QFQ files end on 2026-05-18, while turnover ends on 2026-08-20. A conservative common signal-date cutoff of **2026-05-11** leaves five market days for the fixed 5D endpoint. The current history is already adequate for a 1,000-row Primary and 750-row sensitivity; an incremental tail refresh is optional, not required to preregister H7.

```text
QFQ_global_date_min=2020-12-28
QFQ_global_date_max=2026-05-18
turnover_date_max=2026-08-20
turnover_panel_rows=7480293
tail_gap_calendar_days=94
tail_gap_market_days=67
endpoint_gap_primary_cause=A_QFQ_TAIL_NOT_REFRESHED
COMMON_ANALYSIS_CUTOFF=2026-05-11
QFQ_TAIL_REFRESH_REQUIRED=false
QFQ_TAIL_REFRESH_SCOPE=OPTIONAL_INCREMENTAL_EXISTING_SERIES_2026-05-19_TO_2026-08-20
estimated_tail_refresh_stock_count=5180
estimated_tail_refresh_stock_days=347060
```

## QFQ gap decomposition

|   horizon | reason                            |   missing_endpoint_rows |   missing_endpoint_stocks |   reason_share |
|----------:|:----------------------------------|------------------------:|--------------------------:|---------------:|
|         1 | A_QFQ_TAIL_NOT_REFRESHED          |                  343049 |                      5137 |    0.696621    |
|         1 | C_STOCK_PRICE_SERIES_ENDED        |                       5 |                         5 |    1.01534e-05 |
|         1 | D_INTERNAL_QFQ_GAP                |                    3928 |                      1161 |    0.00797649  |
|         1 | E_TURNOVER_ROW_NOT_PRICE_ELIGIBLE |                  140335 |                      3569 |    0.284975    |
|         1 | F_OTHER                           |                    5130 |                      5130 |    0.0104174   |
|         2 | A_QFQ_TAIL_NOT_REFRESHED          |                  343030 |                      5136 |    0.688084    |
|         2 | C_STOCK_PRICE_SERIES_ENDED        |                      10 |                         5 |    2.0059e-05  |
|         2 | D_INTERNAL_QFQ_GAP                |                    4893 |                      1161 |    0.00981488  |
|         2 | E_TURNOVER_ROW_NOT_PRICE_ELIGIBLE |                  140335 |                      3569 |    0.281498    |
|         2 | F_OTHER                           |                   10261 |                      5131 |    0.0205826   |
|         5 | A_QFQ_TAIL_NOT_REFRESHED          |                  342969 |                      5134 |    0.664357    |
|         5 | C_STOCK_PRICE_SERIES_ENDED        |                      23 |                         5 |    4.45527e-05 |
|         5 | D_INTERNAL_QFQ_GAP                |                    7261 |                      1161 |    0.0140651   |
|         5 | E_TURNOVER_ROW_NOT_PRICE_ELIGIBLE |                  140335 |                      3569 |    0.27184     |
|         5 | F_OTHER                           |                   25654 |                      5135 |    0.0496937   |

At the common signal cutoff, endpoint-presence coverage is:

|   horizon |   eligible_turnover_rows |   endpoint_coverage |
|----------:|-------------------------:|--------------------:|
|         1 |              6.04266e+06 |            0.976127 |
|         2 |              6.04266e+06 |            0.975967 |
|         5 |              6.04266e+06 |            0.975571 |

This cutoff removes the uniform tail while retaining the existing historical window. Remaining missing rows mainly reflect the bounded QFQ start, absent full QFQ series, the four early-ending files, or isolated internal gaps. Refreshing the 67-market-day tail is much smaller than a full-history reload, but it is not necessary merely to increase sample size.

## Suspension and zero contract

```text
suspended_rows=12307
suspended_volume_zero_share=0.36085154789956936
suspended_turnover_zero_share=0.008369220768668237
suspended_turnover_missing_share=0.9914682700901926
suspended_qfq_close_available_share=0.0012188185585439181
active_rows=7467986
active_zero_primary_turnover_rows=0
active_qfq_close_available_share=0.8326322518547838
RECOMMENDED_SUSPENSION_TREATMENT=ACTIVE_DAYS_ONLY
```

A suspension is not an observed low-demand trading day: the market did not permit normal trading. Treating it as zero would mix non-comparable states into log turnover. The Primary recommendation is therefore `ACTIVE_DAYS_ONLY`; suspended dates are invalid observations, not zeros.

## 200-day availability contracts

| contract | stocks any | median valid days | >=500 | >=750 | >=1000 | >=1250 |
|---|---:|---:|---:|---:|---:|---:|
| EXACT_200_MARKET_DAYS | 5135 | 1306 | 4928 | 4547 | 3941 | 2757 |
| LAST_200_ACTIVE_TRADING_DAYS | 5137 | 1406 | 4960 | 4657 | 4267 | 3746 |

`EXACT_200_MARKET_DAYS` is closer to literal calendar fidelity but invalidates long spans after even a short suspension. `LAST_200_ACTIVE_TRADING_DAYS` preserves a 200-observation historical mean among comparable trading observations; its calendar span may exceed 200 market days, but it never uses future observations. For A-share economic comparability, the proposed Primary is **LAST_200_ACTIVE_TRADING_DAYS**. The exact-market-day definition remains a data-only comparison, not a searched alternative.

## Log contract

Among valid active Primary observations: positive rate=100.00000000%, zero count=0, smallest positive=3.5224666e-06, p0.1=0.00044398178, p1=0.0012613851, p5=0.0026667878, median=0.013046859. The data support `LOG_TURNOVER=log(TOTAL_SHARE_TURNOVER)` on positive active rows. `epsilon_required=false`; no D05 epsilon is copied.

## Potential regression-row availability (presence only)

| horizon | stocks any | median rows | >=500 | >=750 | >=1000 | >=1250 |
|---:|---:|---:|---:|---:|---:|---:|
| 1D | 5119 | 1297 | 4877 | 4548 | 4125 | 3612 |
| 2D | 5119 | 1296 | 4874 | 4547 | 4123 | 3610 |
| 5D | 5118 | 1293 | 4868 | 4547 | 4114 | 3597 |

Rows require positive active Primary turnover, the proposed past-only baseline, QFQ t-1/t presence, and the appropriate future price endpoint. These are availability flags; no price ratio, coefficient, sign, or outcome comparison was computed.

## 750 versus 1,000 rows

| minimum | stocks | universe share | median market cap | board inclusion rates | size-quartile inclusion rates |
|---:|---:|---:|---:|---|---|
| 750 | 4548 | 87.55% | 6.926e+09 | {"CHINEXT": 0.9946695095948828, "SH_MAIN": 0.937793427230047, "STAR": 0.6996699669966997, "SZ_MAIN": 0.8181818181818182} | {"Q1_SMALL": 0.8691301000769823, "Q2": 0.8775981524249422, "Q3": 0.8728813559322034, "Q4_LARGE": 0.8822170900692841} |
| 1000 | 4125 | 79.40% | 7.054e+09 | {"CHINEXT": 0.9818763326226013, "SH_MAIN": 0.903169014084507, "STAR": 0.4603960396039604, "SZ_MAIN": 0.711864406779661} | {"Q1_SMALL": 0.7713625866050808, "Q2": 0.7821401077752117, "Q3": 0.7981510015408321, "Q4_LARGE": 0.8244803695150116} |

`RECOMMENDED_PRIMARY_MIN_ROWS=1000` because it is closer to the D05 long-history design and offers more plausible stock-level estimation stability. `RECOMMENDED_SENSITIVITY_MIN_ROWS=750` makes the selection cost visible and improves retention. This recommendation uses no coefficient or return information.

## ST and limit-status contract

ST observations are 2.373372% of otherwise potential 1D rows. Because ST stocks face special trading limits and microstructure, the proposed Primary excludes **ST observations**, while retaining the stock during non-ST intervals; excluding whole stocks would discard unrelated history. This remains for human approval. Historical limit-status is unavailable. That limitation is most material for 1D interpretation; 2D and 5D are retained as fixed microstructure-robustness horizons, not searched performance alternatives.

## Primary, Secondary, and exceptions

Primary availability: stocks any=5119, median rows=1297, >=750=4548, >=1000=4125. Secondary availability: stocks any=5119, median rows=1297, >=750=4548, >=1000=4125. They remain different measurements and are never substituted for one another.

`future_H7_blocking_exclusion_count=76` includes no Primary/opening level, corrupt/impossible denominator, or zero potential 1D history. `future_H7_flag_only_stock_count=3774` retains non-authoritative local discrepancies, circulating-denominator differences, deterministic duplicate-date warnings, and other lineage flags without deleting usable Primary rows.

## PROPOSED_H7_CONTRACT

```text
status=FOR_HUMAN_REVIEW
Primary turnover=TOTAL_SHARE_TURNOVER
Secondary turnover=BAOSTOCK_CIRCULATING_TURNOVER
Primary horizon=1D
Microstructure robustness horizons=2D,5D
Suspension treatment=ACTIVE_DAYS_ONLY
200D baseline definition=LAST_200_ACTIVE_TRADING_DAYS
Log zero handling=DIRECT_LOG_POSITIVE_ACTIVE_ROWS
ST treatment=EXCLUDE_ST_OBSERVATIONS; RETAIN_NON_ST_HISTORY
Primary minimum regression rows=1000
Sensitivity minimum regression rows=750
QFQ analysis cutoff=2026-05-11
QFQ tail refresh needed=false; optional incremental refresh only
Blocking data exclusions=no Primary/opening level; corrupt/impossible denominator; no potential 1D history
```

`C2_estimated=false`, `volume_return_regression_run=false`, `future_performance_accessed=false`, `network_download_performed=false`. Recommended next step: human review and approval or revision of this proposed contract, then create a separate formal preregistration before any H7 coefficient estimation.
