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
- return_source=total_market_cap_month_end
- benchmark=tradable_universe_equal_weight
- benchmark_liquidity_filter=amount_20d>=50000000
- benchmark_tradability_filter=amount>0_and_high_ne_low
- benchmark_return_source=total_market_cap_month_end
- periods=61
- start_date=2021-03-31
- end_date=2026-04-30
- ending_nav=1.402545695
- ending_benchmark_nav=1.635298258
- ending_excess_nav=0.7589824003
- annualized_return=0.06881295386
- max_drawdown=-0.1975803756
- sharpe_ratio=0.464453404
- annualized_turnover=14.39357902
- annualized_excess_return=-0.05366186571
- excess_max_drawdown=-0.2457550621
- information_ratio=-0.2609310977

## QA

- average_selected_count=49.27868852
- min_selected_count=0
- max_selected_count=51
- average_benchmark_count=3261.360656
- min_benchmark_count=0
- max_benchmark_count=4686
- average_liquidity_filtered_count=1239.229508
- average_untradable_filtered_count=67.16393443
- average_buyable_count=3251.540984
- min_buyable_count=0
- max_buyable_count=4683
- average_monthly_benchmark_return=0.01040805669
- average_monthly_excess_return=-0.003518528852
- benchmark_missing_periods=1
- valid_excess_periods=60
- average_monthly_turnover=1.199464918
- average_trade_count=64.24590164
- average_attempted_sell_count=29.68852459
- average_blocked_sell_count=0.09836065574
- average_forced_hold_weight=0.001960655738
- total_transaction_cost=0.14633472
- average_transaction_cost=0.002398929836
- selected_count_below_top_n=1
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

- empty_buyable_cross_section=1
- empty_factor_cross_section=14
- missing_benchmark_return=15
- selected_count_below_top_n=1