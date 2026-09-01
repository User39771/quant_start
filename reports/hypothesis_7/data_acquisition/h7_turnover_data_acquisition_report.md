# H7 Full-Market Turnover Data Acquisition

## Data-layer result

`H7_TURNOVER_DATA_READY_WITH_EXCEPTIONS`. This is a cache-first data result, not an H7 hypothesis result.

```text
data_cutoff=2026-08-20
broader_a_stock_count=5195
baostock_status={"SKIP_ALREADY_COMPLETE": 5192, "SUCCESS": 3}
cninfo_status={"SUCCESS_WITH_EVENTS": 5180, "SUCCESS_NO_EVENTS": 15}
primary_total_share_turnover_stock_count=5180
primary_total_share_turnover_median_coverage=1.0
primary_total_share_turnover_p10_coverage=0.996268656716418
secondary_baostock_turn_stock_count=5195
secondary_baostock_turn_median_coverage=1.0
exception_stock_count=2688
exception_rate=0.5174205967276228
top_exception_types={"LARGE_VALIDATION_DISCREPANCY": 1876, "CNINFO_INCOMPLETE_EVENT_DATE": 992, "NO_OPENING_TOTAL_SHARES": 20, "CNINFO_NO_HISTORY": 15}
history_length_size_spearman=0.14244633089340705
rows_after_2026_08_20_received=3140
rows_after_2026_08_20_discarded=3140
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
H5_run=false
H6_run=false
MCTS_run=false
Phase_B_run=false
H7_turnover_data_status=H7_TURNOVER_DATA_READY_WITH_EXCEPTIONS
```

## Contract and limitations

BaoStock volume is stored in shares, amount in CNY, and vendor turnover percent is converted to a decimal secondary measure. Primary turnover is volume divided by CNINFO point-in-time total shares. CNINFO events become usable only on `max(change_date, announcement_date)` and are applied forward; no later event is backfilled into an earlier date. HTTP 200 with empty records is retained as `SUCCESS_NO_EVENTS`. Local cap/close and BaoStock-implied circulating shares are validation only.

The exception queue records source failures, empty histories, incomplete event dates, unknown opening levels, and large validation discrepancies. Validation discrepancies do not invalidate CNINFO automatically. Exact 200-day eligibility requires the current day plus all 200 preceding observations to be valid, without fill; the history thresholds remain for human selection.

|   minimum_valid_days |   stock_count | recommended   |
|---------------------:|--------------:|:--------------|
|                  500 |          4938 | False         |
|                  750 |          4590 | False         |
|                 1000 |          4073 | False         |
|                 1250 |          2977 | False         |

Recommended next step: review the exception queue and choose the minimum valid-history threshold before any H7 regression. No C2 or future-performance analysis was run.
