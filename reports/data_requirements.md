# Data Requirements

- assessment_date=2026-06-18
- purpose=minimum_data_needed_for_tradable_a_share_backtesting
- status=data_gap_inventory

## Summary

The current research framework is blocked by missing or unusable realism data. The required fields below should be converted into stable internal project contracts before entering factor generation or backtesting. Data may come from PostgreSQL, CSV, Parquet, or an API, but downstream modules should consume the same standardized fields.

## P0: Adjusted Price

Required fields:

- `code`
- `date`
- `qfq_close` or `hfq_close` or `adjusted_close`
- `adj_factor`
- raw `close`

Uses:

- Strict realized returns.
- Future-return labels for IC / Rank IC.
- Portfolio NAV and benchmark returns.

Missing-data risk:

- `total_market_cap` return proxy can be distorted by corporate actions, share-count changes, and vendor methodology.
- IC and backtest performance may not reflect tradable shareholder returns.

Current status:

- `stock_prices_history.adj_factor` exists in schema.
- Sample audit shows `adj_factor_non_null=0`.
- Current official return source remains `total_market_cap_month_end`.

Priority: P0.

## P0: Stock Lifecycle And Historical Universe

Required fields:

- `code`
- `list_date`
- `delist_date`
- `listing_status`
- delisted historical symbols
- historical symbol / name changes if applicable

Uses:

- Point-in-time universe construction.
- IPO filtering.
- Delisting handling.
- Avoiding current-universe survivorship bias.

Missing-data risk:

- Backtests may include future IPOs in past periods or omit historical delisted stocks.
- Results may be biased optimistic and not comparable to live deployment.

Current status:

- No usable `list_date` found.
- No usable `delist_date` found.
- Current `is_active` style fields are not a substitute for historical membership.

Priority: P0.

## P1: Trading Status

Required fields:

- `code`
- `date`
- suspension flag
- `trading_status`
- `limit_up`
- `limit_down`
- ST / `*ST` flag
- `volume`
- `amount`

Uses:

- Buy-side tradability filters.
- Sell-side forced-hold constraints.
- Limit-up / limit-down execution modeling.
- Turnover and transaction-cost realism.

Missing-data risk:

- Backtest may assume impossible buys or sells.
- Alpha may be overstated if blocked exits or locked-limit days are ignored.
- Results may also be overly conservative if coarse proxies such as `high == low` over-filter tradable days.

Current status:

- Same-day `amount` and price fields are available.
- Explicit limit-price fields were not confirmed in the active mapped price table.
- Minimal sell-side constraint is implemented, but complete execution realism is still incomplete.

Priority: P1.

## P1: Corporate Actions

Required fields:

- `code`
- ex-date / announcement date if available
- dividend
- split
- bonus share
- rights issue
- share capital changes

Uses:

- Adjusted-price validation.
- Explaining market-cap return distortions.
- Reconciling share-count and corporate-action jumps.

Missing-data risk:

- Adjustment factors cannot be audited independently.
- Market-cap proxy returns may reflect share issuance or capital changes rather than shareholder return.

Current status:

- Some dividend-related fields exist in schema.
- Full corporate-action reconstruction has not been connected to the official return series.

Priority: P1.

## P2: Historical Industry

Required fields:

- `code`
- industry code
- industry name
- industry effective date
- `in_date`
- `out_date`

Uses:

- Point-in-time Shenwan industry classification.
- Industry neutralization.
- Avoiding future industry membership backfill.

Missing-data risk:

- Industry dummies may use future classification if as-of dates are incomplete.
- Neutralized factors may retain hidden industry exposure.

Current status:

- `map_company_industry_sw.in_date` and `out_date` exist.
- Industry as-of handling should remain part of all future runs.

Priority: P2.

## Required Process

Before future strategy work resumes:

1. Populate P0 adjusted price and lifecycle data.
2. Convert every source into internal standard fields.
3. Rerun existing factor diagnostics, backtests, portfolio experiments, and walk-forward validation without changing strategy logic.
4. Only after the same pipeline is rerun on credible data should factor or portfolio logic be revisited.
