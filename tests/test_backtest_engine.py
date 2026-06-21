from __future__ import annotations

import math
import unittest

import pandas as pd

from aq_factor_lab.backtest_engine import BacktestConfig, MonthlyRebalanceBacktester


def row(
    date: str,
    code: str,
    factor: float | None,
    cap: float | None,
    name: str | None = None,
    amount_20d: float | None = 100_000_000.0,
    amount: float | None = 10_000_000.0,
    high: float | None = 11.0,
    low: float | None = 10.0,
    adjusted_close: float | None = None,
) -> dict[str, object]:
    return {
        "date": pd.Timestamp(date),
        "code": code,
        "name": name or code,
        "cf_yield_neutral": factor,
        "composite_alpha": factor,
        "composite_alpha_ic_weighted": factor,
        "total_market_cap": cap,
        "amount_20d": amount_20d,
        "amount": amount,
        "high": high,
        "low": low,
        "adjusted_close": adjusted_close,
    }


def ranked_buffer_panel(
    *,
    second_month_held_rank: int,
    held_amount_20d: float | None = 100_000_000.0,
    held_amount: float | None = 10_000_000.0,
    held_high: float | None = 11.0,
    held_low: float | None = 10.0,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, held_rank in [
        ("2025-01-31", 1),
        ("2025-02-28", second_month_held_rank),
        ("2025-03-31", second_month_held_rank),
    ]:
        for rank in range(1, 121):
            code = rank_code(rank, held_rank=held_rank)
            rows.append(
                row(
                    date,
                    code,
                    factor=float(1_000 - rank),
                    cap=100.0,
                    amount_20d=held_amount_20d if date == "2025-02-28" and code == "000001" else 100_000_000.0,
                    amount=held_amount if date == "2025-02-28" and code == "000001" else 10_000_000.0,
                    high=held_high if date == "2025-02-28" and code == "000001" else 11.0,
                    low=held_low if date == "2025-02-28" and code == "000001" else 10.0,
                )
            )
    return pd.DataFrame(rows)


def rank_code(rank: int, *, held_rank: int) -> str:
    if rank == held_rank:
        return "000001"
    offset = rank + 1 if rank < held_rank else rank
    return f"{offset:06d}"


class MonthlyRebalanceBacktesterTests(unittest.TestCase):
    def test_default_factor_col_is_ic_weighted_composite_with_rank_buffer(self):
        self.assertEqual(BacktestConfig().factor_col, "composite_alpha_ic_weighted")
        self.assertEqual(BacktestConfig().keep_rank_threshold, 100)

    def test_selects_month_end_top_n_with_stable_code_tie_breaker(self):
        panel = pd.DataFrame(
            [
                row("2025-01-30", "000001", 99.0, 100.0),
                row("2025-01-31", "000002", 0.5, 100.0),
                row("2025-01-31", "000001", 0.5, 100.0),
                row("2025-01-31", "000003", 0.4, 100.0),
                row("2025-02-28", "000001", 0.2, 110.0),
                row("2025-02-28", "000002", 0.1, 90.0),
                row("2025-02-28", "000003", 0.3, 100.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=2)).run(panel)

        first_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-01-31"]
        self.assertEqual(first_holdings["code"].tolist(), ["000001", "000002"])
        self.assertEqual(first_holdings["rank"].tolist(), [1, 2])
        self.assertNotIn("2025-01-30", set(result.holdings["rebalance_date"]))

    def test_default_selection_uses_ic_weighted_composite_alpha(self):
        panel = pd.DataFrame(
            [
                {**row("2025-01-31", "000001", 0.9, 100.0), "composite_alpha_ic_weighted": 0.1},
                {**row("2025-01-31", "000002", 0.1, 100.0), "composite_alpha_ic_weighted": 0.9},
                {**row("2025-02-28", "000001", 0.9, 110.0), "composite_alpha_ic_weighted": 0.1},
                {**row("2025-02-28", "000002", 0.1, 120.0), "composite_alpha_ic_weighted": 0.9},
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        self.assertEqual(result.holdings["code"].tolist(), ["000002"])

    def test_explicit_selection_can_use_cf_yield_neutral(self):
        panel = pd.DataFrame(
            [
                {**row("2025-01-31", "000001", 0.9, 100.0), "composite_alpha_ic_weighted": 0.1},
                {**row("2025-01-31", "000002", 0.1, 100.0), "composite_alpha_ic_weighted": 0.9},
                {**row("2025-02-28", "000001", 0.9, 110.0), "composite_alpha_ic_weighted": 0.1},
                {**row("2025-02-28", "000002", 0.1, 120.0), "composite_alpha_ic_weighted": 0.9},
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(factor_col="cf_yield_neutral", top_n=1, transaction_cost_rate=0.0)
        ).run(panel)

        self.assertEqual(result.holdings["code"].tolist(), ["000001"])

    def test_explicit_selection_can_use_composite_alpha(self):
        panel = pd.DataFrame(
            [
                {**row("2025-01-31", "000001", 0.9, 100.0), "composite_alpha": 0.1},
                {**row("2025-01-31", "000002", 0.1, 100.0), "composite_alpha": 0.9},
                {**row("2025-02-28", "000001", 0.9, 110.0), "composite_alpha": 0.1},
                {**row("2025-02-28", "000002", 0.1, 120.0), "composite_alpha": 0.9},
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(factor_col="composite_alpha", top_n=1, transaction_cost_rate=0.0)
        ).run(panel)

        self.assertEqual(result.holdings["code"].tolist(), ["000002"])

    def test_rank_buffer_retains_previous_holding_ranked_80_and_fills_remaining_slots(self):
        panel = ranked_buffer_panel(second_month_held_rank=80)

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=100)).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertIn("000001", set(second_holdings["code"]))
        self.assertEqual(int(second_holdings.loc[second_holdings["code"] == "000001", "rank"].iloc[0]), 80)
        self.assertEqual(int(second_holdings.shape[0]), 50)
        self.assertNotIn(rank_code(50, held_rank=80), set(second_holdings["code"]))
        for expected_rank in range(1, 50):
            self.assertIn(rank_code(expected_rank, held_rank=80), set(second_holdings["code"]))

    def test_buy_rank_limits_new_entries_and_sell_rank_retains_existing_holdings(self):
        panel = ranked_buffer_panel(second_month_held_rank=4)

        result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=2, buy_rank=2, sell_rank=4, transaction_cost_rate=0.0)
        ).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertIn("000001", set(second_holdings["code"]))
        self.assertEqual(int(second_holdings.loc[second_holdings["code"] == "000001", "rank"].iloc[0]), 4)
        self.assertEqual(int(second_holdings.shape[0]), 2)
        self.assertTrue((second_holdings.loc[second_holdings["code"] != "000001", "rank"] <= 2).all())

    def test_max_turnover_scales_weight_changes_and_keeps_partial_previous_holdings(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0),
                row("2025-01-31", "000002", 0.8, 100.0),
                row("2025-01-31", "000003", 0.1, 100.0),
                row("2025-01-31", "000004", 0.0, 100.0),
                row("2025-02-28", "000001", 0.1, 110.0),
                row("2025-02-28", "000002", 0.0, 110.0),
                row("2025-02-28", "000003", 0.9, 110.0),
                row("2025-02-28", "000004", 0.8, 110.0),
                row("2025-03-31", "000001", 0.1, 121.0),
                row("2025-03-31", "000002", 0.0, 121.0),
                row("2025-03-31", "000003", 0.9, 121.0),
                row("2025-03-31", "000004", 0.8, 121.0),
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=2, buy_rank=2, sell_rank=2, max_turnover=0.5, transaction_cost_rate=0.0)
        ).run(panel)

        second_nav = result.nav[result.nav["rebalance_date"] == "2025-02-28"].iloc[0]
        self.assertAlmostEqual(second_nav["turnover"], 0.5)
        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"].set_index("code")
        self.assertAlmostEqual(second_holdings.loc["000001", "weight"], 0.375)
        self.assertAlmostEqual(second_holdings.loc["000002", "weight"], 0.375)
        self.assertAlmostEqual(second_holdings.loc["000003", "weight"], 0.125)
        self.assertAlmostEqual(second_holdings.loc["000004", "weight"], 0.125)
        self.assertAlmostEqual(second_holdings["weight"].sum(), 1.0)

    def test_min_position_weight_blocks_tiny_new_buys_and_records_cash_weight(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 9.0, 100.0),
                row("2025-01-31", "000002", 8.0, 100.0),
                row("2025-02-28", "000001", 9.0, 110.0),
                row("2025-02-28", "000002", 8.0, 110.0),
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=2, max_turnover=0.001, min_position_weight=0.01, transaction_cost_rate=0.0)
        ).run(panel)

        first_nav = result.nav.iloc[0]
        self.assertAlmostEqual(first_nav["cash_weight"], 1.0)
        self.assertEqual(int(first_nav["selected_count"]), 0)
        self.assertTrue(result.holdings.empty)

    def test_dust_threshold_and_max_positions_clean_tail_positions(self):
        rows: list[dict[str, object]] = []
        for date, leader_offset in [("2025-01-31", 0), ("2025-02-28", 10), ("2025-03-31", 20)]:
            for index in range(1, 21):
                code = f"{index:06d}"
                rank = ((index + leader_offset - 1) % 20) + 1
                rows.append(row(date, code, float(100 - rank), 100.0 + index))
        panel = pd.DataFrame(rows)

        result = MonthlyRebalanceBacktester(
            BacktestConfig(
                top_n=5,
                buy_rank=5,
                sell_rank=5,
                max_turnover=0.5,
                max_positions=5,
                dust_threshold=0.05,
                transaction_cost_rate=0.0,
            )
        ).run(panel)

        self.assertLessEqual(int(result.nav["selected_count"].max()), 5)
        self.assertTrue((result.holdings["weight"] >= 0).all())
        for _date, group in result.holdings.groupby("rebalance_date"):
            self.assertAlmostEqual(float(group["weight"].sum()), 1.0)

    def test_sell_priority_worst_rank_first_removes_worse_rank_when_capping_positions(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 9.0, 100.0),
                row("2025-01-31", "000002", 8.0, 100.0),
                row("2025-01-31", "000003", 7.0, 100.0),
                row("2025-02-28", "000001", 1.0, 110.0),
                row("2025-02-28", "000002", 2.0, 110.0),
                row("2025-02-28", "000003", 9.0, 110.0),
                row("2025-03-31", "000001", 1.0, 121.0),
                row("2025-03-31", "000002", 2.0, 121.0),
                row("2025-03-31", "000003", 9.0, 121.0),
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(
                top_n=3,
                buy_rank=3,
                sell_rank=3,
                max_turnover=0.5,
                max_positions=2,
                sell_priority="worst_rank_first",
                transaction_cost_rate=0.0,
            )
        ).run(panel)

        second_codes = set(result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]["code"])
        self.assertIn("000003", second_codes)
        self.assertIn("000002", second_codes)
        self.assertNotIn("000001", second_codes)

    def test_rank_weighting_and_score_weighting_are_supported(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 3.0, 100.0),
                row("2025-01-31", "000002", 2.0, 100.0),
                row("2025-01-31", "000003", 1.0, 100.0),
                row("2025-02-28", "000001", 3.0, 110.0),
                row("2025-02-28", "000002", 2.0, 110.0),
                row("2025-02-28", "000003", 1.0, 110.0),
            ]
        )

        rank_result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=3, weighting_method="rank_weight", transaction_cost_rate=0.0)
        ).run(panel)
        rank_weights = rank_result.holdings.set_index("code")["weight"]
        self.assertGreater(rank_weights.loc["000001"], rank_weights.loc["000002"])
        self.assertGreater(rank_weights.loc["000002"], rank_weights.loc["000003"])
        self.assertAlmostEqual(rank_weights.sum(), 1.0)

        score_result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=3, weighting_method="score_weight", transaction_cost_rate=0.0)
        ).run(panel)
        score_weights = score_result.holdings.set_index("code")["weight"]
        self.assertGreater(score_weights.loc["000001"], score_weights.loc["000002"])
        self.assertGreater(score_weights.loc["000002"], score_weights.loc["000003"])
        self.assertAlmostEqual(score_weights.sum(), 1.0)

    def test_rank_buffer_drops_previous_holding_ranked_beyond_threshold(self):
        panel = ranked_buffer_panel(second_month_held_rank=120)

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=100)).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertNotIn("000001", set(second_holdings["code"]))
        self.assertEqual(int(second_holdings.shape[0]), 50)

    def test_rank_buffer_does_not_retain_low_liquidity_previous_holding(self):
        panel = ranked_buffer_panel(second_month_held_rank=80, held_amount_20d=49_999_999.0)

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=100)).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertNotIn("000001", set(second_holdings["code"]))

    def test_rank_buffer_forces_hold_zero_amount_previous_holding(self):
        panel = ranked_buffer_panel(second_month_held_rank=80, held_amount=0.0)

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=100)).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertIn("000001", set(second_holdings["code"]))
        second_nav = result.nav[result.nav["rebalance_date"] == "2025-02-28"].iloc[0]
        self.assertEqual(int(second_nav["blocked_sell_count"]), 1)

    def test_rank_buffer_forces_hold_one_price_locked_previous_holding(self):
        panel = ranked_buffer_panel(second_month_held_rank=80, held_high=10.0, held_low=10.0)

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=100)).run(panel)

        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"]
        self.assertIn("000001", set(second_holdings["code"]))
        second_nav = result.nav[result.nav["rebalance_date"] == "2025-02-28"].iloc[0]
        self.assertEqual(int(second_nav["blocked_sell_count"]), 1)

    def test_keep_rank_threshold_cannot_be_less_than_top_n(self):
        with self.assertRaisesRegex(ValueError, "keep_rank_threshold must be greater than or equal to top_n"):
            MonthlyRebalanceBacktester(BacktestConfig(top_n=50, keep_rank_threshold=49))

    def test_equal_weights_use_actual_selected_count_when_less_than_top_n(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.3, 100.0),
                row("2025-01-31", "000002", None, 100.0),
                row("2025-01-31", "000003", 0.1, 100.0),
                row("2025-02-28", "000001", 0.2, 110.0),
                row("2025-02-28", "000003", 0.1, 110.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=50)).run(panel)

        weights = result.holdings["weight"]
        self.assertEqual(len(weights), 2)
        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertTrue((weights == 0.5).all())
        self.assertEqual(int(result.nav.loc[0, "selected_count"]), 2)
        self.assertIn("selected_count_below_top_n", set(result.warnings["warning_type"]))

    def test_turnover_and_transaction_cost_cover_initial_unchanged_and_partial_rebalance(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.5, 100.0),
                row("2025-01-31", "000002", 0.4, 100.0),
                row("2025-01-31", "000003", 0.3, 100.0),
                row("2025-02-28", "000001", 0.5, 110.0),
                row("2025-02-28", "000002", 0.4, 90.0),
                row("2025-02-28", "000003", 0.1, 100.0),
                row("2025-03-31", "000001", 0.5, 121.0),
                row("2025-03-31", "000002", 0.1, 99.0),
                row("2025-03-31", "000003", 0.4, 120.0),
                row("2025-04-30", "000001", 0.5, 121.0),
                row("2025-04-30", "000002", 0.1, 99.0),
                row("2025-04-30", "000003", 0.4, 120.0),
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=2, keep_rank_threshold=2, transaction_cost_rate=0.002)
        ).run(panel)

        nav = result.nav
        self.assertAlmostEqual(nav.loc[0, "turnover"], 1.0)
        self.assertAlmostEqual(nav.loc[0, "transaction_cost"], 0.002)
        self.assertAlmostEqual(nav.loc[1, "turnover"], 0.0)
        self.assertAlmostEqual(nav.loc[1, "transaction_cost"], 0.0)
        self.assertAlmostEqual(nav.loc[2, "turnover"], 1.0)
        self.assertAlmostEqual(nav.loc[2, "transaction_cost"], 0.002)

        trades = result.trades[result.trades["rebalance_date"] == "2025-03-31"].set_index("code")
        self.assertAlmostEqual(trades.loc["000002", "weight_change"], -0.5)
        self.assertAlmostEqual(trades.loc["000003", "weight_change"], 0.5)
        self.assertAlmostEqual(trades["transaction_cost_contribution"].sum(), 0.002)

    def test_period_returns_prefer_adjusted_close_when_available(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0, adjusted_close=10.0),
                row("2025-01-31", "000002", 0.1, 100.0, adjusted_close=20.0),
                row("2025-02-28", "000001", 0.9, 200.0, adjusted_close=11.0),
                row("2025-02-28", "000002", 0.1, 100.0, adjusted_close=22.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        nav = result.nav.iloc[0]
        self.assertAlmostEqual(nav["gross_return"], 0.1)
        self.assertEqual(nav["return_source"], "adjusted_close_month_end")

    def test_blocked_sell_is_forced_hold_and_records_sell_side_diagnostics(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0),
                row("2025-01-31", "000002", 0.8, 100.0),
                row("2025-01-31", "000003", 0.1, 100.0),
                row("2025-02-28", "000001", 0.1, 110.0, amount=0.0),
                row("2025-02-28", "000002", 0.2, 110.0),
                row("2025-02-28", "000003", 0.9, 110.0),
                row("2025-03-31", "000001", 0.1, 121.0),
                row("2025-03-31", "000002", 0.2, 121.0),
                row("2025-03-31", "000003", 0.9, 121.0),
            ]
        )

        result = MonthlyRebalanceBacktester(
            BacktestConfig(top_n=2, buy_rank=2, sell_rank=2, transaction_cost_rate=0.0)
        ).run(panel)

        second_nav = result.nav[result.nav["rebalance_date"] == "2025-02-28"].iloc[0]
        second_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-02-28"].set_index("code")
        self.assertIn("000001", set(second_holdings.index))
        self.assertAlmostEqual(second_holdings.loc["000001", "weight"], 0.5)
        self.assertEqual(int(second_nav["attempted_sell_count"]), 1)
        self.assertEqual(int(second_nav["blocked_sell_count"]), 1)
        self.assertEqual(int(second_nav["forced_hold_count"]), 1)
        self.assertAlmostEqual(second_nav["blocked_sell_weight"], 0.5)
        self.assertAlmostEqual(second_nav["forced_hold_weight"], 0.5)

    def test_nav_uses_gross_return_minus_transaction_cost(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.5, 100.0),
                row("2025-01-31", "000002", 0.4, 100.0),
                row("2025-02-28", "000001", 0.3, 110.0),
                row("2025-02-28", "000002", 0.2, 90.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=2, transaction_cost_rate=0.002)).run(panel)

        self.assertAlmostEqual(result.nav.loc[0, "gross_return"], 0.0)
        self.assertAlmostEqual(result.nav.loc[0, "net_return"], -0.002)
        self.assertAlmostEqual(result.nav.loc[0, "nav"], 0.998)

    def test_benchmark_uses_tradable_universe_not_only_selected_or_non_null_factor(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0),
                row("2025-01-31", "000002", 0.1, 100.0),
                row("2025-01-31", "000003", None, 100.0),
                row("2025-01-31", "000004", 0.8, 100.0),
                row("2025-02-28", "000001", 0.9, 110.0),
                row("2025-02-28", "000002", 0.1, 120.0),
                row("2025-02-28", "000003", None, 90.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        nav = result.nav.loc[0]
        self.assertEqual(int(nav["selected_count"]), 1)
        self.assertEqual(int(nav["benchmark_count"]), 3)
        self.assertAlmostEqual(nav["benchmark_return"], (0.1 + 0.2 - 0.1) / 3)
        self.assertAlmostEqual(nav["benchmark_nav"], 1.0 + (0.1 + 0.2 - 0.1) / 3)
        self.assertAlmostEqual(nav["excess_return"], nav["net_return"] - nav["benchmark_return"])
        self.assertAlmostEqual(nav["excess_nav"], 1.0 + nav["excess_return"])

    def test_benchmark_excludes_low_and_missing_amount_20d(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0, amount_20d=100_000_000.0),
                row("2025-01-31", "000002", 0.8, 100.0, amount_20d=49_999_999.0),
                row("2025-01-31", "000003", 0.7, 100.0, amount_20d=None),
                row("2025-01-31", "000004", 0.6, 100.0, amount_20d=80_000_000.0),
                row("2025-02-28", "000001", 0.9, 110.0),
                row("2025-02-28", "000002", 0.8, 120.0),
                row("2025-02-28", "000003", 0.7, 90.0),
                row("2025-02-28", "000004", 0.6, 105.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=2, transaction_cost_rate=0.0)).run(panel)

        first_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-01-31"]
        self.assertEqual(first_holdings["code"].tolist(), ["000001", "000004"])
        nav = result.nav.loc[0]
        self.assertEqual(int(nav["liquidity_filtered_count"]), 2)
        self.assertEqual(int(nav["untradable_filtered_count"]), 0)
        self.assertEqual(int(nav["buyable_count"]), 2)
        self.assertEqual(int(nav["benchmark_count"]), 2)
        self.assertAlmostEqual(nav["benchmark_return"], (0.1 + 0.05) / 2)
        metrics = result.metrics.set_index("metric")
        self.assertAlmostEqual(metrics.loc["average_liquidity_filtered_count", "value"], 2.0)
        self.assertAlmostEqual(metrics.loc["average_untradable_filtered_count", "value"], 0.0)

    def test_benchmark_excludes_no_volume_limit_locked_and_missing_fields(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0, amount=0.0),
                row("2025-01-31", "000002", 0.8, 100.0, high=10.0, low=10.0),
                row("2025-01-31", "000003", 0.7, 100.0, high=None),
                row("2025-01-31", "000004", 0.6, 100.0),
                row("2025-02-28", "000001", 0.9, 110.0),
                row("2025-02-28", "000002", 0.8, 120.0),
                row("2025-02-28", "000003", 0.7, 90.0),
                row("2025-02-28", "000004", 0.6, 105.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=2, transaction_cost_rate=0.0)).run(panel)

        first_holdings = result.holdings[result.holdings["rebalance_date"] == "2025-01-31"]
        self.assertEqual(first_holdings["code"].tolist(), ["000004"])
        self.assertAlmostEqual(first_holdings["weight"].iloc[0], 1.0)
        nav = result.nav.loc[0]
        self.assertEqual(int(nav["liquidity_filtered_count"]), 0)
        self.assertEqual(int(nav["untradable_filtered_count"]), 3)
        self.assertEqual(int(nav["buyable_count"]), 1)
        self.assertEqual(int(nav["benchmark_count"]), 1)
        self.assertAlmostEqual(nav["benchmark_return"], 0.05)

    def test_empty_buyable_cross_section_records_warning_and_keeps_benchmark_path(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0, amount_20d=1.0),
                row("2025-01-31", "000002", 0.8, 100.0, amount=0.0),
                row("2025-02-28", "000001", 0.9, 110.0),
                row("2025-02-28", "000002", 0.8, 120.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        self.assertTrue(result.holdings.empty)
        nav = result.nav.loc[0]
        self.assertEqual(int(nav["selected_count"]), 0)
        self.assertEqual(int(nav["buyable_count"]), 0)
        self.assertEqual(int(nav["benchmark_count"]), 0)
        self.assertTrue(pd.isna(nav["benchmark_return"]))
        self.assertTrue(pd.isna(nav["excess_return"]))
        warnings = set(result.warnings["warning_type"])
        self.assertIn("empty_buyable_cross_section", warnings)
        self.assertIn("missing_benchmark_return", warnings)
        self.assertIn("selected_count_below_top_n", warnings)

    def test_excess_nav_chains_monthly_excess_returns_and_metrics_use_excess_nav(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 100.0),
                row("2025-01-31", "000002", 0.1, 100.0),
                row("2025-02-28", "000001", 0.9, 120.0),
                row("2025-02-28", "000002", 0.1, 110.0),
                row("2025-03-31", "000001", 0.1, 108.0),
                row("2025-03-31", "000002", 0.9, 110.0),
                row("2025-04-30", "000001", 0.1, 118.8),
                row("2025-04-30", "000002", 0.9, 121.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        nav = result.nav
        expected_excess_returns = [0.05, -0.05, 0.0]
        expected_excess_nav = [1.05, 0.9975, 0.9975]
        for actual, expected in zip(nav["excess_return"], expected_excess_returns, strict=True):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(nav["excess_nav"], expected_excess_nav, strict=True):
            self.assertAlmostEqual(actual, expected)

        metrics = result.metrics.set_index("metric")
        self.assertAlmostEqual(
            metrics.loc["annualized_excess_return", "value"],
            (expected_excess_nav[-1] / 1.0) ** (12 / 3) - 1.0,
        )
        self.assertAlmostEqual(metrics.loc["excess_max_drawdown", "value"], -0.05)
        self.assertAlmostEqual(metrics.loc["information_ratio", "value"], 0.0)

    def test_missing_benchmark_keeps_relative_nav_flat_and_records_warning(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.9, 0.0),
                row("2025-01-31", "000002", 0.1, None),
                row("2025-02-28", "000001", 0.9, 110.0),
                row("2025-02-28", "000002", 0.1, 120.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        nav = result.nav.loc[0]
        self.assertEqual(int(nav["benchmark_count"]), 0)
        self.assertTrue(pd.isna(nav["benchmark_return"]))
        self.assertTrue(pd.isna(nav["excess_return"]))
        self.assertAlmostEqual(nav["benchmark_nav"], 1.0)
        self.assertAlmostEqual(nav["excess_nav"], 1.0)
        self.assertIn("missing_benchmark_return", set(result.warnings["warning_type"]))

    def test_metrics_use_monthly_net_returns_nav_drawdown_and_turnover(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.5, 100.0),
                row("2025-02-28", "000001", 0.5, 110.0),
                row("2025-03-31", "000001", 0.5, 99.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        metrics = result.metrics.set_index("metric")["value"]
        self.assertAlmostEqual(metrics.loc["annualized_return"], (0.99 / 1.0) ** (12 / 2) - 1)
        self.assertAlmostEqual(metrics.loc["max_drawdown"], -0.1)
        self.assertAlmostEqual(metrics.loc["annualized_turnover"], 6.0)
        self.assertTrue(math.isfinite(metrics.loc["sharpe_ratio"]))

    def test_sharpe_returns_nan_when_monthly_returns_have_zero_std(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", 0.5, 100.0),
                row("2025-02-28", "000001", 0.5, 100.0),
                row("2025-03-31", "000001", 0.5, 100.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=1, transaction_cost_rate=0.0)).run(panel)

        metrics = result.metrics.set_index("metric")
        self.assertTrue(pd.isna(metrics.loc["sharpe_ratio", "value"]))
        self.assertIn("zero_std", str(metrics.loc["sharpe_ratio", "note"]))
        self.assertTrue(pd.isna(metrics.loc["information_ratio", "value"]))
        self.assertIn("zero_std", str(metrics.loc["information_ratio", "note"]))

    def test_missing_factor_and_missing_period_return_are_recorded(self):
        panel = pd.DataFrame(
            [
                row("2025-01-31", "000001", None, 100.0),
                row("2025-01-31", "000002", None, 100.0),
                row("2025-02-28", "000001", 0.5, 100.0),
                row("2025-02-28", "000002", 0.4, 100.0),
                row("2025-03-31", "000001", 0.5, 110.0),
            ]
        )

        result = MonthlyRebalanceBacktester(BacktestConfig(top_n=2)).run(panel)

        warnings = set(result.warnings["warning_type"])
        self.assertIn("empty_factor_cross_section", warnings)
        self.assertIn("missing_period_return", warnings)
        missing = result.holdings[result.holdings["code"] == "000002"]
        self.assertTrue(pd.isna(missing["period_return"].iloc[0]))


if __name__ == "__main__":
    unittest.main()
