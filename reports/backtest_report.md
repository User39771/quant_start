# Monthly Rebalanced Backtest Report

- strategy=monthly_rebalanced_top50_equal_weight
- factor=composite_alpha_ic_weighted
- rebalance_frequency=monthly
- top_n=50
- buy_rank=50
- sell_rank=100
- keep_rank_threshold=100
- max_turnover=None
- weighting=equal_weight
- transaction_cost_rate=0.002
- liquidity_filter=amount_20d>=50000000
- tradability_filter=amount>0_and_high_ne_low
- buy_side_constraints=enabled
- return_source=unknown
- benchmark=tradable_universe_equal_weight
- benchmark_liquidity_filter=amount_20d>=50000000
- benchmark_tradability_filter=amount>0_and_high_ne_low
- benchmark_return_source=unknown
- periods=0
- start_date=
- end_date=
- ending_nav=
- ending_benchmark_nav=
- ending_excess_nav=
- annualized_return=NaN
- max_drawdown=NaN
- sharpe_ratio=NaN
- annualized_turnover=NaN
- annualized_excess_return=NaN
- excess_max_drawdown=NaN
- information_ratio=NaN

## QA

- average_selected_count=NaN
- min_selected_count=NaN
- max_selected_count=NaN
- average_benchmark_count=NaN
- min_benchmark_count=NaN
- max_benchmark_count=NaN
- average_liquidity_filtered_count=NaN
- average_untradable_filtered_count=NaN
- average_buyable_count=NaN
- min_buyable_count=NaN
- max_buyable_count=NaN
- average_monthly_benchmark_return=NaN
- average_monthly_excess_return=NaN
- benchmark_missing_periods=0
- valid_excess_periods=0
- average_monthly_turnover=NaN
- average_trade_count=NaN
- average_attempted_sell_count=NaN
- average_blocked_sell_count=NaN
- average_forced_hold_weight=NaN
- total_transaction_cost=NaN
- average_transaction_cost=NaN
- selected_count_below_top_n=0
- missing_period_return=0

## Method

- Rebalance dates are the last available trading date in each calendar month.
- Holdings are selected using the current rebalance-date factor cross-section only.
- Rank Buffer retains previous holdings that remain buyable and rank within sell_rank.
- Rank Buffer retains previous holdings that remain buyable and rank within keep_rank_threshold.
- Rank Buffer retains previous holdings that remain buyable and rank within keep_rank_threshold when sell_rank is not explicitly set.
- New buys are restricted to buy_rank or better; remaining seats are filled from eligible non-retained stocks by current rank.
- max_turnover, when set, scales desired weight changes toward the target portfolio and leaves residual cash if initial deployment is capped.
- weighting_method controls target weights after selection: equal_weight, rank_weight, or score_weight.
- Monthly return covers the holding period from the rebalance date to the next rebalance date.
- Turnover is sum(abs(target_weight - previous_weight)); first entry turnover is 1.0.
- Transaction cost is turnover * transaction_cost_rate; no additional factor of 2 is applied.
- transaction_cost_rate is a one-way rate per traded notional; a full replacement has turnover=2.0 and costs 2 * transaction_cost_rate.
- amount_20d is the trailing 20-trading-day mean of raw CNY amount.
- Buy-side liquidity filter removes stocks with amount_20d < 50,000,000 or missing amount_20d.
- Buy-side tradability filter removes stocks with amount == 0, high == low, or missing tradability fields.
- Sell-side execution model blocks same-day exits when amount == 0, volume == 0, high == low, or available halt/status flags indicate suspension.
- Blocked sells are forced holds; forced_hold_weight records the retained previous weight.
- Benchmark applies the same rebalance-date liquidity and tradability filters as strategy buys.
- Current phase still does not fully model explicit limit-down exit prices when limit_down data is unavailable.
- Benchmark is each month tradable high-liquidity valid-stock equal-weight average period return.
- Benchmark does not deduct transaction costs.
- Excess return = strategy net return - benchmark return.
- Excess NAV is compounded from monthly excess_return, not nav minus benchmark_nav.
- IR = mean(excess_return) / std(excess_return) * sqrt(12).

## Warnings

- empty_factor_panel=1