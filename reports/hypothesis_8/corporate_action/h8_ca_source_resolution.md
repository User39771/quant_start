# H8 Corporate-Action Source Resolution

`corporate_action_source_status=BAOSTOCK_CA_SOURCE_ACCEPTED_WITH_LIMITATIONS`.

## Direct source evidence

Installed BaoStock 00.9.30; function exists; signature `(code, start_date=None, end_date=None)`. Installed implementation: `D:\Python\Lib\site-packages\baostock\evaluation\season_index.py`. Actual server fields: `['code', 'dividOperateDate', 'foreAdjustFactor', 'backAdjustFactor', 'adjustFactor']`. A preliminary call on probe member 600019 returned 11 sparse dated records before the cached 40-stock pass; it is not an additional probe stock. The package's adjustment endpoint is used directly, not a third-party guessed BaoStock schema.

`dividOperateDate` is accepted as an effective adjustment/ex-date only after the CNINFO cross-check below. Factor values are positive finite metadata, never used to change a price or infer additional event dates. No attempt is made to infer a precise cumulative-factor algorithm from field names.

Probe sample is 40 deterministic main-board/non-observed-ever-ST stocks: five history-spanning members per SH/SZ x size-quartile cell. Selection uses only prior data-readiness counts/size. Request start=2020-01-01, end=2026-05-12. API success=40/40; with events=39; no events=1; source event count=204.

All accepted rows have parseable, unique, in-range common-market event dates and positive finite factors. The fixed pre-probe dense-series QA guard is >5% of common-market dates; this is an intentionally loose source sanity check, not a return-based threshold. Individual event counts and intervals are in the probe CSV. An empty successful response remains SUCCESS_NO_EVENTS, not a download failure.

## Independent ex-date check / false negatives

Existing local CNINFO share-history files contain share-change VARYDATE, not certified dividend ex-date. They were not silently promoted to corporate actions. Explicit CNINFO historical-dividend endpoint: [https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139](https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139); current installed AKShare `stock_dividend_cninfo` maps F020D to 除权日, F018D to 股权登记日, and F023D to 派息日. Only **F020D** is matched. No PDF or announcement corpus was downloaded. API supports code-level history; records outside 2020-01-01..2026-05-12 are discarded before caching/matching. Missing ex-dates are never replaced by payment/registration dates. Fresh responses can count undated rows, but dated-only normalized caches cannot reconstruct that count: cache-only missing-ex-date counts are UNKNOWN (blank), not zero. The validation denominator contains explicit known dates only and is not an exhaustive-event-completeness claim.

CNINFO successful stock probes=40/40. Unique stock/date external known events=193; exact-date matched=193; unmatched=0; match rate=100.000000%.

| classification | count |
|---|---|
| VALIDATED_EVENT | 193 |
| SOURCE_ONLY_PLAUSIBLE_EVENT | 11 |

VALIDATED_EVENT requires the same stock and exact date in both sources. Valid source-only rows are SOURCE_ONLY_PLAUSIBLE_EVENT, not falsely called independent validations. Unmatched explicit external events are UNRESOLVED_EVENT / false-negative evidence; the procedure does not shift dates to force matching. No price-return heuristic or old QFQ/raw ratio is used.

The source also returns listing initialization records: 10 probe rows align with local CNINFO A股上市 metadata. They are separately identified, not claimed to be dividend events; excluding the listing boundary cannot remove an otherwise valid adjacent pre-listing return. Other source-only rows remain explicitly unvalidated externally. Source event count includes these initialization rows.

Adapter QA correction: BaoStock's get_data() returns a columnless DataFrame for a successful no-record response even when response.fields contains all five fields. The adapter now verifies response.fields and preserves that schema for an empty frame; this is SUCCESS_NO_EVENTS, not a source-schema failure. The one affected probe member600962 was retried within the two-attempt budget; no sample expansion or source threshold change.

The pre-probe sufficient acceptance rule is >=38/40 successful BaoStock and CNINFO probes, no schema failures, at least one known external event, and **zero unmatched known external events**. A finite 40-stock probe cannot prove exhaustive lifetime capture: a pass is ACCEPTED_WITH_LIMITATIONS. Rejection stops before full download and GARCH.

Optional Sina/AKShare factor cross-check was not needed and was not run. Public BaoStock website retrieval returned an application shell rather than readable field documentation; no third-party schema description was substituted as authoritative evidence. The acceptance rests on direct package/server records plus actual CNINFO date matches.

## Coverage and limitations

Source coverage is the explicitly queried 2020-01-01..2026-05-12 interval, not the first observed event date. SUCCESS_NO_EVENTS means the API reports no event in that interval, not that lifetime absence is established. Cache failures give no coverage and exclude that stock from clean-row counts. Source-only coverage outside probe members is an acknowledged vendor-completeness limitation. Calendar plausibility and external-date validation do not prove every type of corporate action is captured.

All prices stay raw. H8 current-universe / observed-ever-ST / historical-seen limitations remain. H7 is unchanged; no H8 coefficients or future-return relations were computed.
