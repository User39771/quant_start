# H7 Post-Download Data Quality & Readiness Audit

## Decision

**H7_DATA_READY_WITH_EXCEPTIONS.** Both source caches cover the 5,195-stock universe and were re-read independently of status. Primary turnover is broadly constructible, but data-availability and lineage exceptions remain explicit; none was repaired with future events, local cap/close, or BaoStock-implied shares. This is a data-layer decision only.

```text
data_cutoff=2026-08-20
broader_a_stock_count=5195
BAOSTOCK_cache_files=5195
BAOSTOCK_valid_files=5195
BAOSTOCK_complete_or_usable_stocks=5195
BAOSTOCK_failed_or_corrupt_stocks=0
BAOSTOCK_suspected_truncated_downloads=0
BAOSTOCK_status={"SKIP_ALREADY_COMPLETE": 5192, "SUCCESS": 3}
CNINFO_cache_files=5195
CNINFO_valid_files=5195
CNINFO_status={"SUCCESS_WITH_EVENTS": 5180, "SUCCESS_NO_EVENTS": 15}
CNINFO_stocks_without_opening_total_shares=35
status_cache_mismatch_count=0
PRIMARY_stock_count_with_any_valid_data=5180
PRIMARY_median_coverage=1.0
PRIMARY_p10_coverage=0.996268656716418
PRIMARY_stocks_ge_99pct_coverage=5084
PRIMARY_stocks_ge_95pct_coverage=5172
PRIMARY_stocks_ge_90pct_coverage=5178
PRIMARY_stocks_lt_80pct_coverage=16
SECONDARY_stock_count=5195
SECONDARY_median_coverage=1.0
SECONDARY_median_distinct_values_per_stock=1551.0
primary_vs_secondary_expected_order_rate=0.8613196874003952
primary_gt_secondary_by_more_than_1pct_rows=41701
baostock_implied_circ_vs_cninfo_median_error=1.5908017288028774e-05
baostock_implied_circ_vs_cninfo_p95_error=0.23696865446344897
stocks_with_any_valid_200d=5135
stocks_ge_500_valid_days=4938
stocks_ge_750_valid_days=4588
stocks_ge_1000_valid_days=4071
stocks_ge_1250_valid_days=2976
history_length_size_spearman=0.14253133302915266
endpoint_1D_coverage=0.9240834899131074
endpoint_2D_coverage=0.9231751564537296
endpoint_5D_coverage=0.920519277243051
tradestatus_coverage=1.0
isST_coverage=1.0
suspended_stock_days=12307
ST_stock_days=198062
historical_limit_status_ready=false
top_quality_exception_types={"LOCAL_CIRCULATING_SHARE_VALIDATION_DISCREPANCY": 2385, "LOCAL_TOTAL_SHARE_VALIDATION_DISCREPANCY": 1876, "BAOSTOCK_CNINFO_CIRCULATING_DISCREPANCY": 1394, "CNINFO_DUPLICATE_INFORMATION_DATE": 1008, "CNINFO_INCOMPLETE_EVENT_DATE": 992, "PRIMARY_SECONDARY_ORDER_VIOLATION_GT_1PCT": 580, "CNINFO_EXTREME_TOTAL_SHARE_JUMP": 94, "NO_OPENING_TOTAL_SHARES": 35, "SUCCESS_NO_EVENTS_NO_OPENING_LEVEL": 15}
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
network_download_performed=false
H5_run=false
H6_run=false
MCTS_run=false
Phase_B_run=false
H7_data_readiness=H7_DATA_READY_WITH_EXCEPTIONS
```

## Cache and structural QA

Status and physical caches were checked independently. BaoStock valid files=5,195/5,195; CNINFO valid files=5,195/5,195. Empty CNINFO histories are valid `SUCCESS_NO_EVENTS` responses, not schema crashes. Malformed or stale status/cache combinations are listed in the exceptions CSV. Structural exception counts include schema, duplicate date, cutoff, sign/range, information-date, duplicate-event and extreme-jump checks.

```text
files_with_schema_error=0
files_with_corrupt_content=0
files_with_duplicate_dates=0
files_with_after_cutoff_rows=0
files_with_negative_volume=0
files_with_invalid_turnover=0
stocks_with_internal_market_day_gaps=0
```

## Measurement and zero semantics

Primary decimal turnover quantiles are p0=0, p0.1=0.00030870234, p1=0.0012273142, p5=0.0026516252, median=0.013037174, p95=0.074802626, p99=0.15048953, p99.9=0.28219261, max=0.63933608. `turnover>1` rows=0; values were flagged, not winsorized.

Secondary turnover has zero rate=1.3792012e-05, missing rate=0.0016312195, p1=0.001687, median=0.017546, p99=0.2315662, max=1.064833. Median distinct values per stock=1551.0, p10=940.0; precision concern=False.

Full-market zero/missing patterns are stored in `h7_microstructure_readiness.csv`. `ZERO_OR_MISSING_SEMANTICS_REVIEW_REQUIRED=False` is based only on whether B/C/D/F exceed 1% in aggregate; it does not select epsilon.

## Share lineage and denominator cross-checks

Point-in-time total shares use only complete events on/after `max(change_date, announcement_date)`, then apply the known level forward. The interval before the first usable level remains unknown. `SUCCESS_NO_EVENTS` has no authoritative external opening level in the current project, so it stays `NO_OPENING_TOTAL_SHARES`.

Across overlap rows, `TOTAL_SHARE_TURNOVER <= BAOSTOCK_CIRCULATING_TURNOVER` within numerical tolerance on 86.131969%; rows exceeding the secondary by more than 1%=41,701. These are validation flags, not automatic deletions, because the denominators differ. BaoStock-implied circulating-share relative error versus CNINFO has median=0.001591%, p90=3.085404%, p95=23.696865%, p99=94.781727%.

Local implied total-share error has pooled median=1.410343%, p95=54.311927%; local implied circulating-share error has median=1.915709%, p95=70.842280%. These remain **USEFUL_BUT_NOT_AUTHORITATIVE** and never fill Primary.

## Exact history and endpoint readiness

Every eligible t requires a valid current Primary measurement and all exact prior 200 BaoStock market dates; t is excluded from its own baseline and no missing date is replaced. These are measurement-availability counts only: the future log/epsilon contract remains undecided. QFQ endpoint coverage checks only the presence of t-1, t and t+1/t+2/t+5 closes; no return was calculated.

| row_type   |   threshold |   stock_count |   percentage_of_universe |   size_quartile |   inclusion_rate |
|:-----------|------------:|--------------:|-------------------------:|----------------:|-----------------:|
| threshold  |         500 |          4938 |                 0.950529 |             nan |              nan |
| threshold  |         750 |          4588 |                 0.883157 |             nan |              nan |
| threshold  |        1000 |          4071 |                 0.783638 |             nan |              nan |
| threshold  |        1250 |          2976 |                 0.572859 |             nan |              nan |

The size relation is Spearman(valid history days, log latest historical market cap)=0.142531. Size-quartile inclusion rates are in `h7_history_sufficiency_real.csv`; no new industry or listing-year metadata was downloaded.

## Board and microstructure readiness

| board   |   stock_count |   bao_success |   cninfo_event_stocks |   median_primary_coverage |   median_valid_200d_primary_days |
|:--------|--------------:|--------------:|----------------------:|--------------------------:|---------------------------------:|
| CHINEXT |           938 |           938 |                   936 |                         1 |                           1408   |
| SH_MAIN |          1704 |          1704 |                  1696 |                         1 |                           1408   |
| STAR    |           606 |           606 |                   605 |                         1 |                           1022.5 |
| SZ_MAIN |          1947 |          1947 |                  1943 |                         1 |                           1330   |

`tradestatus` and `isST` are available at the rates above. Suspended rows are retained. Historical limit-up/down or one-price-limit authoritative fields are absent, so `historical_limit_status_ready=false`; OHLC was not promoted to an authoritative substitute. Constant-close, suspended-price, stock-specific positive-volume p1-day, and ST-day diagnostics are descriptive only.

## Recommended next step

Review the explicit lineage/order/status exceptions and choose a minimum valid-history threshold using coverage and selection-bias evidence only. Then preregister H7 measurement, zero/log handling, eligible-sample and microstructure exclusions before any coefficient estimation. Do not select the threshold from H7 results.
