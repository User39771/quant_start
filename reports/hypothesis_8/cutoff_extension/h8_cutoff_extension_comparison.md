# H8 CA-Lineage Cutoff Extension Comparison

Status: **H8_EXTENDED_SAMPLE_READY_FOR_HUMAN_FREEZE**.

This is a sample-availability recalculation only. H8 results, Eq.9, gamma coefficients and outcome summaries were not opened or computed. The accepted BaoStock CA source, main-board/non-observed-ever-ST candidate set, exact-prior-22 rule, matched P1/P2 exclusion, zero-mean GARCH(1,1)-normal specification and longest-clean-segment chronology remain unchanged.

## Time and incremental source

- data cutoff: 2026-08-20
- analysis start: 2020-02-11
- final market endpoint: 2026-08-20
- new formation cutoff: 2026-08-19
- old formation cutoff: 2026-05-11
- added formation market days: 71
- candidate stocks: 2790
- API success: 2790; with new events: 1944; no new events: 846
- network failed: 0; schema failed: 0; metadata conflicts: 0
- new event rows: 1952
- optional CNINFO sanity: checked=20, exact matches=20, conflicts=0, status=INCREMENTAL_CNINFO_DATE_SEMANTICS_CONFIRMED

No 2020-01-01..2026-05-12 full-history request was made for a valid old cache. Successful empty incremental responses are valid `SUCCESS_NO_NEW_EVENTS` records.

## Segment and GARCH availability

- unchanged: 1872
- extended: 382
- switched: 536
- shortened/other: 0
- GARCH success: 2784
- GARCH numeric failure: 6
- old success to new failure: 1
- old failure to new success: 1

The selected longest clean segment was recomputed over the complete fixed analysis interval and ties choose the earliest segment. All GARCH diagnostics use only that new selected segment with the frozen package/model specification; failures are not rescued.

## Rows

- stocks with any final rows: 2784
- old total matched rows: 1282962
- new total matched rows: 1316388
- delta: 33426
- median old/new rows: 266.0 / 270.0

| threshold | old | new | delta | entered | dropped | candidate share | size inclusion spread |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 750 | 434 | 474 | 40 | 40 | 0 | 16.9892% | 15.4950% |
| 1000 | 287 | 312 | 25 | 25 | 0 | 11.1828% | 11.4778% |
| 1250 | 182 | 200 | 18 | 18 | 0 | 7.1685% | 9.1822% |
| 1500 | 121 | 130 | 9 | 9 | 0 | 4.6595% | 5.4519% |

## Corporate-action frequency selection

- all candidates CA count median/p25/p75: 7.0 / 5.0 / 8.0
- 750 sample median/p25/p75: 1.0 / 0.0 / 3.0
- 1000 sample median/p25/p75: 1.0 / 0.0 / 2.0
- Spearman(CA event count, final rows): -0.6788135952118561

These are sample-selection diagnostics, not return attribution. `recommended_primary_min_rows=HUMAN_JUDGMENT`; `recommended_long_history_sensitivity=HUMAN_JUDGMENT`.

H8_results_opened=false; Eq9_fit=false; gamma31_estimated=false; gamma32_estimated=false; outcome_statistics_computed=false; H7_rerun=false; H7_modified=false.

Recommended next step: **HUMAN_FREEZE_PRIMARY_AND_LONG_HISTORY_THRESHOLDS**. STOP.
