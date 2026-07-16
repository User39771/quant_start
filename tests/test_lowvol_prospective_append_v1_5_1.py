import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.run_lowvol_prospective_append_v1_5_1 import (
    PROTECTED,
    append_ledger,
    main,
    next_period,
    output_root,
    period_id,
)
from scripts.refresh_lowvol_prospective_data_v1_5_1 import APPROVAL_COLUMNS
from scripts.run_lowvol_locked_grid_prototype_v1_5_1 import period_targets
from scripts.test_lowvol20_hypothesis_v1_4 import window_statistics


class LowVolProspectiveAppendV151Tests(unittest.TestCase):
    def make_project(self, root: Path, calendar_length: int) -> tuple[Path, Path]:
        root = root.resolve()
        (root / "data/processed").mkdir(parents=True)
        (root / "reports").mkdir()
        (root / "scripts").mkdir()
        dates = pd.bdate_range("2026-05-18", periods=calendar_length)
        schedule = pd.DataFrame([
            {
                "rebalance_date": dates[0], "next_rebalance_date": dates[20],
                "period_trading_days": 20, "period_type": "full",
                "universe_name": "research_universe_v1_2", "transaction_cost": 0,
            },
            {
                "rebalance_date": dates[20], "next_rebalance_date": dates[min(39, len(dates) - 1)],
                "period_trading_days": min(19, len(dates) - 21), "period_type": "partial",
                "universe_name": "research_universe_v1_2", "transaction_cost": 0,
            },
        ])
        schedule.to_csv(root / "reports/adjusted_stock_pool_baseline_periods_v1_5.csv", index=False)
        benchmarks = []
        for code in ("000300", "000852", "399006"):
            for index, date in enumerate(dates):
                benchmarks.append({"benchmark_code": code, "trade_date": date, "close": 100 + index})
        benchmark_path = root / "data/processed/hybrid_benchmark_panel_v1_5.csv"
        pd.DataFrame(benchmarks).to_csv(benchmark_path, index=False)
        codes = [f"{index:06d}" for index in range(1, 57)]
        pd.DataFrame({"code": codes}).to_csv(
            root / "data/processed/research_universe_lowvol_freeze_20260711.csv", index=False
        )
        prices = []
        for number, code in enumerate(codes, 1):
            for index, date in enumerate(dates):
                close = 100 + 0.03 * index + (number % 11 + 1) * 0.1 * np.sin(index / (number % 5 + 2))
                prices.append({
                    "stock_code": code, "trade_date": date, "qfq_close": close,
                    "adjusted_close": close, "adjusted_flag": True,
                })
        price_path = root / "data/processed/adjusted_price_panel_v1_5.csv"
        pd.DataFrame(prices).to_csv(price_path, index=False)
        for relative in PROTECTED:
            path = root / relative
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"protected:{relative}", encoding="utf-8")
        run_id = "fixture_refresh"
        run = output_root(root) / "refresh_runs" / run_id
        processed = run / "processed"
        processed.mkdir(parents=True)
        approved_price = processed / "adjusted_price_panel_prospective_v1_5_1.csv"
        approved_benchmark = processed / "hybrid_benchmark_panel_prospective_v1_5_1.csv"
        approved_price.write_bytes(price_path.read_bytes())
        approved_benchmark.write_bytes(benchmark_path.read_bytes())
        price_hash = hashlib.sha256(approved_price.read_bytes()).hexdigest()
        benchmark_hash = hashlib.sha256(approved_benchmark.read_bytes()).hexdigest()
        qa_path = run / "refresh_qa.csv"
        pd.DataFrame([{
            "critical_qa_pass": True, "observe_allowed": True,
            "price_panel_sha256": price_hash, "benchmark_panel_sha256": benchmark_hash,
        }]).to_csv(qa_path, index=False)
        approval = {
            "refresh_run_id": run_id, "parent_refresh_run_id": "",
            "cutoff": dates[-1].strftime("%Y-%m-%d"),
            "price_panel_path": str(approved_price.relative_to(root)),
            "benchmark_panel_path": str(approved_benchmark.relative_to(root)),
            "price_panel_sha256": price_hash, "benchmark_panel_sha256": benchmark_hash,
            "qa_sha256": hashlib.sha256(qa_path.read_bytes()).hexdigest(),
            "approved_at": "2026-07-13T00:00:00+00:00", "publication_status": "approved",
            "decision_maker": "fixture_user", "notes": "fixture approval",
        }
        pd.DataFrame([approval], columns=APPROVAL_COLUMNS).to_csv(output_root(root) / "approved_refreshes.csv", index=False)
        return price_path, benchmark_path

    def args(self, root: Path, command: str) -> list[str]:
        return [command, "--project-root", str(root), "--refresh-run-id", "fixture_refresh"]

    def test_schedule_continuation_uses_frozen_anchor_and_twenty_intervals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, benchmark_path = self.make_project(root, 61)
            benchmark = pd.read_csv(benchmark_path, dtype={"benchmark_code": str})
            result = next_period(root, benchmark)
            dates = pd.bdate_range("2026-05-18", periods=61)
            self.assertEqual(result["rebalance_date"], dates[40])
            self.assertEqual(result["signal_date"], dates[39])
            self.assertEqual(result["evaluation_end_date"], dates[60])

    def test_lowvol_window_uses_twenty_returns_and_twenty_one_prices(self):
        dates = list(pd.bdate_range("2026-01-01", periods=21))
        prices = pd.Series(np.linspace(100, 103, 21), index=dates)
        result = window_statistics(prices, dates, dates[-1], 20)
        self.assertEqual(result["price_observation_count"], 21)
        self.assertEqual(result["return_interval_count"], 20)

    def test_evaluation_only_security_cannot_enter_universe(self):
        frame = pd.DataFrame({
            "stock_code": ["000001", "000002"], "baseline_eligible": [True, True],
            "signal_sample_member": [True, False], "evaluation_sample_member": [True, True],
            "primary_reliable_signal": [True, True], "label_available": [True, True],
            "quantile": [1, 5], "forward_return": [0.01, 0.50],
        })
        self.assertEqual(period_targets(frame)["UNIVERSE"]["codes"], ["000001"])

    def test_label_change_does_not_change_frozen_target(self):
        frame = pd.DataFrame({
            "stock_code": ["000001", "000002"], "baseline_eligible": [True, True],
            "signal_sample_member": [True, True], "evaluation_sample_member": [True, False],
            "primary_reliable_signal": [True, True], "label_available": [True, False],
            "quantile": [1, 5], "forward_return": [0.01, np.nan],
        })
        before = period_targets(frame)["UNIVERSE"]
        frame.loc[1, ["evaluation_sample_member", "label_available", "forward_return"]] = [True, True, 9.0]
        after = period_targets(frame)["UNIVERSE"]
        self.assertEqual(before["codes"], after["codes"])
        self.assertEqual(before["target"], after["target"])

    def test_incomplete_period_records_waiting_without_result(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 40)
            self.assertEqual(main(self.args(root, "observe")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv")
            self.assertEqual(ledger["status"].tolist(), ["WAITING_FOR_COMPLETE_PERIOD"])
            self.assertFalse(list(output_root(root).glob("snapshots/*/result.csv")))
            self.assertEqual(main(self.args(root, "evaluate")), 0)
            self.assertEqual(len(pd.read_csv(output_root(root) / "prospective_periods.csv")), 1)

    def test_stale_refresh_id_fails_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 61)
            args = ["observe", "--project-root", str(root), "--refresh-run-id", "older_refresh"]
            self.assertEqual(main(args), 2)

    def test_observation_freezes_pending_snapshot_before_evaluation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 41)
            self.assertEqual(main(self.args(root, "observe")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            self.assertEqual(ledger.iloc[-1]["status"], "PENDING")
            snapshot = output_root(root) / "snapshots" / ledger.iloc[-1]["period_id"]
            self.assertTrue((snapshot / "factor.csv").exists())
            self.assertFalse((snapshot / "result.csv").exists())

    def test_duplicate_append_transition_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 40)
            row = {"period_id": "p1", "status": "PENDING"}
            append_ledger(root, row)
            with self.assertRaises(ValueError):
                append_ledger(root, row)

    def test_target_weights_reconcile(self):
        frame = pd.DataFrame({
            "stock_code": ["000001", "000002", "000003", "000004", "000005"],
            "baseline_eligible": [True] * 5, "signal_sample_member": [True] * 5,
            "evaluation_sample_member": [False] * 5, "primary_reliable_signal": [True] * 5,
            "label_available": [False] * 5, "quantile": [1, 2, 3, 4, 5],
            "forward_return": [np.nan] * 5,
        })
        targets = period_targets(frame)
        for item in targets.values():
            self.assertAlmostEqual(sum(item["target"].values()), 1.0)

    def test_historical_files_remain_unchanged(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 40)
            before = {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in PROTECTED
            }
            self.assertEqual(main(self.args(root, "observe")), 0)
            after = {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in PROTECTED
            }
            self.assertEqual(before, after)

    def test_period_id_is_fixed_at_signal_time(self):
        date = pd.Timestamp("2026-07-13")
        self.assertEqual(period_id(date), period_id(date, pd.Timestamp("2026-08-10")))

    def test_complete_period_requires_calculation_then_human_approval(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 61)
            self.assertEqual(main(self.args(root, "observe")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            pid = ledger.iloc[-1]["period_id"]
            self.assertEqual(ledger.iloc[-1]["status"], "PENDING")
            self.assertEqual(main(self.args(root, "evaluate")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            self.assertEqual(ledger.iloc[-1]["status"], "CALCULATED")
            self.assertEqual(main(["append", "--project-root", str(root), "--period-id", pid]), 2)
            self.assertEqual(main(["append", "--project-root", str(root), "--period-id", pid, "--approve"]), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            self.assertEqual(ledger.iloc[-1]["status"], "APPENDED")
            self.assertEqual(main(["append", "--project-root", str(root), "--period-id", pid, "--approve"]), 2)

    def test_second_period_advances_schedule_and_keeps_nav_continuity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root, 81)
            self.assertEqual(main(self.args(root, "observe")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            first = ledger.iloc[-1]["period_id"]
            self.assertEqual(main(self.args(root, "evaluate")), 0)
            self.assertEqual(main(["append", "--project-root", str(root), "--period-id", first, "--approve"]), 0)
            self.assertEqual(main(self.args(root, "observe")), 0)
            ledger = pd.read_csv(output_root(root) / "prospective_periods.csv", dtype=str)
            pending = ledger.loc[ledger["status"].eq("PENDING")]
            second = pending.iloc[-1]["period_id"]
            self.assertNotEqual(first, second)
            self.assertEqual(main(self.args(root, "evaluate")), 0)
            result = pd.read_csv(output_root(root) / "snapshots" / second / "result.csv")
            q5_zero_cost = result[result["portfolio"].eq("Q5") & np.isclose(result["transaction_cost"], 0)]
            self.assertEqual(len(q5_zero_cost), 1)
            self.assertNotEqual(float(q5_zero_cost.iloc[0]["turnover"]), 1.0)


if __name__ == "__main__":
    unittest.main()
