from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import probe_h7_turnover_sources as probe


class H7TurnoverSourceProbeTests(unittest.TestCase):
    def test_fixed_contract_and_budget(self) -> None:
        self.assertEqual(probe.MAX_STOCKS, 30)
        self.assertEqual(probe.START_DATE, pd.Timestamp("2020-01-01"))
        self.assertEqual(probe.DATA_CUTOFF, pd.Timestamp("2026-08-20"))

    def test_sample_is_deterministic_and_bounded(self) -> None:
        root = Path(__file__).resolve().parents[1]
        first = probe.select_sample(root)
        second = probe.select_sample(root)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(len(first), 30)
        self.assertFalse(first.stock_code.duplicated().any())

    def test_cutoff_removes_later_rows(self) -> None:
        frame = pd.DataFrame({"date": ["2026-08-20", "2026-08-21"]})
        kept, removed = probe.apply_cutoff(frame, "date")
        self.assertEqual(removed, 1)
        self.assertEqual(kept.date.tolist(), ["2026-08-20"])

    def test_volume_and_percentage_units(self) -> None:
        values = pd.Series([1.0, 12.5])
        self.assertEqual(probe.baostock_volume_to_shares(values).tolist(), [1.0, 12.5])
        self.assertEqual(probe.eastmoney_volume_to_shares(values).tolist(), [100.0, 1250.0])
        np.testing.assert_allclose(probe.percent_to_decimal(values), [0.01, 0.125])

    def test_cninfo_dates_units_and_incomplete_event(self) -> None:
        raw = pd.DataFrame({
            "公告日期": ["2020-01-03", None], "变动日期": ["2020-01-02", "2020-02-01"],
            "总股本": [12.5, 13.0], "已流通股份": [10.0, 11.0],
        })
        out, removed = probe.normalize_cninfo(raw, "1")
        self.assertEqual(removed, 0)
        self.assertEqual(out.total_shares.iloc[0], 125_000)
        self.assertEqual(out.information_available_date.iloc[0], pd.Timestamp("2020-01-03"))
        self.assertTrue(out.event_date_incomplete.iloc[1])

    def test_point_in_time_lineage_has_no_future_backfill(self) -> None:
        events, _ = probe.normalize_cninfo(pd.DataFrame({
            "公告日期": ["2020-01-03"], "变动日期": ["2020-01-02"],
            "总股本": [10.0], "已流通股份": [8.0],
        }), "000001")
        lineage = probe.build_point_in_time_shares(
            events, pd.Series(pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-04"]))
        )
        self.assertTrue(pd.isna(lineage.total_shares.iloc[0]))
        self.assertEqual(lineage.total_shares.iloc[1], 100_000)
        self.assertEqual(lineage.total_shares.iloc[2], 100_000)

    def test_total_share_turnover_formula_is_distinct(self) -> None:
        volume = pd.Series([1_000.0])
        total_shares = pd.Series([100_000.0])
        self.assertAlmostEqual((volume / total_shares).iloc[0], 0.01)
        normalized, _ = probe.normalize_baostock(pd.DataFrame({
            "date": ["2020-01-02"], "code": ["sz.000001"], "open": [1], "high": [1],
            "low": [1], "close": [1], "volume": [1000], "amount": [1000], "turn": [2],
            "tradestatus": [1], "isST": [0],
        }), "000001")
        self.assertIn("baostock_circulating_turnover", normalized)
        self.assertNotIn("total_share_turnover", normalized)

    def test_exact_200_uses_prior_positive_observations(self) -> None:
        values = pd.Series(np.ones(202))
        valid = probe.exact_200_positive_valid(values)
        self.assertFalse(valid.iloc[199])
        self.assertTrue(valid.iloc[200])
        values.iloc[10] = 0
        self.assertFalse(probe.exact_200_positive_valid(values).iloc[200])

    def test_raw_writer_rejects_post_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            frame = pd.DataFrame({"trade_date": ["2026-08-21"], "value": [1]})
            with self.assertRaisesRegex(ValueError, "post_cutoff"):
                probe.write_raw(Path(directory), "test", {"000001": frame})

    def test_no_research_or_full_market_paths(self) -> None:
        source = inspect.getsource(probe).lower()
        for forbidden in ("statsmodels", "sklearn", "c2_hat", "c2_sign", "sharpe"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("5195", source)


if __name__ == "__main__":
    unittest.main()
