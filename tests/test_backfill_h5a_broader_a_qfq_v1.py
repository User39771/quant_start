from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "data_collection"
    / "backfill_h5a_broader_a_qfq_v1.py"
)
SPEC = importlib.util.spec_from_file_location("qfq_downloader", SCRIPT)
assert SPEC and SPEC.loader
qfq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qfq)


def raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2020-12-27", "2020-12-29", "2020-12-31", "2026-05-19"],
            "收盘": [9.0, 10.0, 11.0, 12.0],
        }
    )


class DownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache, self.meta = qfq.paths(self.root)
        self.cache.mkdir(parents=True)
        self.meta.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_normalize_clips_without_filling(self) -> None:
        frame = qfq.normalize_qfq(raw_frame(), "1")
        self.assertEqual(frame.trade_date.tolist(), ["2020-12-29", "2020-12-31"])
        self.assertEqual(set(frame.source), {qfq.SOURCE})
        self.assertEqual(frame.stock_code.tolist(), ["000001", "000001"])

    def test_basic_qa_rejects_duplicates_and_bad_prices(self) -> None:
        cases = [
            pd.DataFrame({"date": ["2021-01-01", "2021-01-01"], "close": [1, 1]}),
            pd.DataFrame({"date": ["2021-01-01"], "close": [0]}),
            pd.DataFrame(),
        ]
        for raw in cases:
            with self.assertRaises(qfq.DataQualityError):
                qfq.normalize_qfq(raw, "000001")

    def test_atomic_write_and_cached_validation(self) -> None:
        path = self.cache / "000001.csv"
        qfq.atomic_write_csv(qfq.normalize_qfq(raw_frame(), "000001"), path)
        self.assertTrue(qfq.valid_cached_file(path, "000001"))
        self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_three_attempts_use_bounded_backoff_then_succeed(self) -> None:
        status = qfq.initial_status(["000001"])
        calls = []
        sleeps = []

        def fetch(code: str, start: str, end: str) -> pd.DataFrame:
            calls.append(code)
            if len(calls) < 3:
                raise OSError("temporary SSL EOF")
            return raw_frame()

        outcome = qfq.download_one(
            "000001",
            status,
            0,
            self.cache,
            self.meta,
            fetch,
            sleeps.append,
            lambda low, high: low,
        )
        self.assertEqual(outcome, "success")
        self.assertEqual(calls, ["000001"] * 3)
        self.assertEqual(sleeps, [15.0, 45.0])
        self.assertEqual(int(status.at[0, "attempts"]), 3)

    def test_failure_is_recorded_without_global_stop(self) -> None:
        status = qfq.initial_status(["000001", "000002"])

        def fail(code: str, start: str, end: str) -> pd.DataFrame:
            raise OSError("SSL EOF")

        outcome = qfq.download_one(
            "000001",
            status,
            0,
            self.cache,
            self.meta,
            fail,
            lambda _: None,
            lambda low, high: low,
        )
        self.assertEqual(outcome, "transient_failed")
        self.assertEqual(status.at[0, "status"], "failed_for_now")
        self.assertEqual(status.at[1, "status"], "pending")
        rows = pd.read_csv(self.meta / "request_log.csv")
        self.assertEqual(rows.status.eq("failed").sum(), 3)
        self.assertEqual(rows.status.eq("error_backoff").sum(), 2)

    def test_success_resume_requires_status_and_valid_file(self) -> None:
        codes = ["000001", "000002"]
        status = qfq.initial_status(codes)
        status.at[0, "status"] = "success"
        qfq.atomic_write_csv(status, self.meta / "download_status.csv")
        loaded = qfq.load_status(self.meta / "download_status.csv", codes, self.cache)
        self.assertEqual(loaded.at[0, "status"], "pending")
        qfq.atomic_write_csv(qfq.normalize_qfq(raw_frame(), "000001"), self.cache / "000001.csv")
        status.at[0, "status"] = "success"
        qfq.atomic_write_csv(status, self.meta / "download_status.csv")
        loaded = qfq.load_status(self.meta / "download_status.csv", codes, self.cache)
        self.assertEqual(loaded.at[0, "status"], "success")

    def test_interrupted_attempt_is_resumable(self) -> None:
        codes = ["000001"]
        status = qfq.initial_status(codes)
        status.loc[0, ["status", "attempts_in_pass"]] = ["in_progress", 1]
        qfq.atomic_write_csv(status, self.meta / "download_status.csv")
        loaded = qfq.load_status(self.meta / "download_status.csv", codes, self.cache)
        self.assertEqual(loaded.at[0, "status"], "failed_for_now")
        self.assertEqual(loaded.at[0, "error_type"], "Interrupted")

    def test_summary_has_only_plain_download_outputs(self) -> None:
        status = qfq.initial_status(["000001", "000002"])
        summary = qfq.save_outputs(status, self.meta, 0.0, "DOWNLOAD_IN_PROGRESS")
        self.assertEqual(summary["pending_count"], 2)
        self.assertEqual(
            {path.name for path in self.meta.iterdir()},
            {"download_status.csv", "failed_codes.csv", "download_summary.md"},
        )
        source = SCRIPT.read_text(encoding="utf-8").lower()
        self.assertNotIn("sha256", source)
        self.assertNotIn("eastmoney", source)

    def test_cli_exposes_only_run_and_status(self) -> None:
        parser = qfq.build_parser()
        self.assertEqual(parser.parse_args(["run"]).command, "run")
        self.assertEqual(parser.parse_args(["status"]).command, "status")

    def test_request_log_is_append_only_csv(self) -> None:
        path = self.meta / "request_log.csv"
        for attempt in (1, 2):
            qfq.append_request(path, {"stock_code": "000001", "attempt": attempt})
        rows = pd.read_csv(path, dtype={"stock_code": str})
        self.assertEqual(rows.stock_code.tolist(), ["000001", "000001"])
        self.assertEqual(rows.attempt.tolist(), [1, 2])

    def test_error_classifier_does_not_read_stock_code_as_http_status(self) -> None:
        exc = OSError(
            "HTTPSConnectionPool /sz000429/ caused by SSLError: UNEXPECTED_EOF_WHILE_READING"
        )
        self.assertEqual(qfq.classify_error(exc), "SSLError")

    def test_real_http_status_and_retry_after_are_recognized(self) -> None:
        class Response:
            status_code = 429
            headers = {"Retry-After": "17"}

        exc = RuntimeError("rate limited")
        exc.response = Response()
        self.assertEqual(qfq.classify_error(exc), "HTTP429")
        self.assertEqual(qfq.retry_after(exc), 17.0)

    def test_json_default_handles_numpy_scalars_and_timestamp(self) -> None:
        encoded = json.dumps(
            {
                "integer": np.int64(3),
                "floating": np.float64(1.5),
                "boolean": np.bool_(True),
                "timestamp": pd.Timestamp("2026-08-20"),
            },
            default=qfq.json_default,
        )
        self.assertEqual(
            json.loads(encoded),
            {
                "integer": 3,
                "floating": 1.5,
                "boolean": True,
                "timestamp": "2026-08-20T00:00:00",
            },
        )

    def test_feasibility_selection_is_deterministic_and_board_balanced(self) -> None:
        codes = (
            [f"00{i:04d}" for i in range(20)]
            + [f"60{i:04d}" for i in range(20)]
            + [f"30{i:04d}" for i in range(20)]
            + [f"688{i:03d}" for i in range(20)]
        )
        status = qfq.initial_status(codes)
        chosen = qfq.select_feasibility(status, 1)
        counts = status.loc[chosen, "board"].value_counts().to_dict()
        self.assertEqual(counts, {"SZ_MAIN": 13, "SH_MAIN": 13, "CHINEXT": 12, "STAR": 12})
        self.assertEqual(status.loc[chosen, "feasibility_group"].unique().tolist(), [1])

    def test_normal_pause_jitter_bounds_are_used(self) -> None:
        status = qfq.initial_status(["000001"])
        sleeps = []
        original = qfq.fetch_sina
        qfq.fetch_sina = lambda code, start, end: raw_frame()
        try:
            qfq.process_indices(
                [0],
                status,
                self.cache,
                self.meta,
                0.0,
                {},
                sleeps.append,
                lambda low, high: (low + high) / 2,
            )
        finally:
            qfq.fetch_sina = original
        self.assertEqual(sleeps, [4.25])
        log = pd.read_csv(self.meta / "request_log.csv")
        self.assertEqual(log.iloc[-1].status, "normal_pause")
        self.assertEqual(float(log.iloc[-1].elapsed_seconds), 4.25)


if __name__ == "__main__":
    unittest.main()
