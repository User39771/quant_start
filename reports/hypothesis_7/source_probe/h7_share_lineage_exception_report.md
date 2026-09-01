# H7 Turnover Source Contract Exception Review

## Decision

**FULL_DOWNLOAD_READY_WITH_EXCEPTION_QUEUE**. The main contract is usable with explicit per-stock exceptions; this review does not authorize or start a full-market download.

```text
review_stock_count=15
cninfo_keyerror_root_cause=HTTP_200_EMPTY_RECORDS_IN_ORIGINAL_AND_FULL_HISTORY_WINDOWS; AKSHARE_WRAPPER_UNCONDITIONALLY_INDEXED_ANNOUNCEMENT_DATE
cninfo_network_failure_status=SUCCESS
cninfo_schema_consistent=True
cninfo_date_contract_status=REASONABLE_CONSERVATIVE; PARTIAL_LAG_EFFECT; NO_RULE_CHANGE
high_discrepancy_root_causes={"NO_MATERIAL_EXCEPTION_IN_REVIEW_METRICS": 7, "TRANSIENT_LOCAL_MARKET_CAP_OR_EVENT_TIMING_EXCEPTION": 3, "UNRESOLVED": 2, "LOCAL_TOTAL_AND_CIRCULATING_MARKET_CAP_LINEAGE_DISCREPANCY": 1, "LOCAL_TOTAL_MARKET_CAP_LINEAGE_DISCREPANCY": 1, "CNINFO_CIRCULATING_SHARE_DEFINITION_OR_LINEAGE_MISMATCH": 1}
baostock_implied_circulating_vs_cninfo_median_error=2.0335784588487865e-05
baostock_implied_circulating_vs_cninfo_p95_error=0.1850431110160369
local_implied_total_shares_validation_status=USEFUL_BUT_NOT_AUTHORITATIVE
local_implied_circulating_shares_validation_status=USEFUL_BUT_NOT_AUTHORITATIVE
cninfo_total_shares_primary_status=ACCEPTABLE_WITH_KNOWN_LIMITATIONS
baostock_circulating_turnover_secondary_status=ACCEPTABLE_WITH_LIMITATIONS
unresolved_exception_stock_count=2
data_cutoff=2026-08-20
full_market_download_performed=false
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
full_download_readiness=FULL_DOWNLOAD_READY_WITH_EXCEPTION_QUEUE
```

## Schema finding

The original 2020-start requests for 000004 and 300344 returned HTTP 200 with an empty `records` array, so there were no returned columns. AKShare then indexed `公告日期` unconditionally, converting a valid empty response into `KeyError`. Expanded 1990-start requests also returned no records, so these are unresolved no-history/opening-balance exceptions rather than evidence of a renamed field. HTTP status, top-level keys, raw column names, row counts, and up to three representative rows are preserved in `h7_cninfo_schema_review.csv`; no request headers or tokens are stored.

## Date contract

`information_available_date=max(change_date, announcement_date)` remains a reasonable conservative rule and prevents future-event backfill. Event-window rows explicitly identify the change-to-announcement gap. Where that gap explains material error, the stock is labeled accordingly; no event-specific replacement rule was introduced.

## Share-lineage diagnosis

The exception sample and event-window files provide stock/date evidence. Across 13,120 valid daily comparisons, BaoStock-implied circulating shares versus CNINFO have pooled median error 0.0020%, but pooled p95 is 18.50% because 000002 has a persistent roughly 18.5% circulating-share definition/lineage mismatch. Outside that exception, BaoStock generally tracks CNINFO more closely than local cap/close shares. Several large total-share discrepancies occur in local market-cap lineage: 688004 has a persistent local total/circulating ratio near 1.41 while BaoStock implied circulating shares stay near CNINFO; 301683 has a stable total-share ratio of 4/3 while its circulating measures agree. Therefore local implied shares remain a useful cross-check but are not authoritative. Simple-ratio features are reported as diagnostics only and are never used to repair values.

## Source decisions and next step

- `CNINFO_TOTAL_SHARES`: **ACCEPTABLE_WITH_KNOWN_LIMITATIONS** as Primary denominator, with empty-history/network/schema exceptions retained and no turnover constructed when an opening level is unavailable.
- `BAOSTOCK_CIRCULATING_TURNOVER`: **ACCEPTABLE_WITH_LIMITATIONS** as Secondary robustness; precision and zero/trading-status semantics are adequate, but its circulating-share denominator differs from D05 total shares.
- If a later human decision authorizes full download: cutoff 2026-08-20, cache-first, resumable, per-stock failure isolation, BaoStock first, CNINFO second, already-cached skip, no AKShare blocker, and checkpoint/progress logging. This task does not execute it.

No return, C2, H5/H6/MCTS/Phase B, prospective, or final-test analysis was run.
