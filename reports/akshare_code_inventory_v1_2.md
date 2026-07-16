# AkShare Code Inventory v1.2

## Scope And Method
- Read-only scan of Python source, tests, config, local cache metadata, and existing diagnostics.
- No live fetch and no network access.
- No code, backtest engine, historical cache, or stock-pool files were modified.

## Requested rg Commands
```powershell
rg --no-ignore -n "akshare|stock_zh_a_hist|index_zh_a_hist|stock_zh_index_daily_tx|get_daily_price|get_index_price|DataLayerService|qfq|adjust|data/cache/price" -g "*.py"
rg --no-ignore -n "data/cache/price|to_csv|manifest|retry|sleep|backoff" -g "*.py"
```

## Inventory Summary
- Python files with relevant keyword hits: 60
- `data/cache/price` CSV files: 5197
- `data/cache/price` total entries including tmp/non-csv: 5198

## Main Findings
1. The strongest provenance for current `data/cache/price` is the database sync path: `scripts/sync_database_cache.py` + `src/aq_factor_lab/db_source.py` + `config/db_mapping.json`.
2. The old AkShare price cache path is `scripts/precache_price.py` using `src/aq_factor_lab/data.py::AkShareClient.price_history`; it is slower but has stronger retry/cache-fallback behavior.
3. Current formal fetch depends on `stock_zh_a_hist` for raw/qfq stocks and `index_zh_a_hist` for benchmarks; diagnostics show those direct endpoints are unstable now.
4. `stock_zh_index_daily_tx` is a proven benchmark fallback from current diagnostics.

## Historical Cache Format
- CSV cache files: 5197.
- Sampled schema:
- sampled 200 files: `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange`
- Includes: `close`, `high`, `low`, `amount`, `turnover`, `total_market_cap`, `circulating_market_cap` for most sampled files.
- Missing for formal baseline: `open`, `volume`, `pre_close`, explicit `qfq_close`/`adj_factor`.
- Known exception: `300378` lacks `high/low` in sampled cache and ends at 2026-06-12.

| code | rows | min_date | max_date | columns | bytes |
|---|---:|---|---|---|---:|
| 000063 | 1268 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 159287 |
| 300857 | 1269 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 154955 |
| 000681 | 1269 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 155363 |
| 000901 | 1269 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 151984 |
| 000938 | 1269 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 156940 |
| 000977 | 1269 | 2021-03-22 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 157131 |
| 300378 | 1560 | 2020-01-02 | 2026-06-12 | `db_symbol,date,close,amount,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 169800 |
| 600519 | 5 | 2026-06-10 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 768 |
| 300750 | 5 | 2026-06-10 | 2026-06-16 | `db_symbol,date,close,amount,high,low,turnover,total_market_cap,circulating_market_cap,updated_at,code,exchange` | 763 |

## DB Sync Evidence
- `data/processed/db_sync_summary_all_price.csv`: rows=5195, success=5195, first cache max=2026-04-21, last cache max=2026-06-15.
- `config/db_mapping.json` maps price endpoint to `public.stock_prices` with `company_id`, `trade_date`, `close_price`, `amount`, `high_price`, `low_price`, `turnover`, market-cap fields.

## Key Code Paths
| file | endpoint/source | stock | index | qfq | retry/sleep | cache-first | assessment |
|---|---|---:|---:|---:|---:|---:|---|
| `scripts/diagnose_akshare_fetch_v1_2.py` | `stock_zh_a_hist;index_zh_a_hist;stock_zh_index_daily_tx` | true | true | true | false | false | current_diagnostic_tool |
| `scripts/fetch_formal_data_v1_2.py` | `stock_zh_a_hist;index_zh_a_hist` | true | true | true | true | false | current_formal_fetch_needs_fallbacks |
| `scripts/precache_price.py` | `stock_zh_a_hist via AkShareClient.price_history` | true | false | true | true | true | old_price_precache_runner_reusable_for_cache_first |
| `scripts/smoke_test_data_layer.py` | `database/local` | true | false | true | true | false | current_public_data_layer_partial_reuse |
| `scripts/sync_database_cache.py` | `PostgreSQL public.stock_prices` | true | false | false | false | true | database_cache_path_likely_generated_price_cache |
| `src/aq_factor_lab/data.py` | `stock_zh_a_hist;stock_zh_a_spot_em;stock_cash_flow_sheet_by_report_em;stock_profit_sheet_by_report_em;stock_individual_fund_flow` | true | false | true | true | true | old_akshare_client_reusable_cache_logic |
| `src/aq_factor_lab/data_layer/__init__.py` | `database/local` | true | true | false | true | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/akshare_client.py` | `stock_zh_a_hist;index_zh_a_hist;stock_zh_a_spot_em;stock_board_concept_name_em;stock_board_concept_cons_em` | true | true | true | false | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/cache.py` | `database/local` | false | false | false | false | true | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/config.py` | `database/local` | false | false | false | true | true | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/errors.py` | `database/local` | false | false | false | true | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/normalize.py` | `stock_zh_a_hist;index_zh_a_hist;stock_zh_a_spot_em;stock_board_concept_cons_em` | true | true | false | false | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/quality.py` | `database/local` | false | false | false | false | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/rate_limit.py` | `database/local` | false | false | false | true | false | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/data_layer/service.py` | `database/local` | true | true | true | true | true | current_public_data_layer_partial_reuse |
| `src/aq_factor_lab/db_source.py` | `PostgreSQL public.stock_prices` | true | false | false | false | true | database_cache_path_likely_generated_price_cache |
| `tests/test_data_layer.py` | `stock_zh_a_hist;index_zh_a_hist;stock_zh_a_spot_em;stock_board_concept_name_em;stock_board_concept_cons_em` | true | true | true | true | true | current_public_data_layer_partial_reuse |
| `tests/test_diagnose_akshare_fetch_v1_2.py` | `stock_zh_a_hist;index_zh_a_hist;stock_zh_index_daily_tx` | true | true | true | false | false | current_diagnostic_tool |
| `tests/test_fetch_formal_data_v1_2.py` | `stock_zh_a_hist` | true | false | true | false | false | current_formal_fetch_needs_fallbacks |

## Direct Answers
1. **Most likely generator of `data/cache/price`:** `scripts/sync_database_cache.py` via `src/aq_factor_lab/db_source.py`. The DB sync summary and cache schema match this path. `scripts/precache_price.py` is the likely old AkShare price-only cache runner, but its raw AkShare output schema does not match most current cache files.
2. **Endpoint/source:** current cache source is likely PostgreSQL `public.stock_prices`; old AkShare cache runner used `ak.stock_zh_a_hist(... adjust="qfq", timeout=20)`.
3. **Why slower but more stable:** old AkShare client retries price 5 times, backs off with jitter, throttles each attempt, sleeps between symbols, skips existing cache, and falls back to cache on fetch failure. DB sync is slower due to per-symbol/window queries and atomic CSV validation, but it bypasses current Eastmoney HTTPS failures.
4. **Formal fetch dependency risk:** yes. It depends on `ak.stock_zh_a_hist` against `push2his.eastmoney.com`; latest diagnostics show direct failures for both formerly successful controls and failed names. Benchmark `index_zh_a_hist` also fails.
5. **Fallbacks:** use `stock_zh_index_daily_tx` for benchmarks; use existing `data/cache/price` for stock close/high/low/amount/market-cap; use DB sync/source if credentials are available; spot data can only update latest snapshot, not historical OHLC; old AkShare retry logic helps pacing but cannot fix a broken endpoint by itself.
6. **Recommendation:** add a small fallback adapter. Source stock close/high/low/amount from DB/old cache first, source benchmarks via `stock_zh_index_daily_tx`, and keep `stock_zh_a_hist` only as retryable enrichment for missing qfq/open/volume/pre_close. Do not call the result formal adjusted-return-ready until adjusted price and execution fields are complete.

## Full Inventory
See `reports/akshare_code_inventory_v1_2.csv` for file-level rows and test coverage notes.
