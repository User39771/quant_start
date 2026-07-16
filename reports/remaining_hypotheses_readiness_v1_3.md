# Remaining Hypotheses Readiness v1.3

## Stage Metadata

| field | value |
|---|---|
| status | `audited_with_blockers` |
| scope | `VOL20` and `Liquidity20` readiness only; no factor calculation, window/threshold choice, combination, backtest, or approval decision. |
| inputs | `adjusted_price_panel_v1_2.csv`, `backtest_price_panel_v1_2.csv`, 000300 benchmark calendar, baseline periods, source cache headers, QFQ manifest, and prior QA/readiness reports. |
| outputs | `factor_readiness_vol20_v1_3.csv`, `factor_readiness_liquidity20_v1_3.csv`, this report. |
| changed_files | Only the three requested report paths. |
| commands | Read-only `Get-Content`, `rg`, and Python schema/coverage/missingness checks. |
| exit_codes | `0` for evidence used in this audit. |
| QA | 70,145 adjusted-panel rows, 56 stocks, dates `2020-01-02` through `2026-06-16`; no duplicate stock-date rows per adjusted-panel QA. |
| blockers | No point-in-time universe, QFQ/cap vintages, suspension/ST/limit state, or execution data. |
| next-stage recommendation | No auto-approval. The CSV readiness fields are constraints for a later owner to reassess, not permission to calculate or simulate a factor. |

The baseline file has 312 full headline output rows across repeated universe/cost variants. It does not represent 312 independent rebalance dates; coverage counts below retain that output-row denominator for traceability.

## VOL20

| field | assessment |
|---|---|
| available | `partially_available` |
| point_in_time_status | `partial`: construct returns only through the 000300 market-calendar date T-1, but QFQ history was fetched retrospectively and adjustment vintages are not archived. |
| stock_coverage | `54/56` stocks have one or more exact windows; `13060/13290` eligible windows (`98.27%`) meet the data condition. |
| date_coverage | `2020-01-02` to `2026-06-16`; exactly 21 positive QFQ closes on T-20 through T-1 are required to produce 20 returns. |
| missing_pattern | QFQ missing rows: `002544` 1269, `300133` 1269, `002049` 10, `002131` 3, `301171` 3; listing histories and stock non-trading dates create additional invalid endpoints. |
| research_allowed | `true`, conditional on exact 21-close windows, T-1 signal timing, and exclusion of every incomplete or status-unknown window. |
| execution_sim_allowed | `false` |
| additional_data_required | As-of-date adjustment-factor/vendor vintages, corporate actions, and historical suspension/ST/limit/trade-state plus OHLCV execution data. |
| principal_biases | Current-universe bias, revised-QFQ risk, close-only observation, and suspension-induced false low volatility when a no-trade sequence is recorded as unchanged closes. |

The adjusted panel has `qfq_close` and an equal `adjusted_close` where `adjusted_flag=true`. Daily return must be `qfq_close_t / qfq_close_(t-1) - 1` only when both exact dates are observed. Forward fill, backfill, raw-close substitution, or using the prior stock-specific trading date would defeat the stated 20 market-day requirement.

Close-only data cannot observe intraday dispersion, limit locks, or fill feasibility. The 16 raw amount-missing records also carry repeated raw closes and missing QFQ; they are source-gap/no-trade ambiguous, not evidence of low volatility. Explicit trade status is required to screen suspension-induced flat-return windows reliably.

## Liquidity20

| field | assessment |
|---|---|
| available | `partially_available` |
| point_in_time_status | `partial`: dated values can end at T-1, but the legacy cache is not an archived historical vendor snapshot and neither its cap history nor turnover definition is point-in-time certified. |
| stock_coverage | Amount: `54/56` stocks and `13064/13290` exact 20-day eligible windows (`98.30%`). Field rows: amount `70129/70145`, turnover `70129/70145` in the raw/backtest panel only, circulating cap `70145/70145`, volume `0/70145`. |
| date_coverage | `2020-01-02` to `2026-06-16`; amount research requires 20 positive daily observations through T-1 on the 000300 calendar. |
| missing_pattern | Amount/turnover missing: `002049` 10, `002131` 3, `301171` 3. Volume is absent throughout. Circulating cap is numerically complete but source-vintage status is unknown. |
| research_allowed | `true` only for a trailing raw-amount research proxy with exact windows and excluded missing/nonpositive dates. |
| execution_sim_allowed | `false` |
| additional_data_required | Documented volume units; documented turnover unit/denominator; point-in-time float shares/circulating cap; historical trading status; participation and transaction-cost data. |
| principal_biases | Current-universe bias, cache-vintage risk, inferred rather than documented amount/turnover units, ambiguity between halts and source gaps, and no executable-capacity model. |

Input inventory: the adjusted panel exposes `amount`, `total_market_cap`, and `circulating_market_cap`, but omits `volume` and `turnover`. The separate raw/backtest panel exposes turnover on 70,129 rows and no volume values. Its turnover is plausibly a fraction because its median is `0.020000` and the median `amount / circulating_market_cap` is `0.024818`; this is a consistency check, not a source contract. Amount and cap magnitudes are consistent with CNY, but the cache does not document units or as-of vintages.

Zero or missing amount must be excluded from research eligibility. It must not be converted to zero liquidity, filled, or used to infer a suspension. Amount-based screening is not an execution model: without historical volume, trade status, limits, and participation constraints it cannot establish capacity or exit feasibility.

## Decision Boundary

Both candidates remain research-only and conditional. Neither is execution-simulation ready. No threshold, window selection beyond the audited 20-day requirement, factor combination, factor test, backtest, or next-stage approval is made here.
