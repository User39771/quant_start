import random
import unittest

import numpy as np
import pandas as pd

from aq_factor_lab.mcts_sandbox_v1 import (
    Node,
    build_common_signal_panel,
    canonical,
    evaluate_expression,
    formula,
    mcts_proposal,
    percentile_rank,
    random_expression,
    signal_identity,
)
from scripts.run_mcts_historical_seen_sandbox_v1 import guarded_read_csv, search_seed


class MctsSandboxV1Test(unittest.TestCase):
    def signal_panel(self, periods=2, stocks=48):
        rows = []
        for period in range(periods):
            for stock in range(stocks):
                rows.append(
                    {
                        "period_index": period,
                        "stock_code": f"{stock:06d}",
                        "signal_sample_member": True,
                        "RETURN_60": float(stock),
                        "VOL_20": float((stock + period) % stocks + 1),
                        "AMOUNT_MEAN_20": float(stock + 1) * 1e8,
                    }
                )
        return pd.DataFrame(rows)

    def test_common_mask_coverage_no_fill_and_no_labels(self):
        raw = self.signal_panel()
        raw.loc[(raw.period_index == 0) & (raw.stock_code == "000000"), "VOL_20"] = np.nan
        panel, coverage = build_common_signal_panel(raw)
        self.assertEqual(coverage.loc[0, "common_count"], 47)
        self.assertTrue(coverage.loc[0, "period_valid"])
        self.assertAlmostEqual(coverage.loc[0, "common_coverage"], 47 / 48)
        self.assertTrue(np.isnan(panel.loc[0, "P_VOL_20"]))
        with self.assertRaises(ValueError):
            build_common_signal_panel(raw.assign(forward_return=0.0))

    def test_minimum_stock_count(self):
        _, coverage = build_common_signal_panel(self.signal_panel(stocks=24))
        self.assertFalse(coverage["period_valid"].any())

    def test_all_candidates_share_common_target(self):
        panel, _ = build_common_signal_panel(self.signal_panel())
        identities = [
            signal_identity((primitive,), panel)
            for primitive in ("P_RETURN_60", "P_VOL_20", "P_AMOUNT_MEAN_20")
        ]
        self.assertTrue(all(result["valid"] for result in identities))

    def test_percentile_rank_and_ties(self):
        values = pd.Series([1.0, 1.0, 3.0])
        expected = pd.Series([0.5, 0.5, 1.0])
        pd.testing.assert_series_equal(percentile_rank(values), expected)

    def test_rev60_normalized_rank_identity(self):
        panel, _ = build_common_signal_panel(self.signal_panel())
        normalized = evaluate_expression(("NEG", ("P_RETURN_60",)), panel)
        raw = -panel["RETURN_60"]
        for _, group in panel.assign(n=normalized, r=raw).groupby("period_index"):
            self.assertTrue(group.n.rank().equals(group.r.rank()))

    def test_canonical_rules(self):
        a, b = ("P_RETURN_60",), ("P_VOL_20",)
        self.assertEqual(canonical(("ADD", a, b)), canonical(("ADD", b, a)))
        self.assertEqual(canonical(("MUL", a, b)), canonical(("MUL", b, a)))
        self.assertEqual(canonical(("NEG", ("NEG", a))), canonical(a))
        self.assertEqual(canonical(("RANK", ("RANK", a))), canonical(("RANK", a)))

    def test_rank_signature_ignores_labels(self):
        panel, _ = build_common_signal_panel(self.signal_panel())
        expr = ("NEG", ("P_RETURN_60",))
        first = signal_identity(expr, panel.assign(forward_return=1.0))
        second = signal_identity(expr, panel.assign(forward_return=-1.0))
        self.assertEqual(first["signal_rank_signature"], second["signal_rank_signature"])

    def test_seed_and_mcts_proposals_reproducible(self):
        left, right = random.Random(7), random.Random(7)
        self.assertEqual(
            [formula(random_expression(left)) for _ in range(10)],
            [formula(random_expression(right)) for _ in range(10)],
        )
        roots = Node(None), Node(None)
        rngs = random.Random(9), random.Random(9)
        self.assertEqual(
            formula(mcts_proposal(roots[0], rngs[0]).expr),
            formula(mcts_proposal(roots[1], rngs[1]).expr),
        )

    def test_cache_hit_does_not_consume_unique_budget(self):
        panel, _ = build_common_signal_panel(self.signal_panel(periods=24, stocks=25))
        panel["forward_return"] = -panel["RETURN_60"] / 100
        rows, summary = search_seed("mcts", 3, panel, unique_budget=5, max_proposals=200)
        unique_indices = pd.Series([row["unique_evaluation_index"] for row in rows]).dropna()
        self.assertEqual(summary["unique_reward_evaluations"], unique_indices.nunique())
        self.assertTrue(summary["canonical_cache_hits"] + summary["rank_cache_hits"] > 0)

    def test_forbidden_paths(self):
        from pathlib import Path

        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "data/prospective/rev60.csv")
        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "reports/final_test.csv")


if __name__ == "__main__":
    unittest.main()
