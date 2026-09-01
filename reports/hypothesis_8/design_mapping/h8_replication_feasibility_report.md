# H8 Replication Feasibility & Design Mapping

## Decision summary

**Current execution readiness: H8_NOT_READY.** Recommended design direction, not a freeze: **STOCK_LEVEL_P1_P2_ADAPTED_REPLICATION**, conditional on resolving return decomposition/price treatment and a small GARCH dependency/implementation decision. No H8 coefficients, effects, significance, or real-data GARCH were computed.

Paper Primary is INDEX_LEVEL; Section 7 individual-stock analysis is DIAGNOSTIC. The current repository cannot faithfully reproduce index Primary or the 2400-day stock contract. H8 is not H7 robustness and cannot rescue or invalidate H7.

## Source and equation fidelity

The local 15-page PDF was checked at pp.4-6 (variables, Eq.7/Eq.9), pp.9-10 (Section 7/Table11), pp.11-12 (price limits), and p.14 (code availability). See `h8_equation_mapping.md` for the full algebra, controls and source anchors.

- Raw turnover target: daily volume / float-adjusted shares outstanding.
- Best local candidate: BAOSTOCK_CIRCULATING_TURNOVER; **CLOSE_ECONOMIC_MATCH**, not EXACT_MATCH. Existing H7 source-probe documentation labels the vendor denominator circulating shares. Its detailed free-float adjustments are not established by local package code; no correlation was used to certify identity.
- TOTAL_SHARE_TURNOVER is AVAILABLE_BUT_NOT_PAPER_PRIMARY; total and circulating/free-float denominators are not interchangeable.
- Recommended measurement: PAPER_STYLE_22D_TRUNCATED_TURNOVER, not H7's 200D deviation. No real detrended series was constructed in this audit.
- Recommend exact prior 22 CSI300 market dates, all active with positive finite turnover; gap invalidates the window. The paper does not specify stock-suspension handling. Last-22-active is reported only as a coverage alternative, not selected based on results.
- Paper D_POS includes zero (r>=0). Keep zero-return rows; their r-multiplied regressors are zero. This corrects the strict-positive candidate in the request using p.5.
- GARCH: arch_available=False; no dependency installed and no model estimated. A zero-mean GARCH(1,1) path requires a minimal package addition and explicit unit/initialization choices; weekday columns are available from dates.
- Equation algebra is fully mapped; exact implementation parity is **partial**, because author code, variance scaling details, suspension handling and decomposition are unresolved.

## Data-only coverage

Audit comparison interval: 2020-01-02 through 2026-05-11 for formation, with next endpoint 2026-05-12. This does not freeze H8 cutoff. BaoStock full cache dates range 2020-01-02 through 2026-08-20; this audit does not expand formation to those later dates.

| Measure | Value |
|---|---:|
| Universe | 5195 |
| Active rows | 7095355 |
| Active positive turnover rate | 100.00000000% |
| Active zero turnover | 0 |
| Active missing turnover | 0 |
| Suspended rows | 11522 |
| Suspended zero volume | 4441 |
| Suspended zero turnover / missing turnover | 103 / 11417 |
| Exact22 usable rows / positive-active-current denominator | 6930228 / 7095355 |
| Exact22 coverage | 97.672745% |
| Last22-active usable rows | 6981079 |
| Last22-active coverage | 98.389425% |
| Active positive opens / closes | 7095355 / 7095355 |
| Active missing/invalid opens | 0 |
| OHLC ordering inconsistencies | 0 |
| Potential P1 rows (before GARCH; exact22, active adjacent prices) | 6927836 |
| Potential P2 rows (same plus next open) | 6927836 |
| QFQ close alternative potential P1 rows (presence only) | 6117040 |
| Canonical QFQ files / date span | 5180 / 2020-12-28..2026-05-18 |
| Potential stock count, any P1 row, no history threshold chosen | 5191 |
| Zero current-return observations / valid current-price pairs | 186540 / 7087697 |
| Zero current-return share | 2.63188452% |
| Reopening after observed suspension | 2473 |
| Potential P1 after formation ST exclusion (candidate only) | 6767647 |

Prices are checked by presence/positivity/equality and OHLC ordering only. No real next-day return magnitudes, sign-conditioned outcomes or return-turnover association were calculated. Strict adjacent active-price coverage omits reopening rows whose previous market-date quote is suspended/stale; it never bridges gaps.

## Sample mapping, no threshold choice

| history_days | stocks |
|---|---|
| 750 | 4818 |
| 1000 | 4492 |
| 1250 | 4015 |
| 1500 | 3570 |
| 2000 | 0 |
| 2400 | 0 |

Counts above use active positive same-source OHLC days through the audit cutoff, not fitted regression rows. Final usable rows would be lower after lag/endpoint and GARCH requirements. All 2400-day counts are zero; selecting 750 instead is **not** authorized by this audit.

| candidate | N | history_median | history_min | history_max | observed_ever_ST | board_counts | size_quartiles |
|---|---|---|---|---|---|---|---|
| A_paper_fidelity | 0 | nan | nan | nan | 0 | {} | {} |
| A_main_no_observed_ST_before_history | 2792 | 1536 | 15 | 1536 | 0 | {'SH_MAIN': 1527, 'SZ_MAIN': 1265} | {'Q4_LARGE': 986, 'Q3': 766, 'Q2': 628, 'Q1_SMALL': 410, 'UNKNOWN': 2} |
| B_modern_any_P1_no_min_chosen | 5191 | 1534 | 25 | 1536 | 500 | {'SH_MAIN': 1702, 'SZ_MAIN': 1491, 'CHINEXT': 1393, 'STAR': 605} | {'Q4_LARGE': 1298, 'Q2': 1297, 'Q3': 1297, 'Q1_SMALL': 1296, 'UNKNOWN': 3} |

Ever-ST means observed within available 2020-cutoff history only, not a certified 2002-2021/lifetime record. Main-board classification treats both 300 and 301 as ChiNext and 688 as STAR; no existing H7 code/classification was changed. Size quartiles use available historical mean circulating market cap through the audit cutoff, not current/latest size. First observed cache date is not listing date; listing-age selection is only visible through observed history length and left truncation.

## Price and decomposition decisions

ST selection impact: current main boards contain 3195 stocks; 403 have observed ST history. The modern any-P1 candidate loses 500 stocks under an observed-ever-ST exclusion, leaving 4691. These are coverage comparisons, not chosen H8 filters.

BaoStock download script requests adjustflag=3 (raw), and cached open/high/low/close are same source/date/convention. This is the preferred **candidate** for paired intraday/overnight endpoints. It is not proven identical to CSMAR adjustment choices. Raw corporate-action gaps can contaminate overnight returns, so raw is not automatically economically clean.

Canonical broader-A QFQ contains close only, not QFQ open or an authoritative matched adjustment-factor series. It cannot guarantee consistent open/close adjustment or certify cross-ex-date overnight treatment. **QFQ_OVERNIGHT_REPLICATION_RISK=true** denotes an unverified pairing/adjustment risk, not proof that consistent QFQ necessarily creates artificial returns. Do not combine raw open with QFQ close.

**RETURN_DECOMPOSITION_CONTRACT_STATUS=UNRESOLVED.** The PDF explicitly defines simple returns yet writes an additive overnight/intraday identity. Conventional simple components obey the multiplicative identity and differ from the sum by their cross-product; only synthetic identity QA was run. Author code was not found locally or downloaded. No covert log-return substitution.

## Index and institutional inventory

| Paper index | Code | Local matching price/open/close/volume/turnover/float denominator | Full replication |
|---|---|---|---|
| SSE Composite | 000001 | none certified as index | false |
| SSE A-Share | 000002 | none certified as index | false |
| SZSE Component | 399001 | none | false |
| SZSE A-Share | 399107 | none | false |

Local benchmark panels contain CSI300 (000300), CSI1000 (000852), and ChiNext (399006), not these four targets; formal_benchmark_panel_v1_2 has no rows. Stock-cache 000001/000002 are stocks, not index observations. No constituent median turnover is substituted for aggregate index turnover. **INDEX_PRIMARY_REPLICATION=NOT_FEASIBLE** with current data.

No local H-share daily panel, H-share turnover, matched A/H identities or AHXA/AHXH panel was found in the data inventory. **P3_INSTITUTION_FEASIBLE=false**; no board, size or pre/post surrogate is used.

## Remaining mechanisms and limits

Authoritative historical limit prices/status and complete historical listing/board/ST/reform exception rules are unavailable. **historical_limit_status_ready=false; LOCAL_LIMIT_STATUS_CONSTRUCTIBLE=false** under current inputs. Price-limit robustness needs data supplementation; no return-near-10% or close==low inference is used.

**MARGIN_REFORM_REPLICATION_RELEVANT=false**: 2020-onward history has no pre-2010 period. The local candidate misses 2002-2019 market regimes and includes COVID/post-COVID and post-2021 observations. Modern broader-A adds ChiNext/STAR absent from paper stock sample. It is current-universe historical backfill, not point-in-time, with survivorship/future-universe bias. Formal paper algebra does not fix these limitations.

## Feasibility classification and human decisions

| Component | Classification | Qualification |
|---|---|---|
| P1 SIGN | ADAPTED_REPLICATION_FEASIBLE | Data presence; GARCH dependency/scaling and final sample unresolved |
| P2 TIMING | ADAPTED_REPLICATION_FEASIBLE | Same-source OHLC available; decomposition and corporate-action contract unresolved |
| P3 INSTITUTION | NOT_FEASIBLE | No A/H data |
| STOCK-LEVEL SIZE | ADAPTED_REPLICATION_FEASIBLE | Diagnostic only; recent historical coverage; no H7-gradient objective |
| PRICE-LIMIT ROBUSTNESS | DATA_SUPPLEMENT_REQUIRED | Authoritative status/rules missing |

Recommended next step: human review of raw-price corporate-action/decomposition convention, exact22 suspension rule, modern versus main-board sample and explicit minimum history, and minimal zero-mean GARCH dependency/unit contract. Then draft a separate H8 preregistration; do not run it now. Architecture direction is stock-level P1/P2 adapted, while current execution status remains H8_NOT_READY. No recommendation is based on local H8 coefficients.

## Boundary verification

H7 unchanged metadata check=True (size/mtime only; no hash framework). H7 was not imported or rerun. H7 role=PHENOMENON_DIAGNOSTIC; H8 role=MECHANISM_REPLICATION_DIAGNOSTIC.

`H8_results_opened=false; gamma_estimated=false; network_download_performed=false; MCTS_run=false; Phase_B_run=false; strategy_backtest_run=false; H7_rerun=false; H7_modified=false`.

The audit follows a data-quality workflow: denominators, temporal boundaries, unknown definitions and missing dependencies are separated from design feasibility. STOP AFTER FEASIBILITY / DESIGN MAPPING.
