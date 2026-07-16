import unittest

import numpy as np
import pandas as pd

from scripts.run_changzheng10_event_study import (
    EVENT_DATE,
    approximate_equal_weight_contribution,
    breadth60,
    classify_interpretation,
    compounded,
    daily_returns,
    event_calendar,
    normalize_prices,
    theme_codes,
)


class Changzheng10EventStudyTests(unittest.TestCase):
    def test_theme_membership_is_fixed_and_deduplicated(self):
        themes = ["商业航天"] * 11 + ["AI|商业航天"] + ["AI"] * 44
        codes = [f"{index:06d}" for index in range(56)]
        codes[11] = "002049"
        universe = pd.DataFrame({"code": codes, "theme": themes})
        space, ai = theme_codes(universe)
        self.assertEqual(len(space), 12)
        self.assertEqual(len(ai), 45)
        self.assertEqual(set(space) & set(ai), {"002049"})

    def test_calendar_maps_first_full_day_and_t_plus_5(self):
        dates = pd.bdate_range("2026-07-01", "2026-07-20")
        frame = pd.DataFrame({"trade_date": dates})
        _, relative = event_calendar(frame, frame)
        self.assertEqual(relative[0], EVENT_DATE)
        self.assertEqual(relative[1], pd.Timestamp("2026-07-13"))
        self.assertEqual(relative[5], pd.Timestamp("2026-07-17"))

    def test_returns_compounding_and_no_fill(self):
        matrix = pd.DataFrame(
            {"a": [100.0, 110.0, 99.0], "b": [100.0, 100.0, 110.0]},
            index=pd.date_range("2026-01-01", periods=3),
        )
        returns = daily_returns(matrix)
        self.assertAlmostEqual(compounded(returns["a"]), -0.01)
        broken = matrix.copy()
        broken.iloc[1, 0] = np.nan
        with self.assertRaises(ValueError):
            daily_returns(broken)

    def test_approximate_contribution_is_static_equal_weight(self):
        contributions = [
            approximate_equal_weight_contribution(value, 12) for value in (0.12, -0.06)
        ]
        self.assertEqual(contributions, [0.01, -0.005])

    def test_normalization_rejects_duplicate_dates(self):
        raw = pd.DataFrame({"日期": ["2026-07-10", "2026-07-10"], "收盘": [10.0, 10.1]})
        with self.assertRaises(ValueError):
            normalize_prices("000001", raw, "stock", "x", "endpoint", "now")

    def test_breadth_uses_fractional_overlap_and_exact_window(self):
        calendar = list(pd.bdate_range("2026-01-01", periods=60))
        universe = pd.DataFrame(
            {"code": ["000001", "002049"], "theme": ["商业航天", "AI|商业航天"]}
        )
        rows = []
        for code, trend in (("000001", 1.0), ("002049", -1.0)):
            for index, date in enumerate(calendar):
                rows.append(
                    {
                        "instrument_type": "stock",
                        "instrument_code": code,
                        "trade_date": date,
                        "adjusted_close": 100 + trend * index,
                    }
                )
        result = breadth60(pd.DataFrame(rows), universe, calendar, calendar[-1])
        self.assertEqual(result["eligible_weight"], 1.5)
        self.assertEqual(result["above_weight"], 1.0)
        self.assertAlmostEqual(result["breadth60"], 2 / 3)

    def test_descriptive_categories(self):
        positive = {
            (benchmark, day): 0.01 for benchmark in ("000300", "000852") for day in (1, 3, 5)
        }
        self.assertEqual(classify_interpretation(positive, 8)[0], "positive response observed")
        mixed = positive.copy()
        mixed[("000300", 3)] = -0.01
        mixed[("000300", 5)] = -0.01
        self.assertEqual(classify_interpretation(mixed, 8)[0], "mixed response")
        unclear = {
            ("000300", 1): 0.01,
            ("000852", 1): -0.01,
            ("000300", 3): -0.01,
            ("000852", 3): 0.01,
            ("000300", 5): 0.01,
            ("000852", 5): -0.01,
        }
        self.assertEqual(classify_interpretation(unclear, 6)[0], "no clear response observed")
        zeros = {(benchmark, day): 0.0 for benchmark in ("000300", "000852") for day in (1, 3, 5)}
        self.assertEqual(classify_interpretation(zeros, 0)[0], "no clear response observed")


if __name__ == "__main__":
    unittest.main()
