# Methodology Assessment

- assessment_date=2026-06-18
- project_status=research_framework_sealed
- strategy_validity=not_validated
- recommended_next_step=data_substrate_remediation

## Completed Work

The project has built a usable A-share quantitative research framework around the existing database and local cache workflow:

- PostgreSQL read-only synchronization into local cache files.
- Cache-only research execution for repeatable local studies.
- Financial statement handling with TTM-style cash-flow construction and announcement-date availability controls.
- Factor preprocessing with MAD winsorization, z-score standardization, and market-cap / Shenwan-industry neutralization.
- Factor diagnostics including IC, Rank IC, group returns, cross-factor correlation, and coverage reporting.
- Monthly rebalanced long-only backtest with transaction costs, tradable benchmark, liquidity filters, and tradability filters.
- Portfolio construction experiments covering larger holding counts, rank buffers, turnover caps, dust controls, and max-position controls.
- Walk-forward validation that selects parameters on training windows and evaluates only on subsequent test windows.
- Data realism audit for adjusted returns, point-in-time universe inputs, trading-status fields, and market-cap / industry as-of risks.
- Minimal sell-side execution constraints for same-day no-trade or locked-price forced holds.

## Why The Current Strategy Cannot Be Claimed Effective

The current strategy is not validated as a tradable alpha strategy.

Key reasons:

- Walk-forward out-of-sample validation failed:
  - overall sample-out annualized excess return: `-0.06377747765`
  - overall sample-out average information ratio: `-0.5181605268`
  - selected parameters were unstable across splits.
- The best in-sample portfolio construction variants still produced negative excess return after costs.
- Strict adjusted-price returns are unavailable in the current usable cache:
  - `stock_prices_history.adj_factor` exists in schema, but sample `adj_factor_non_null=0`.
  - current official backtest still uses `total_market_cap_month_end` as the return proxy.
- Historical point-in-time universe cannot be reconstructed from available data:
  - no usable `list_date`
  - no usable `delist_date`
  - current active-status fields do not recover historical delisted names.
- The `total_market_cap` return proxy is not a formal adjusted return series and can be distorted by share-capital changes, corporate actions, and data vendor methodology.

Because of these issues, continuing to tune portfolio parameters would mostly optimize against a weak data substrate and in-sample noise.

## Valuable Conclusions

The work still produced useful engineering and research conclusions:

- The factor layer shows non-zero cross-sectional ranking signal in diagnostics, especially before converting the score into a high-turnover concentrated portfolio.
- Rank buffer, turnover cap, dust threshold, and max-position controls reduce implementation drag and make holdings more interpretable.
- The minimal sell-side forced-hold model has a small measured impact in the latest run:
  - average attempted sells per month: `29.68852459`
  - average blocked sells per month: `0.09836065574`
  - average forced hold weight: `0.001960655738`
- The main blocker is not another round of factor stacking or portfolio parameter search. The main blocker is missing data realism:
  - strict adjusted returns
  - point-in-time universe / delisting history
  - richer trading status and limit-price fields

## Recommendation

Recommended project posture:

- Pause portfolio-layer parameter tuning.
- Pause adding new raw factors.
- Prioritize sourcing and integrating:
  - adjusted prices or non-null adjustment factors covering the full research period
  - list / delist history and historical symbols
  - suspension, trading-status, limit-up / limit-down, and ST flags
- After the data substrate is fixed, rerun the same research pipeline before changing strategy logic.
- If the required data cannot be obtained, treat this project as a research framework and learning system, not a deployable trading strategy.

## Final Assessment

The framework is valuable and reusable. The current strategy is not validated. The next defensible milestone is data-source completion, not further in-sample optimization.
