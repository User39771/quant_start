# External Data Integration Plan

- assessment_date=2026-06-18
- scope=design_only
- vendor_integration=not_implemented
- secrets_policy=no_api_keys_or_passwords_in_docs_or_logs

## Objective

Future external data should repair the data substrate before any new strategy work resumes. The project should not couple factor or backtest logic directly to a vendor. Every source must first be converted into internal standard contracts.

Acceptable upstream formats:

- PostgreSQL tables
- CSV files
- Parquet files
- API responses

Required downstream rule:

- Factor generation and backtesting consume only internal standardized fields.
- No vendor-specific field names, credentials, request logic, or response quirks should leak into `factors.py` or `backtest_engine.py`.

## Contract 1: Adjusted Price

Minimum internal fields:

- `code`
- `date`
- `close`
- `adjusted_close`
- `adj_factor`
- `return_source`

Semantics:

- `date` is the trading date.
- `adjusted_close` must be usable for shareholder return calculation.
- If only `adj_factor` is provided, `adjusted_close = close * adj_factor` may be constructed after validating alignment by `code` and `date`.
- All rolling or future-return operations must be grouped by `code`.
- `return_source` should identify whether returns use `adjusted_close`, `close_times_adj_factor`, or a fallback proxy.

Validation:

- Coverage by date and code.
- Non-null adjusted values over the research window.
- No cross-stock rolling or shift contamination.
- Sanity checks around corporate-action dates.

## Contract 2: Point-In-Time Universe

Minimum internal fields:

- `code`
- `date`
- `is_listed_asof`
- `list_date`
- `delist_date`
- `listing_status`

Semantics:

- A stock is eligible on date `t` only if `list_date <= t`.
- If `delist_date` exists, eligibility requires `t < delist_date`.
- Delisted historical stocks must remain available for dates when they were listed.
- Future IPOs must never appear in earlier historical universes.

Validation:

- Monthly eligible-universe count.
- IPO-filtered count.
- Delist-filtered count.
- Historical delisted-symbol count.

## Contract 3: Trading Status

Minimum internal fields:

- `code`
- `date`
- `amount`
- `volume`
- `is_suspended`
- `trading_status`
- `limit_up`
- `limit_down`
- `is_st`
- `is_star_st`

Semantics:

- Only same-day status fields may decide whether a rebalance-date buy or sell can execute.
- Buy constraints and sell constraints must be modeled separately.
- If a sell cannot execute, the position becomes a forced hold and contributes to forced-hold diagnostics.
- If a buy cannot execute or the portfolio cannot be fully reallocated, cash weight must be recorded.

Validation:

- Zero amount / zero volume day counts.
- Blocked sell count and blocked sell weight.
- Forced hold count and forced hold weight.
- Cash weight after failed execution.

## Integration Steps

1. Add a source adapter that reads the external data without exposing secrets in code, docs, or logs.
2. Write a deterministic conversion job into internal standard cache files.
3. Add coverage QA outputs before any factor or backtest run uses the new data.
4. Rerun the existing full pipeline unchanged:
   - factor panel generation
   - IC / Rank IC diagnostics
   - group returns
   - monthly backtest
   - portfolio experiments
   - walk-forward validation
5. Compare results against the previous `total_market_cap_month_end` proxy run.

## Non-Goals

- Do not add a new data vendor inside this planning document.
- Do not store API keys, database passwords, account names, or tokens in documentation.
- Do not use new data to expand factor count before strict returns and point-in-time universe are fixed.
- Do not claim a strategy is validated from full-sample parameter selection.
