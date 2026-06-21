# Codex Project Handoff

## Workspace

- Project root: `D:\Python_Files\quant_start`
- Keep local research entrypoint at `scripts/run_research.py`.
- Keep source under `src/aq_factor_lab`.
- Do not recreate Python env, do not run `npm install`, do not add proxy env vars.
- Do not modify files under `C:\Users\Hangxi Yang\OneDrive\文档\量化初步`.

## Environment And DB Access

- PostgreSQL credentials are stored in project root `.env`.
- Do not copy the `.env` password into docs or logs.
- `scripts/run_research.py` and `scripts/sync_database_cache.py` now auto-load root `.env` before running.
- Verified on 2026-06-17:
  - `python scripts/sync_database_cache.py --endpoints price --max-symbols 1 --years 1 --dry-run`
  - no longer fails with missing `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`.
- Important sync rule:
  - `--endpoints price` alone requires explicit `--symbols`.
  - To auto-load symbols from DB universe, include `universe`, for example:
    ```powershell
    python scripts/sync_database_cache.py --endpoints universe,price --years 5 --refresh-existing
    ```
  - For explicit symbols, use DB-style symbols:
    ```powershell
    python scripts/sync_database_cache.py --endpoints price --symbols SZ_000001,SZ_000002,SZ_000006 --years 1 --refresh-existing
    ```

## Current Data State

- DB schema is available at `data/processed/db_schema.csv`.
- `public.stock_prices` has `high_price` and `low_price`.
- `config/db_mapping.json` price endpoint now maps:
  - `high -> high_price`
  - `low -> low_price`
  - `amount -> amount`
  - `turnover -> turnover`
  - `total_market_cap -> total_market_cap`
  - `circulating_market_cap -> circulating_market_cap`
- Existing older DB price cache may still lack `high/low`; refresh price cache before trusting real-world tradability backtests.
- Verified explicit refresh for three symbols:
  ```powershell
  python scripts/sync_database_cache.py --endpoints price --symbols SZ_000001,SZ_000002,SZ_000006 --years 1 --refresh-existing
  ```
  This wrote price cache headers including `high,low`.

## Implemented Core Features

- Explicit DB mapping via `config/db_mapping.json`.
- Local CSV cache for universe, price, cashflow, profit, and Shenwan industry.
- Atomic CSV writes and cache coverage handling in DB sync layer.
- `total_market_cap` and `circulating_market_cap` are included in price cache.
- Price return calculation no longer uses unadjusted `close`.
- `future_return_20d` and monthly backtest period returns use the `total_market_cap` return proxy.
- `cf_yield = operating_cashflow / total_market_cap_cny`.
- Unit Alignment Guard chooses market cap multiplier; latest observed multiplier was `1`.
- `price_adjustment=market_cap_proxy`.
- `return_source=total_market_cap`.

## Factor Processing Implemented

- Core neutral factors:
  - `cf_yield_neutral`
  - `cashflow_quality_score_neutral`
  - `reversal_20d_neutral`
  - `volatility_20d_neutral`
- Processing pipeline:
  - MAD winsorization
  - cross-sectional Z-score
  - OLS neutralization against `ln_total_market_cap`
  - Shenwan L1 industry dummy neutralization when industry data is available
  - fallback to market-cap-only neutralization when industry data/sample is insufficient
- Raw `reversal_20d` and `volatility_20d` remain in `factor_panel.csv`; neutralized versions are added alongside them.
- `composite_alpha = cf_yield_neutral + reversal_20d_neutral - volatility_20d_neutral`.
- `composite_alpha` is `NaN` whenever any component is missing.
- Factor panel now carries Shenwan fields when cache exists:
  - `sw_l1_code`
  - `sw_l2_code`
  - `sw_l3_code`
  - `sw_l1_name`
  - `industry_source`

## Industry Data

- Discovery script: `scripts/discover_industry_classification.py`
- Discovery log: `data/processed/industry_discovery_log.md`
- Verified tables:
  - `public.map_company_industry_sw`
  - `public.dim_industry_categories_sw`
- Field contract:
  - stock field: `company_id`
  - L1/L2/L3 code fields: `l1_index_code`, `l2_index_code`, `l3_index_code`
  - names: join to `dim_industry_categories_sw.index_code`, read `industry_name`
  - date fields: `in_date`, `out_date`
- Industry cache endpoint: `industry_sw`
- Cache path: `data/cache/industry_sw/<code>.csv`
- As-of join rule:
  - `in_date <= obs_date`
  - `out_date is null OR out_date >= obs_date`

## Monthly Backtest Implemented

- Module: `src/aq_factor_lab/backtest_engine.py`
- Strategy:
  - monthly rebalance
  - `composite_alpha` descending by default
  - Top 50
  - equal weight
  - long-only
  - transaction cost rate `0.002`
- Explicit `BacktestConfig(factor_col="cf_yield_neutral")` still preserves the old single-factor selection path.
- Main outputs:
  - `data/processed/backtest_nav.csv`
  - `data/processed/backtest_holdings.csv`
  - `data/processed/backtest_trades.csv`
  - `data/processed/backtest_metrics.csv`
  - `data/processed/backtest_warnings.csv`
  - `reports/backtest_report.md`
- Absolute metrics:
  - `annualized_return`
  - `max_drawdown`
  - `sharpe_ratio`
  - `annualized_turnover`
- Benchmark and relative metrics:
  - benchmark: tradable high-liquidity valid-stock equal-weight return
  - `benchmark_return`
  - `benchmark_nav`
  - `excess_return = net_return - benchmark_return`
  - `excess_nav`
  - `annualized_excess_return`
  - `excess_max_drawdown`
  - `information_ratio`

## Real-World Constraint Upgrade

- Factor panel feature engineering now includes:
  - `amount`
  - `amount_20d`
  - `high`
  - `low`
  - `reversal_20d`
  - `volatility_20d`
- Price time-series features use group-safe `groupby("code")` windows for panel calculations:
  - `shift`
  - `pct_change`
  - `rolling`
- `amount_20d` definition:
  - trailing 20-trading-day mean of raw `amount`
  - `amount.rolling(20, min_periods=10).mean()`
  - unit stays raw CNY
- Backtest buy-side filters:
  - liquidity filter: `amount_20d >= 50_000_000`
  - tradability filter: `amount > 0 and high != low`
  - missing `amount_20d/amount/high/low` is treated as not buyable
  - filters affect strategy selection and tradable benchmark construction
  - benchmark construction uses the same rebalance-date liquidity/tradability pool
  - no sell-side halt/limit exit model yet
- `backtest_nav.csv` now includes:
  - `liquidity_filtered_count`
  - `untradable_filtered_count`
  - `buyable_count`
- `backtest_metrics.csv` now includes:
  - `average_liquidity_filtered_count`
  - `average_untradable_filtered_count`
- `backtest_report.md` now includes:
  - `liquidity_filter=amount_20d>=50000000`
  - `tradability_filter=amount>0_and_high_ne_low`
  - `buy_side_constraints=enabled`

## Current Caveat

- Older full cache was created before `high/low` were mapped.
- If a cache-only real-world backtest shows `average_buyable_count=0`, first refresh price cache with the updated mapping.
- `run_research.py` writes canonical shared outputs under `data/processed` and `reports`.
  Do not run multiple full research/report jobs concurrently in the same workspace unless run-specific output directories or locking are added;
  concurrent runs can overwrite `factor_panel.csv`, backtest CSVs, and markdown reports.
- `data/processed/db_sync_summary.csv` can be created as an empty diagnostic CSV when a sync has no warning/summary rows.
  `db_cache_quality_metadata()` now treats an empty or structurally incomplete sync summary as non-fatal report metadata:
  - empty file: `db_sync_summary_status=empty`
  - readable file without `status`: `db_sync_summary_status=missing_status_column`
  - normal file: `db_sync_summary_status=loaded`
- The minimal validated refresh was:
  ```powershell
  python scripts/sync_database_cache.py --endpoints price --symbols SZ_000001,SZ_000002,SZ_000006 --years 1 --refresh-existing
  python scripts/run_research.py --symbols 000001,000002,000006 --cache-only --years 1 --sleep 0
  ```
- Recommended next full refresh:
  ```powershell
  python scripts/sync_database_cache.py --endpoints universe,price --years 5 --refresh-existing
  python scripts/run_research.py --cache-only --years 5 --sleep 0
  ```

## 2026-06-17 Tradable Benchmark And Price Features Update

- Tradable benchmark is enabled as `benchmark=tradable_universe_equal_weight`.
- Benchmark and strategy buys use the same rebalance-date filters:
  - `amount_20d >= 50_000_000`
  - `amount > 0 and high != low`
  - missing `amount_20d/amount/high/low` is excluded.
- Factor panel carries raw and neutralized price-derived factors:
  - `reversal_20d`
  - `volatility_20d`
  - `reversal_20d_neutral`
  - `volatility_20d_neutral`
- Price-derived rolling features are computed through group-safe code-isolated windows:
  - `forward_return_20d`
  - `momentum_20d`
  - `reversal_20d`
  - `volatility_20d`
  - `turnover_20d`
  - `amount_20d`
- Single-stock `make_price_features()` drops any pre-existing raw `code` column before adding its internal sentinel, preventing duplicate pandas groupers.
- `composite_alpha` is generated from neutralized cash-flow yield, reversal, and volatility components.
- Current default strategy selection uses `composite_alpha`; set `factor_col="cf_yield_neutral"` to run the old default explicitly.
- `backtest_report.md` includes both `benchmark=tradable_universe_equal_weight` and `factor=composite_alpha`.

## Latest Verification

Run on 2026-06-17 after `.env` loading and `high/low` mapping fixes:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
python -m ruff check src scripts tests --select F,I
python -m compileall src tests scripts
python scripts/sync_database_cache.py --endpoints price --symbols SZ_000001,SZ_000002,SZ_000006 --years 1 --refresh-existing
python scripts/run_research.py --symbols 000001,000002,000006 --cache-only --years 1 --sleep 0
```

Observed results:

- Unit tests: `100 tests OK`
- Ruff: `All checks passed`
- Compileall: passed
- Explicit DB price sync for `SZ_000001,SZ_000002,SZ_000006`: success, 906 rows fetched
- Synced price cache headers include `high,low`
- Cache-only research for `000001,000002,000006`: exit 0, 42 factor panel rows

Run on 2026-06-17 after empty `db_sync_summary.csv` handling:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_cli.CliDefaultsTests.test_db_cache_quality_metadata_tolerates_empty_sync_summary
$env:PYTHONPATH='src'; python -m unittest discover -s tests
python -m ruff check src scripts tests --select F,I
python -m compileall src tests scripts
python scripts/run_research.py --symbols 000001,000002,000006 --cache-only --years 1 --sleep 0
python scripts/run_research.py --cache-only --years 5 --sleep 0
python scripts/run_research.py --symbols 600519,000001,300750 --years 1
```

Observed results:

- Empty sync summary regression test: `1 test OK`
- Full unit tests: `101 tests OK`
- Ruff: `All checks passed`
- Compileall: passed
- Three-symbol cache-only research: exit 0, 124 factor panel rows
- Full cache-only research: exit 0, 5015/5015 effective stocks, 288966 factor panel rows
- Project validation command: exit 0
- Full report outputs refreshed:
  - `data/processed/backtest_nav.csv`
  - `data/processed/backtest_holdings.csv`
  - `data/processed/backtest_trades.csv`
  - `data/processed/backtest_metrics.csv`
  - `reports/backtest_report.md`
  - `reports/factor_reliability_report.md`
- Latest full backtest metrics from `data/processed/backtest_metrics.csv`:
  - `annualized_return=0.2254520576`
  - `max_drawdown=-0.2029385551`
  - `sharpe_ratio=1.076269547`
  - `annualized_turnover=9.5`
  - `annualized_excess_return=0.01782055187`
  - `excess_max_drawdown=-0.3595417811`
  - `information_ratio=0.1878901127`
  - `average_liquidity_filtered_count=1112.8333333333333`
  - `average_untradable_filtered_count=65.44444444444444`

Run on 2026-06-17 after tradable benchmark and price reserve feature upgrade:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
python -m ruff check src scripts tests --select F,I
python -m compileall src tests scripts
python scripts/run_research.py --symbols 000001,000002,000006 --cache-only --years 1 --sleep 0
python scripts/run_research.py --cache-only --years 5 --sleep 0
```

Observed results:

- Full unit tests: `104 tests OK`
- Ruff: `All checks passed`
- Compileall: passed
- Three-symbol cache-only research: exit 0, 124 factor panel rows
- Full cache-only research: exit 0, 5015/5015 effective stocks, 288966 factor panel rows
- `factor_panel.csv` includes `reversal_20d` and `volatility_20d`
- `backtest_report.md` includes `benchmark=tradable_universe_equal_weight`
- Latest full tradable-benchmark metrics from `data/processed/backtest_metrics.csv`:
  - `annualized_return=0.2254520576`
  - `max_drawdown=-0.2029385551`
  - `sharpe_ratio=1.076269547`
  - `annualized_turnover=9.5`
  - `annualized_excess_return=0.1438280360`
  - `excess_max_drawdown=-0.1115657069`
  - `information_ratio=0.9436841741`
  - `average_liquidity_filtered_count=1112.8333333333333`
  - `average_untradable_filtered_count=65.44444444444444`

Run on 2026-06-17 after Group-Safe Multi-Factor Synthesis:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
python -m ruff check src scripts tests --select F,I
python -m compileall src tests scripts
python scripts/run_research.py --symbols 000001,000002,000006 --cache-only --years 1 --sleep 0
python scripts/run_research.py --cache-only --years 5 --sleep 0
```

Observed results:

- Full unit tests: `111 tests OK`
- Ruff: `All checks passed`
- Compileall: passed
- Three-symbol cache-only research: exit 0, 124 factor panel rows
- Full cache-only research: exit 0, 5015/5015 effective stocks, 288966 factor panel rows
- `factor_panel.csv` includes `reversal_20d`, `volatility_20d`, `reversal_20d_neutral`, `volatility_20d_neutral`, and `composite_alpha`
- Full factor coverage counts:
  - `reversal_20d_notna=283964`
  - `volatility_20d_notna=284575`
  - `reversal_20d_neutral_notna=283964`
  - `volatility_20d_neutral_notna=284575`
  - `cf_yield_neutral_notna=288762`
  - `cashflow_quality_score_neutral_notna=288762`
  - `composite_alpha_notna=283828`
- `backtest_report.md` includes `benchmark=tradable_universe_equal_weight`
- `backtest_report.md` includes `factor=composite_alpha`
- Single-stock price feature path tolerates raw price frames that already contain a `code` column.
- Latest full composite-alpha backtest metrics from `data/processed/backtest_metrics.csv`:
  - `annualized_return=0.059872381334241886`
  - `max_drawdown=-0.2034576628294018`
  - `sharpe_ratio=0.4095399621427453`
  - `annualized_turnover=16.086666666666666`
  - `annualized_excess_return=-0.047580147783767734`
  - `excess_max_drawdown=-0.25815251405663064`
  - `information_ratio=-0.23213487392228668`
  - `average_liquidity_filtered_count=1052.7222222222222`
  - `average_untradable_filtered_count=65.25`

## Suggested Next Step

Refresh full price cache with `high/low`, then rerun the full real-world constrained backtest:

```powershell
python scripts/sync_database_cache.py --endpoints universe,price --years 5 --refresh-existing
python scripts/run_research.py --cache-only --years 5 --sleep 0
```

## State Handoff (2026-06-18)

Quant methodology audit after IC-weighted composite and rank-buffer backtest:

- `operating_cashflow` factor basis was upgraded from raw reported flow to strict TTM. The pipeline now derives quarterly flows from cumulative financial statements and uses rolling four-quarter sums. `factor_panel.csv` includes `operating_cashflow_reported`, `operating_cashflow_ttm`, `revenue_ttm`, and `parent_net_profit_ttm`.
- Financial factor availability is point-in-time guarded by `announce_date` / `notice_date`; if missing, the pipeline falls back to `report_date + 120d`. Report metadata records `financial_available_date_policy=announce_date_else_report_date_plus_120d`.
- Universe survivorship is not fully solved. The panel only includes dates with historical price observations, so IPOs are not backfilled before listing, but the current universe may still omit delisted historical stocks. Report metadata records `universe_survivorship_status=current_universe_price_history_only` and a survivorship caveat.
- Transaction cost logic is documented as one-way rate per traded notional. Turnover is `sum(abs(target_weight - previous_weight))`; a full replacement has turnover `2.0` and costs `2 * transaction_cost_rate`.
- Sell-side exit constraints are still not modeled. Buy-side liquidity and tradability filters are active, but sell-side suspension, down-limit, or no-volume exit failures remain a caveat.
- Composite diagnostics are available in `ic_summary.csv` and `factor_reliability_report.md`, including IC, Rank IC, yearly IC stability, coverage, and group returns for `composite_alpha` and `composite_alpha_ic_weighted`.

Latest full cache-only run (`python scripts/run_research.py --cache-only --years 5 --sleep 0`) completed successfully:

- Effective stocks: `5015/5015`
- Factor panel rows: `288966`
- Backtest factor: `composite_alpha_ic_weighted`
- Benchmark: `tradable_universe_equal_weight`
- Annualized return: `0.0731367355`
- Annualized excess return: `-0.0488098220`
- Information ratio: `-0.2311194543`
- Annualized turnover: `13.8806557377`

Latest Rank IC means:

- `cf_yield_neutral`: `0.0262992043`
- `reversal_20d_neutral`: `0.0442553327`
- `volatility_20d_neutral`: `-0.0923418188`
- `composite_alpha`: `0.0821870388`
- `composite_alpha_ic_weighted`: `0.0947244968`

Interpretation for next sprint: IC-weighted composite has strong cross-sectional predictive power, but the Top 50 monthly implementation still loses to the tradable benchmark after costs because turnover remains high. Next work should focus on portfolio construction constraints, holding-period smoothing, sell-side tradability modeling, and point-in-time universe data, not on adding more raw factors.

## State Handoff (2026-06-18 Portfolio Construction)

Implemented portfolio construction experiments without adding raw factors.

Code and output changes:

- `BacktestConfig` now supports `rebalance_frequency="monthly"`, `buy_rank`, `sell_rank`, `max_turnover`, and `weighting_method` (`equal_weight`, `rank_weight`, `score_weight`).
- Legacy `keep_rank_threshold` remains supported for the default backtest path.
- Rank buffer semantics: existing holdings are retained while rank is within `sell_rank`; new buys must be within `buy_rank`; remaining seats are filled by current rank.
- `max_turnover` scales weight changes toward the desired portfolio. Initial deployment is not capped; later turnover is capped when configured.
- Default `backtest_report.md` / `backtest_metrics.csv` generation is preserved.
- New outputs:
  - `reports/portfolio_construction_report.md`
  - `data/processed/portfolio_experiment_metrics.csv`
  - `data/processed/portfolio_experiment_nav.csv`

Full cache-only run completed on 2026-06-18:

```powershell
python scripts/run_research.py --cache-only --years 5 --sleep 0
```

Portfolio experiment conclusions, all using `composite_alpha_ic_weighted` and `benchmark=tradable_universe_equal_weight`:

- `baseline_top50_equal_no_buffer`: annualized excess `-0.0654455812`, IR `-0.3550485507`, annualized turnover `17.7206557377`.
- `top100_equal`: annualized excess `-0.0513315722`, IR `-0.2886932663`, annualized turnover `16.5718032787`.
- `top200_equal`: annualized excess `-0.0496717160`, IR `-0.3158404280`, annualized turnover `15.3954098361`.
- `top50_buy50_sell150`: annualized excess `-0.0444406179`, IR `-0.1941306051`, annualized turnover `12.5901639344`.
- `top100_buy100_sell300`: annualized excess `-0.0350688964`, IR `-0.1528705123`, annualized turnover `10.9101639344`.
- `top100_buy100_sell300_max_turnover_0.5`: annualized excess `-0.0319925673`, IR `-0.1314890213`, annualized turnover `5.9746199619`.

Best in-sample candidate by annualized excess return is `top100_buy100_sell300_max_turnover_0.5`. It improves annualized excess return by about `0.0334530138` and cuts annualized turnover by about `11.7460357758` versus baseline, but excess return remains negative. This is not evidence of a deployable strategy; it shows portfolio construction can reduce implementation drag but has not yet converted the IC signal into positive tradable alpha.

Current caveats remain:

- These are full-sample in-sample comparisons only; next validation must be walk-forward or out-of-sample.
- Current universe may still have survivorship bias from missing delisted historical stocks.
- `total_market_cap` return proxy is not strict adjusted-price return.
- Sell-side suspension, down-limit, and zero-volume exit constraints remain incompletely modeled.

## State Handoff (2026-06-18 Portfolio Execution Diagnostics And Walk-Forward)

Implemented portfolio execution diagnostics, tail-position controls, and walk-forward validation without adding raw factors or expanding the parameter search materially.

Code and output changes:

- `BacktestConfig` now supports execution controls: `min_position_weight`, `dust_threshold`, `max_positions`, and `sell_priority`.
- Per-period NAV output now records holding-count distribution inputs, tail-position counts, concentration, buy/sell diagnostics, transaction-cost diagnostics, cash weight, and portfolio/benchmark/active factor score.
- Portfolio experiment metrics now include:
  - `average_holding_count`, `median_holding_count`, `max_holding_count`, `min_holding_count`
  - `average_positions_below_5bp`, `average_positions_below_10bp`, `average_positions_below_20bp`, `average_weight_below_10bp`
  - `average_top10_weight`, `average_top20_weight`, `average_effective_number_of_positions`
  - `average_buy_count`, `average_sell_count`, `average_partial_sell_count`, `turnover_from_buys`, `turnover_from_sells`, `average_transaction_cost`
  - `average_portfolio_factor_score`, `average_benchmark_factor_score`, `average_active_factor_score`
- Added walk-forward validation outputs:
  - `data/processed/walk_forward_metrics.csv`
  - `data/processed/walk_forward_nav.csv`
  - `reports/walk_forward_report.md`
- `reports/portfolio_construction_report.md` now includes walk-forward comparison beside the in-sample portfolio experiments.

Full cache-only validation completed successfully on 2026-06-18:

```powershell
python scripts/run_research.py --cache-only --years 5 --sleep 0
```

Execution diagnosis:

- The prior best in-sample candidate, `top100_buy100_sell300_max_turnover_0.5`, has a serious tail-position accumulation problem.
- Its nominal intent is a Top 100 strategy, but realized holdings are much broader:
  - annualized excess return: `-0.0319925673`
  - IR: `-0.1314890213`
  - annualized turnover: `5.9746199619`
  - average holding count: `376.2950819672`
  - median holding count: `440`
  - max holding count: `521`
  - average positions below 10bp: `190.9836065574`
  - average weight below 10bp: `0.0337920125`
- Diagnosis: the `max_turnover=0.5` cap partially sells positions instead of fully exiting them, so stale low-weight holdings accumulate across months. This lowers turnover but dilutes factor exposure and leaves many economically irrelevant tail positions.

Dust / max-position control result:

- Added controlled candidate: `top100_buy100_sell300_max_turnover_0.5_dust_maxpos300`.
- Settings: `min_position_weight=0.001`, `dust_threshold=0.0005`, `max_positions=300`, `sell_priority=worst_rank_first`.
- Results:
  - annualized return: `0.0979854157`
  - annualized excess return: `-0.0271859398`
  - IR: `-0.1014924569`
  - annualized turnover: `6.0715084012`
  - average holding count: `195.3278688525`
  - median holding count: `193`
  - max holding count: `273`
  - average positions below 10bp: `21.5573770492`
  - average weight below 10bp: `0.0157584449`
  - average active factor score: `0.9929224704`
- Interpretation: dust and max-position controls materially improve portfolio interpretability and reduce tail accumulation, while slightly improving annualized excess return versus the unconstrained max-turnover candidate. However, excess return remains negative after costs.

Walk-forward validation:

- Split `wf_1`: train `2020-01-31` to `2022-12-31`, test `2022-12-31` to `2023-12-31`.
  - selected experiment: `top200_equal`
  - test annualized return: `-0.0983264707`
  - test annualized excess return: `-0.0452419739`
  - test IR: `-0.4046041080`
  - test annualized turnover: `16.4290909091`
- Split `wf_2`: train `2021-01-31` to `2023-12-31`, test `2023-12-31` to `2026-04-30`.
  - selected experiment: `top100_buy100_sell300_max_turnover_0.5`
  - test annualized return: `0.2338769143`
  - test annualized excess return: `-0.0825663193`
  - test IR: `-0.6332725966`
  - test annualized turnover: `6.2222222222`
- Overall walk-forward summary:
  - average out-of-sample annualized excess return: `-0.0639041466`
  - average out-of-sample IR: `-0.5189383523`
  - average out-of-sample turnover: `11.32565657`
  - parameter stability: `unstable`
  - out-of-sample excess: negative

Conclusion for next sprint:

- The composite factor still has useful Rank IC on paper, but current portfolio construction does not pass tradable excess-return validation.
- The tail-position issue is now diagnosed and partially controlled, but the strategy remains negative out-of-sample.
- Do not claim the in-sample best configuration is valid. The next priority should be fixing data and execution realism before further portfolio tuning:
  - point-in-time universe / delisting coverage to reduce survivorship bias
  - strict adjusted-return data instead of `total_market_cap` return proxy
  - sell-side suspension, down-limit, and zero-volume exit constraints
  - then revisit factor layer or portfolio optimization after the data substrate is more reliable

## State Handoff (2026-06-18 Data Realism And Execution Audit)

Implemented a data realism / execution realism audit stage without adding raw factors and without widening portfolio experiment search.

Code and output changes:

- Added read-only audit script: `scripts/audit_market_data_realism.py`.
  - Reads database `information_schema` and small aggregate samples when DB is reachable.
  - Falls back to `data/processed/db_schema.csv` if DB access is unavailable.
  - Does not log database passwords or mutate database state.
- New outputs:
  - `data/processed/market_data_realism_audit.csv`
  - `reports/market_data_realism_audit.md`
- `normalize_price`, factor price features, and monthly backtest returns now prefer strict adjusted prices when present:
  - `adjusted_close`
  - else `close * adj_factor`
  - else existing `total_market_cap` proxy
- `sync_database_cache.py` now constructs `adjusted_close = close * adj_factor` when a future price sync includes both fields.
- `BacktestConfig` / backtest NAV now model minimal sell-side execution constraints:
  - same-day `amount == 0`
  - same-day `volume == 0` if available
  - same-day `high == low`
  - available pause / suspension / trading status flags
  - blocked exits are forced holds and recorded through `blocked_sell_count`, `blocked_sell_weight`, `forced_hold_count`, and `forced_hold_weight`.

Strict adjusted return audit result:

- Database schema contains `public.stock_prices_history.adj_factor`, but the sampled data is not usable for the current 5-year study:
  - `stock_prices_history` date range: `2026-06-04..2026-06-18`
  - rows: `56980`
  - `close_price_non_null=56980`
  - `adj_factor_non_null=0`
- Current local price cache still lacks `adjusted_close` and `adj_factor`.
- Therefore strict adjusted returns were **not** activated for the official backtest.
- Official `return_source` remains `total_market_cap_month_end`.
- Report flag remains: `strict_adjusted_return_unavailable=true`.

Universe / delisting audit result:

- No usable `list_date` found in schema.
- No usable `delist_date` found in schema.
- `companies.is_active` exists, but sample shows only current active-status style data:
  - `is_active=True:count=12222`
- This does not reconstruct historical point-in-time membership.
- Survivorship bias remains unresolved: current universe may omit historical delisted names and may bias results optimistic.

Trading / execution audit result:

- Same-day volume/amount fields exist.
- Sample diagnostic:
  - `stock_prices` date range: `2020-01-02..2026-06-18`
  - rows: `7240366`
  - `close_price_non_null=7240366`
  - `total_market_cap_non_null=7239170`
  - `amount_non_null=7239038`
  - `stock_prices_zero_amount_days=22`
- Minimal sell-side forced-hold model is now active.
- Explicit `limit_down` / `limit_up` prices were not found in the active mapped price table, so true limit-down sell-block modeling still remains incomplete.

Latest full validation run completed successfully:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
python -m ruff check src scripts tests --select F,I
python -m compileall src tests scripts
python scripts/run_research.py --cache-only --years 5 --sleep 0
python scripts/audit_market_data_realism.py
```

Notes:

- The first full `run_research.py --cache-only --years 5 --sleep 0` attempt hit a 30-minute tool timeout at `4812/5015` symbols.
- The same command was rerun with a longer timeout and completed successfully:
  - Effective stocks: `5015/5015`
  - Factor panel rows: `288966`

Latest default monthly backtest after sell-side forced-hold model:

- factor: `composite_alpha_ic_weighted`
- benchmark: `tradable_universe_equal_weight`
- return_source: `total_market_cap_month_end`
- annualized return: `0.06881295386`
- annualized excess return: `-0.05366186571`
- information ratio: `-0.2609310977`
- annualized turnover: `14.39357902`
- average attempted sells per month: `29.68852459`
- average blocked sells per month: `0.09836065574`
- average forced hold weight: `0.001960655738`

Latest portfolio construction results:

- `baseline_top50_equal_no_buffer`: annualized excess `-0.0640122070`, IR `-0.3466885751`, annualized turnover `17.68421666`.
- `top100_buy100_sell300_max_turnover_0.5`: annualized excess `-0.0316501225`, IR `-0.1296971074`, annualized turnover `5.9613391643`, average holding count `376.3442623`.
- `top100_buy100_sell300_max_turnover_0.5_dust_maxpos300`: annualized excess `-0.0276734145`, IR `-0.1048305950`, annualized turnover `6.0571755317`, average holding count `195.4098361`.
- Dust / max-position controls still improve interpretability, but excess return remains negative.

Latest walk-forward result:

- `wf_1` selected `top200_equal`; test annualized excess `-0.0448`, test IR `-0.3999`.
- `wf_2` selected `top100_buy100_sell300_max_turnover_0.5`; test annualized excess `-0.0828`, test IR `-0.6364`.
- Overall sample-out annualized excess: `-0.06377747765`.
- Overall sample-out IR: `-0.5181605268`.
- Parameter stability: `unstable`.
- Strategy still fails out-of-sample.

Next-step recommendation:

- Stop portfolio-layer optimization for now.
- Do not claim the composite strategy is valid.
- Priority should be data substrate remediation:
  - source usable adjusted prices or non-null adjustment factors covering the full research window
  - source historical listing / delisting membership
  - source limit-up / limit-down and richer trading-status fields
- Only after strict returns and point-in-time universe are resolved should the team revisit factor-layer research or portfolio optimization.

## State Handoff (2026-06-18 Methodology Closure And Data Gap Inventory)

Project posture has been shifted from strategy optimization to research-framework closure and data-gap remediation.

New closure documents:

- `reports/methodology_assessment.md`
- `reports/data_requirements.md`
- `data/processed/data_requirements.csv`
- `reports/external_data_integration_plan.md`

Current strategy validity conclusion:

- `strategy_validity=not_validated`
- The current strategy must not be described as a tradable validated alpha strategy.
- The strongest blocking evidence remains walk-forward failure:
  - overall sample-out annualized excess return: `-0.06377747765`
  - overall sample-out average information ratio: `-0.5181605268`
  - parameter stability: `unstable`

Current official data limitations:

- No usable strict adjusted-return data:
  - `stock_prices_history.adj_factor` exists, but audited sample has `adj_factor_non_null=0`.
  - current official `return_source` remains `total_market_cap_month_end`.
- No usable point-in-time lifecycle universe:
  - no usable `list_date`
  - no usable `delist_date`
  - current active-status fields do not reconstruct historical delisted names.
- Sell-side minimal constraints are implemented and measured, but they are not the main reason for strategy failure:
  - average blocked sells per month: `0.09836065574`
  - average forced hold weight: `0.001960655738`

Current prohibitions for the next agent:

- Do not keep tuning in-sample portfolio parameters and claim effectiveness.
- Do not add new raw factors as a workaround for failed walk-forward validation.
- Do not treat `total_market_cap` proxy returns as formal adjusted shareholder returns.
- Do not claim point-in-time universe correctness until historical list/delist data is available.

Necessary next conditions before strategy research resumes:

- Obtain usable adjusted prices or non-null adjustment factors covering the full research period.
- Obtain historical stock lifecycle data including list and delist dates.
- Obtain richer same-day trading-status fields, especially suspension and limit-up / limit-down prices.
- Convert any database, CSV, Parquet, or API source into internal standard contracts before feeding factors or backtests.
- Rerun the same pipeline without changing strategy logic after the data substrate is repaired.

If these data requirements cannot be met, the project should be positioned as a quantitative research framework and learning project, not a deployable trading strategy.
