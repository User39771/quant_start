"""Synthetic checks only: no research inputs or network are needed."""

import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import run_h6_daily_amount_abnormal_activity_v1 as h6


class H6Tests(unittest.TestCase):
    def test_exact_window_includes_formation(self):
        dates = pd.bdate_range("2020-01-01", periods=100)
        window = h6.exact_window(dates, dates[70])
        self.assertEqual(len(window), 50)
        self.assertEqual(window[0], dates[21])
        self.assertEqual(window[-1], dates[70])

    def test_insufficient_calendar_rejected(self):
        dates = pd.bdate_range("2020-01-01", periods=50)
        with self.assertRaises(ValueError):
            h6.exact_window(dates, dates[48])

    def test_missing_does_not_substitute(self):
        values = np.arange(50.0, dtype=float)[None, :]
        values[0, 12] = np.nan
        self.assertFalse(h6.midrank_rows(values).valid_50d.iloc[0])
        with self.assertRaises(ValueError):
            h6.midrank_rows(np.ones((1, 49)))

    def test_zero_preserved_flagged(self):
        result = h6.midrank_rows(np.zeros((1, 50))).iloc[0]
        self.assertTrue(result.valid_50d)
        self.assertTrue(result.amount_zero_flag)
        self.assertEqual(result.amount_zero_days, 50)
        self.assertEqual(result.midrank, 25.5)
        self.assertEqual(result.shock_state, "NORMAL")

    def test_nonfinite_negative_invalid(self):
        for bad in (np.nan, np.inf, -1):
            values = np.ones((1, 50))
            values[0, 0] = bad
            self.assertFalse(h6.midrank_rows(values).valid_50d.iloc[0])

    def test_midrank_ties_no_date_tiebreak(self):
        values = np.r_[np.arange(40), np.repeat(100.0, 10)]
        result = h6.midrank_rows(values[None]).iloc[0]
        self.assertEqual(result.midrank, 45.5)
        self.assertEqual(result.shock_state, "NORMAL")
        self.assertEqual(result.own_history_percentile, 0.9)
        reordered = np.r_[values[:-1][::-1], values[-1]]
        self.assertEqual(h6.midrank_rows(reordered[None]).midrank.iloc[0], result.midrank)

    def test_rank_boundaries(self):
        for rank, state in (
            (1, "LOW_SHOCK"),
            (5, "LOW_SHOCK"),
            (6, "NORMAL"),
            (45, "NORMAL"),
            (46, "HIGH_SHOCK"),
            (50, "HIGH_SHOCK"),
        ):
            values = list(range(1, 51))
            values.remove(rank)
            values.append(rank)
            self.assertEqual(h6.midrank_rows(np.array([values])).shock_state.iloc[0], state)

    def test_trend_and_constant(self):
        values = np.array([np.arange(50), np.arange(50)[::-1], np.ones(50)])
        result = h6.trend_rows(values)
        np.testing.assert_allclose(result[:2], [1, -1])
        self.assertTrue(np.isnan(result[2]))

    def test_primary_periods(self):
        self.assertEqual(h6.PERIODS, tuple(range(3, 57)))
        self.assertEqual(len(h6.PERIODS), 54)
        self.assertFalse(any(p in h6.PERIODS for p in (0, 1, 2)))

    def test_start_and_horizon_offsets(self):
        dates = pd.bdate_range("2020-01-01", periods=100)
        start, ends = h6.outcome_dates(dates, dates[60])
        self.assertEqual(start, dates[61])
        self.assertEqual(ends, {5: dates[66], 10: dates[71], 20: dates[81]})

    def test_middle40_and_51_closes(self):
        daily = np.linspace(-0.02, 0.02, 50)
        for target, expected in ((10, False), (15, True), (34, True), (40, False)):
            ordered = np.r_[np.delete(daily, target), daily[target]]
            prices = np.r_[1.0, np.cumprod(1 + ordered)][None]
            self.assertEqual(h6.normal_formation(prices).normal_formation_return.iloc[0], expected)
        with self.assertRaises(ValueError):
            h6.normal_formation(np.ones((1, 50)))

    def test_middle40_missing_history_invalid(self):
        prices = np.ones((1, 51))
        prices[0, 10] = np.nan
        self.assertFalse(h6.normal_formation(prices).normal_formation_return.iloc[0])

    def test_market_participants_threshold_and_zero(self):
        amount = np.ones((10, 5))
        amount[:2, 0] = np.nan
        amount[:3, 1] = np.nan
        amount[0, 2] = 0
        total, count, median, usable = h6.market_denominators(amount, np.arange(5))
        self.assertEqual(median, 10)
        self.assertEqual(count[2], 10)
        self.assertTrue(usable[0])
        self.assertFalse(usable[1])
        self.assertEqual(total[2], 9)

    def toy_cells(self, count=25, valid=20):
        states = pd.DataFrame(
            {
                "period_index": 3,
                "stock_code": [f"{i:06d}" for i in range(count)],
                "RETURN_STATE": "LOW_RETURN",
                "shock_state": "HIGH_SHOCK",
                "primary_period": True,
                "valid_50d": True,
            }
        )
        outcomes = states[["period_index", "stock_code"]].assign(
            horizon=20,
            future_return=[0.1] * valid + [np.nan] * (count - valid),
            return_start_date=pd.Timestamp("2021-01-01"),
            endpoint_date=pd.Timestamp("2021-02-01"),
        )
        return (
            h6.build_cells(states, outcomes, "primary")
            .query(
                "period_index == 3 and RETURN_STATE == 'LOW_RETURN' "
                "and shock_state == 'HIGH_SHOCK' and horizon == 20"
            )
            .iloc[0]
        )

    def test_membership_frozen_with_missing(self):
        row = self.toy_cells()
        self.assertEqual(row.signal_membership_count, 25)
        self.assertEqual(row.valid_outcome_count, 20)
        self.assertEqual(row.outcome_coverage, 0.8)
        self.assertAlmostEqual(row.mean_future_return, 0.1)
        self.assertTrue(row.cell_valid)

    def test_cell_thresholds(self):
        self.assertFalse(self.toy_cells(24, 24).cell_valid)
        self.assertFalse(self.toy_cells(25, 19).cell_valid)

    def test_equal_period_weights_bootstrap(self):
        data = pd.Series([0.1, 0.3, np.nan], index=[3, 4, 5])
        first, second = h6.summarize(data), h6.summarize(data)
        self.assertAlmostEqual(first["mean_contrast"], 0.2)
        self.assertEqual(first, second)
        self.assertEqual(first["missing_periods"], "5")
        self.assertEqual(first["valid_periods"], 2)
        self.assertEqual(first["block_length"], 3)
        self.assertEqual(first["bootstrap_repetitions"], 10000)
        self.assertEqual(first["bootstrap_seed"], 20260721)

    def test_return_state_reused_no_vt_read(self):
        source = inspect.getsource(h6._load_states)
        self.assertIn('"RETURN60", "RETURN_STATE"', source)
        with patch("scripts.audit_h6_abnormal_activity_readiness.pd.read_csv") as read:
            read.return_value = pd.DataFrame(
                {
                    "period_index": range(1, 57),
                    "signal_as_of_date": pd.bdate_range("2021-01-01", periods=56),
                    "stock_code": "000001",
                    "RETURN60": 0.1,
                    "RETURN_STATE": "MID_RETURN",
                }
            )
            result = h6._load_states(Path("."))
            self.assertEqual(result.RETURN_STATE.unique().tolist(), ["MID_RETURN"])
            self.assertEqual(
                set(read.call_args.kwargs["usecols"]),
                {"period_index", "signal_as_of_date", "stock_code", "RETURN60", "RETURN_STATE"},
            )

    def test_no_future_in_amount_signal(self):
        calendar = pd.bdate_range("2020-01-01", periods=1250)
        states = pd.DataFrame(
            {
                "period_index": range(1, 57),
                "signal_as_of_date": calendar[np.arange(56) * 20 + 50],
                "stock_code": "000001",
                "RETURN60": 0.1,
                "RETURN_STATE": "MID_RETURN",
            }
        )
        amount = np.ones((1, len(calendar)))
        before, _ = h6.build_signals(states, ["000001"], amount, calendar, calendar)
        amount[:, 1151:] = 1e20
        after, _ = h6.build_signals(states, ["000001"], amount, calendar, calendar)
        pd.testing.assert_frame_equal(before, after)
        self.assertTrue(before.RETURN_STATE.eq("MID_RETURN").all())

    def test_raw_contrast_and_paired_interaction_require_both_cells(self):
        rows = []
        effects = {"LOW_RETURN": 0.03, "MID_RETURN": 0.02, "HIGH_RETURN": 0.01}
        for period in h6.PERIODS:
            for state in h6.RETURNS:
                for horizon in h6.HORIZONS:
                    for shock in h6.SHOCKS:
                        rows.append(
                            {
                                "variant": "primary",
                                "period_index": period,
                                "RETURN_STATE": state,
                                "horizon": horizon,
                                "shock_state": shock,
                                "mean_future_return": effects[state]
                                if shock == "HIGH_SHOCK"
                                else 0,
                                "cell_valid": not (
                                    period == 3 and state == "HIGH_RETURN" and shock == "LOW_SHOCK"
                                ),
                            }
                        )
        summary = h6.build_contrasts(pd.DataFrame(rows)).query("row_type == 'summary'")
        low = summary.query("RETURN_STATE == 'LOW_RETURN' and horizon == 20").iloc[0]
        interaction = summary.query("RETURN_STATE == 'LOSER_MINUS_WINNER' and horizon == 20").iloc[
            0
        ]
        self.assertAlmostEqual(low.mean_contrast, 0.03)
        self.assertEqual(low.valid_periods, 54)
        self.assertAlmostEqual(interaction.mean_contrast, 0.02)
        self.assertEqual(interaction.valid_periods, 53)
        self.assertEqual(interaction.missing_periods, "3")

    def test_no_unrelated_execution_or_network(self):
        source = inspect.getsource(h6)
        for forbidden in (
            "subprocess",
            "requests.",
            "akshare",
            "run_mcts",
            "run_phase",
            "total_market_cap",
            '"volume"',
        ):
            self.assertNotIn(forbidden, source)
        self.assertLess(
            source.index('write_csv(signals, output / "h6_signal_states.csv")'),
            source.index("prices = load_matrix"),
        )


if __name__ == "__main__":
    unittest.main()
