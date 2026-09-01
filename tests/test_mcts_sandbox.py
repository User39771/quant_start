import unittest

import numpy as np
import pandas as pd

from aq_factor_lab.mcts_sandbox import (
    canonical,
    depth,
    formula,
    parse_formula,
    quantile_members,
    random_expression,
    run_mcts,
    score_candidate,
)
from scripts.run_mcts_historical_seen_sandbox_v0 import guarded_read_csv, mark_equivalence


class MctsSandboxTest(unittest.TestCase):
    def toy_panel(self):
        rows = []
        for period in range(24):
            for stock in range(25):
                rows.append(
                    {
                        "period_index": period,
                        "stock_code": f"{stock:06d}",
                        "signal_sample_member": True,
                        "RETURN_60": float(stock),
                        "VOL_20": float((stock + period) % 25),
                        "AMOUNT_MEAN_20": float(stock + 1),
                        "forward_return": -float(stock) / 100,
                    }
                )
        return pd.DataFrame(rows)

    def test_parser_canonical_and_depth(self):
        self.assertEqual(canonical(parse_formula("REV60")), "NEG(RETURN_60)")
        self.assertEqual(canonical(parse_formula("-MOM60")), "NEG(RETURN_60)")
        self.assertEqual(canonical(parse_formula("2 * REV60")), "NEG(RETURN_60)")
        self.assertEqual(depth(parse_formula("RANK(NEG(RETURN_60))")), 3)
        with self.assertRaises(ValueError):
            parse_formula("RSI(RETURN_60)")

    def test_rank_and_portfolio_equivalence(self):
        panel = self.toy_panel()
        scores = [score_candidate(parse_formula(x), panel) for x in (
            "REV60", "-MOM60", "2 * REV60", "RANK(NEG(RETURN_60))"
        )]
        self.assertEqual(len({x["rank_signature_hash"] for x in scores}), 1)
        self.assertEqual(len({x["portfolio_signature_hash"] for x in scores}), 1)

    def test_reward_deterministic_and_direction_fixed(self):
        panel = self.toy_panel()
        positive = score_candidate(parse_formula("RETURN_60"), panel)
        negative = score_candidate(parse_formula("NEG(RETURN_60)"), panel)
        self.assertAlmostEqual(positive["reward"], -1.0)
        self.assertAlmostEqual(negative["reward"], 1.0)
        self.assertEqual(positive, score_candidate(parse_formula("RETURN_60"), panel))

    def test_no_forward_return_in_expression(self):
        with self.assertRaises(ValueError):
            parse_formula("ADD(RETURN_60,forward_return)")

    def test_random_seed_reproducible_and_bounded(self):
        import random
        rng_a, rng_b = random.Random(7), random.Random(7)
        a = [formula(random_expression(rng_a)) for _ in range(5)]
        b = [formula(random_expression(rng_b)) for _ in range(5)]
        self.assertEqual(a, b)
        self.assertTrue(all(depth(parse_formula(x)) <= 4 for x in a))

    def test_constant_signal_fails(self):
        result = score_candidate(parse_formula("SUB(RETURN_60,RETURN_60)"), self.toy_panel())
        self.assertEqual(result["evaluation_status"], "failed")

    def test_signal_missing_fails_without_shrinking_universe(self):
        panel = self.toy_panel()
        panel.loc[0, "VOL_20"] = np.nan
        result = score_candidate(parse_formula("VOL_20"), panel)
        self.assertEqual(result["evaluation_status"], "failed")
        self.assertEqual(result["failure_reason"], "non_finite_signal_on_frozen_target")

    def test_q5_receives_phase_a_split_remainder(self):
        target = pd.DataFrame(
            {"stock_code": [f"{i:06d}" for i in range(11)], "signal": range(11)}
        )
        groups = quantile_members(target, "signal")
        self.assertEqual(len(groups[5]), 3)
        self.assertEqual(target.loc[groups[5], "signal"].tolist(), [10, 9, 8])

    def test_mcts_budget_and_reproducibility(self):
        def evaluator(expr):
            return {"reward": float(len(formula(expr)))}

        first = run_mcts(11, 20, evaluator)
        second = run_mcts(11, 20, evaluator)
        self.assertEqual(len(first), 20)
        self.assertEqual([formula(x[0]) for x in first], [formula(x[0]) for x in second])

    def test_every_evaluation_and_failure_can_be_registered(self):
        def row(candidate_id, status):
            return {
                "candidate_id": candidate_id,
                "canonical_formula": "RETURN_60",
                "rank_signature_hash": "x",
                "portfolio_signature_hash": "p",
                "evaluation_status": status,
                "duplicate_formula_of": "",
                "information_equivalent_to": "",
                "rank_equivalent": False,
                "portfolio_equivalent": False,
            }

        rows = pd.DataFrame(
            [
                row("a", "ok"),
                row("b", "failed"),
            ]
        )
        marked = mark_equivalence(rows)
        self.assertEqual(len(marked), 2)
        self.assertEqual(marked.iloc[1]["duplicate_formula_of"], "a")

    def test_prospective_and_final_paths_are_rejected(self):
        from pathlib import Path
        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "data/prospective/rev60.csv")
        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "reports/final_test.csv")


if __name__ == "__main__":
    unittest.main()
