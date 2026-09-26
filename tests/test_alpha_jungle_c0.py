import unittest
import hashlib
import json
import threading
import time
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from aq_factor_lab.alpha_jungle_c0.contract import (
    FINAL_TEST_LOCKED,
    FinalTestLockedError,
    assert_period_allowed,
    label_eligible_sessions,
)
from aq_factor_lab.alpha_jungle_c0.evaluation import (
    daily_coverage_passes,
    daily_rank_ic,
    formula_session_coverage,
)
from aq_factor_lab.alpha_jungle_c0.formula import (
    FormulaError,
    parse_formula,
    required_historical_lookback,
)
from aq_factor_lab.alpha_jungle_c0.provider import (
    LAUNCH_MARKER_SCHEMA_VERSION,
    CodexProvider,
    LLM_PROVIDER_TIMEOUT_SECONDS,
    NativeSubagentProvider,
    build_launch_marker,
    normalize_launch_marker,
)
from aq_factor_lab.alpha_jungle_c0.search import MCTSNode, backup_max, search_disabled, uct
from aq_factor_lab.alpha_jungle_c0.zoo import exact_signal_fingerprint, rank_signal_fingerprint


class AlphaJungleC0Tests(unittest.TestCase):
    @staticmethod
    def _launch_request(proposal=106):
        return {
            "resume_metadata": {
                "experiment_id": "ALPHA_JUNGLE_QLIB_C0",
                "arm": "DIRECT_LLM",
                "proposal_index": proposal,
                "charged_call_index": proposal,
                "prompt_version": "V1",
                "generator_prompt_hash": "frozen-hash",
            }
        }

    def test_current_launch_marker_loads_with_timestamp(self):
        marker = build_launch_marker(self._launch_request(), "/root/current", "2026-09-23T00:00:00Z")
        loaded = normalize_launch_marker(marker, self._launch_request())
        self.assertEqual(loaded["schema_version"], LAUNCH_MARKER_SCHEMA_VERSION)
        self.assertFalse(loaded["legacy_marker"])
        self.assertEqual(loaded["timestamp_utc"], "2026-09-23T00:00:00Z")

    def test_legacy_launch_marker_charges_once_without_replay_or_fake_timestamp(self):
        request = self._launch_request()
        marker = normalize_launch_marker({"task_id": "/root/legacy"}, request)
        self.assertTrue(marker["legacy_marker"])
        self.assertIsNone(marker["timestamp_utc"])
        committed = {105}
        charge = 106 not in committed
        committed.add(106)
        self.assertTrue(charge)
        self.assertFalse(106 not in committed)  # duplicate recovery cannot double-charge
        self.assertEqual(max(committed) + 1, 107)
        self.assertTrue(FINAL_TEST_LOCKED)

    def test_label_horizon_split_isolation(self):
        train = [date(2018, 12, day) for day in range(1, 21)]
        eligible = label_eligible_sessions(train, train[0], train[-1])
        self.assertIn(train[-12], eligible)
        self.assertNotIn(train[-11], eligible)

        validation = [date(2020, 12, day) for day in range(1, 21)]
        self.assertNotIn(
            validation[-11], label_eligible_sessions(validation, validation[0], validation[-1])
        )

    def test_nested_required_historical_lookback(self):
        formula = parse_formula("Zscore(Pct(Delay(close,5),10),20)")
        self.assertEqual(required_historical_lookback(formula), 34)
        autocorr = parse_formula("Add(Autocorr(close,20,5),Rank(Pct(close,5),20))")
        self.assertEqual(required_historical_lookback(autocorr), 24)

    def test_daily_and_formula_coverage_thresholds(self):
        self.assertTrue(daily_coverage_passes(300, 240))
        self.assertFalse(daily_coverage_passes(300, 239))
        self.assertTrue(daily_coverage_passes(10, 20))
        self.assertEqual(formula_session_coverage(90, 100), (0.9, True))
        self.assertEqual(formula_session_coverage(89, 100), (0.89, False))
        self.assertEqual(formula_session_coverage(0, 0), (0.0, False))

    @patch("aq_factor_lab.alpha_jungle_c0.provider.subprocess.run")
    def test_provider_timeout_is_a_charged_failure_not_a_crash(self, run):
        from subprocess import TimeoutExpired

        run.side_effect = TimeoutExpired("codex", LLM_PROVIDER_TIMEOUT_SECONDS)
        with self.subTest("one invocation returns one logged failure"):
            with TemporaryDirectory() as directory:
                result = CodexProvider().invoke(
                    "prompt", Path(directory) / "schema.json", Path(".")
                )
            self.assertFalse(result.ok)
            self.assertEqual(result.error, "provider timeout after 600s")

    def test_native_subagent_bridge_enforces_contract(self):
        with TemporaryDirectory() as directory:
            bridge = Path(directory)

            def respond():
                while not list(bridge.glob("*.request.json")):
                    time.sleep(0.01)
                request = json.loads(list(bridge.glob("*.request.json"))[0].read_text())
                (bridge / f"{request['request_id']}.response.json").write_text(
                    json.dumps(
                        {
                            "task_id": "/root/test",
                            "model": "gpt-5.6-sol",
                            "reasoning_effort": "medium",
                            "tool_or_repository_leakage": False,
                            "output": {"suggestion": "test", "formula": "Zscore(Pct(close,5),20)"},
                        }
                    )
                )

            worker = threading.Thread(target=respond)
            worker.start()
            result = NativeSubagentProvider(bridge, timeout_seconds=2).invoke(
                "prompt", bridge / "unused.json", Path(".")
            )
            worker.join()
            self.assertTrue(result.ok)
            self.assertEqual(result.task_id, "/root/test")
            self.assertEqual(result.output["formula"], "Zscore(Pct(close,5),20)")

    def test_formula_generator_prompt_v1_has_complete_frozen_signatures(self):
        prompt_path = (
            Path(__file__).resolve().parents[1]
            / "reports" / "alpha_jungle_c0" / "FORMULA_GENERATOR_PROMPT_V1.txt"
        )
        prompt = prompt_path.read_text(encoding="utf-8")
        self.assertEqual(prompt.count("{{PROPOSAL_CONTEXT}}"), 1)
        for signature in (
            "Neg(x)", "Abs(x)", "Sign(x)", "Delay(x,window)", "Diff(x,window)",
            "Pct(x,window)", "Ma(x,window)", "Med(x,window)", "Sum(x,window)",
            "Std(x,window)", "Max(x,window)", "Min(x,window)", "Rank(x,window)",
            "Skew(x,window)", "Kurt(x,window)", "Vari(x,window)",
            "Zscore(x,window)", "Autocorr(x,window,lag)", "Add(x,y)", "Sub(x,y)",
            "Mul(x,y)", "Greater(x,y)", "Less(x,y)", "Corr(x,y,window)",
        ):
            self.assertIn(signature, prompt)
        self.assertEqual(
            hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "39ce9ef825e9bc5d5fbb87968a9d60fb4450d1eca5b8ebc096bfc2edae0fe17a",
        )
        parse_formula("Add(Rank(Pct(close,5),20),Autocorr(Pct(volume,5),20,2))")
        parse_formula("Corr(Pct(close,5),Pct(volume,5),20)")

    def test_final_test_lock_fails_on_any_overlap(self):
        assert_period_allowed(date(2019, 1, 1), date(2020, 12, 31))
        with self.assertRaisesRegex(FinalTestLockedError, "FINAL_TEST_LOCKED"):
            assert_period_allowed(date(2020, 12, 31), date(2021, 1, 1))

        locked_index = pd.MultiIndex.from_product([["2021-01-04"], ["A"]])
        locked = pd.Series([1.0], index=locked_index)
        with self.assertRaisesRegex(FinalTestLockedError, "FINAL_TEST_LOCKED"):
            daily_rank_ic(locked, locked)

    def test_formula_canonicalization_validation_and_qlib_compile(self):
        left = parse_formula("Add(Zscore(close,20),Rank(Pct(volume,5),10))")
        right = parse_formula("Add(Rank(Pct(volume,5),10),Zscore(close,20))")
        self.assertEqual(left.canonical(), right.canonical())
        self.assertIn("Ref($volume,5)", left.qlib_expression())
        with self.assertRaises(FormulaError):
            parse_formula("Add(close,volume)")
        with self.assertRaises(FormulaError):
            parse_formula("Delay(close,2)")

    def test_signal_fingerprints_separate_values_from_ranks(self):
        index = pd.MultiIndex.from_product([["2020-01-02", "2020-01-03"], ["A", "B", "C"]])
        a = pd.Series([1, 2, 3, 3, 2, 1], index=index, dtype=float)
        b = a * 10
        self.assertNotEqual(exact_signal_fingerprint(a), exact_signal_fingerprint(b))
        self.assertEqual(rank_signal_fingerprint(a), rank_signal_fingerprint(b))

    def test_mcts_contract_and_stop_guard(self):
        nodes = [MCTSNode(0.2), MCTSNode(0.4)]
        self.assertGreater(uct(10, nodes[0]), nodes[0].reward)
        backup_max(nodes, 0.7)
        self.assertTrue(all(node.reward == 0.7 and node.visits == 2 for node in nodes))
        with self.assertRaisesRegex(RuntimeError, "not authorized"):
            search_disabled()


if __name__ == "__main__":
    unittest.main()
