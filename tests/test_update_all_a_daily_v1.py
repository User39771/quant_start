from __future__ import annotations

import hashlib
import io
import sys
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts" / "data_collection"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import update_all_a_daily_v1 as mod  # noqa: E402


def benchmark_raw(
    closes: tuple[float, float] = (10.0, 11.0), code: str = "000300"
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-07-28", "2026-07-29"],
            "收盘": closes,
            "代码": [code, code],
        }
    )


def write_benchmark_cache(root: Path) -> None:
    path = root / "data/cache/benchmark_refresh_v1_5/000300.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "benchmark_code": ["000300", "000300"],
            "trade_date": ["2026-07-28", "2026-07-29"],
            "close": [10.0, 11.0],
            "instrument_type": ["index", "index"],
            "instrument_name": ["CSI 300", "CSI 300"],
            "source": ["test", "test"],
        }
    ).to_csv(path, index=False)


class ProtectedFileTests(unittest.TestCase):
    def test_protected_file_readable(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.csv"
            path.write_bytes(b"abc")
            self.assertEqual(
                mod.sha256(path, sleep_fn=lambda _: None),
                hashlib.sha256(b"abc").hexdigest(),
            )

    def test_simulated_lock_returns_required_reason(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "locked.csv"
            path.write_text("x", encoding="utf-8")
            with self.assertRaises(mod.ProtectedFileUnreadable) as caught:
                mod.collect_protected_hashes(
                    root,
                    root / "inventory.csv",
                    paths=[path],
                    hash_fn=Mock(side_effect=PermissionError(13, "file locked")),
                )
            self.assertEqual(caught.exception.reason_code, "PROTECTED_FILE_UNREADABLE")
            self.assertIn("locked.csv", str(caught.exception))
            self.assertIn("errno=13", str(caught.exception))

    def test_unreadable_file_is_not_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            locked, readable = root / "locked.csv", root / "readable.csv"
            locked.write_text("x", encoding="utf-8")
            readable.write_text("y", encoding="utf-8")

            def digest(path: Path) -> str:
                if path == locked:
                    raise PermissionError(13, "locked")
                return "ok"

            with self.assertRaises(mod.ProtectedFileUnreadable):
                mod.collect_protected_hashes(
                    root,
                    root / "inventory.csv",
                    paths=[locked, readable],
                    hash_fn=digest,
                )
            inventory = pd.read_csv(root / "inventory.csv")
            self.assertEqual(len(inventory), 2)
            self.assertEqual(
                inventory.set_index("relative_path").loc["locked.csv", "status"],
                "unreadable",
            )
            self.assertEqual(
                inventory.set_index("relative_path").loc["readable.csv", "status"],
                "ok",
            )

    def test_snapshot_failure_does_not_create_formal_snapshot(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "locked.csv"
            path.write_text("x", encoding="utf-8")
            with (
                patch.object(mod, "protected_files", return_value=[path]),
                patch.object(
                    mod,
                    "sha256",
                    side_effect=PermissionError(13, "locked"),
                ),
            ):
                exit_code, _ = mod.run_snapshot(root)
            self.assertEqual(exit_code, 1)
            self.assertFalse(mod.hash_snapshot_path(root).exists())

    def test_three_retries_then_success(self):
        calls = 0
        sleeps: list[float] = []

        def opener(_: Path):
            nonlocal calls
            calls += 1
            if calls <= 3:
                raise PermissionError(13, "locked")
            return io.BytesIO(b"ok")

        digest = mod.sha256(
            Path("unused"),
            sleep_fn=sleeps.append,
            open_fn=opener,
        )
        self.assertEqual(digest, hashlib.sha256(b"ok").hexdigest())
        self.assertEqual(calls, 4)
        self.assertEqual(sleeps, [1, 2, 4])

    def test_three_retries_then_failure(self):
        opener = Mock(side_effect=PermissionError(13, "locked"))
        sleeps: list[float] = []
        with self.assertRaises(PermissionError):
            mod.sha256(
                Path("unused"),
                sleep_fn=sleeps.append,
                open_fn=opener,
            )
        self.assertEqual(opener.call_count, 4)
        self.assertEqual(sleeps, [1, 2, 4])

    def test_required_liquidity_file_remains_protected(self):
        paths = {
            path.as_posix()
            for path in mod.protected_files(ROOT)
        }
        self.assertTrue(
            any(
                path.endswith("reports/liquidity_filter_amount_readiness_v1_6.csv")
                for path in paths
            )
        )


class BenchmarkProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_dir = self.root / "reports/run"
        self.run_dir.mkdir(parents=True)
        write_benchmark_cache(self.root)
        self.client = SimpleNamespace(version="test")

    def tearDown(self):
        self.tmp.cleanup()

    def test_remote_disconnected_classification(self):
        self.assertEqual(
            mod.classify_probe_error(RemoteDisconnected("closed")),
            "REMOTE_DISCONNECTED",
        )

    def test_primary_three_failures_then_stops_without_fallback(self):
        primary = Mock(side_effect=RemoteDisconnected("closed"))
        fallback = Mock(return_value=benchmark_raw())
        with self.assertRaises(mod.BenchmarkProbeError):
            mod.benchmark_preflight(
                self.root,
                self.run_dir,
                "run",
                "2026-07-30",
                "000300",
                client=self.client,
                primary_fetch=primary,
                fallback_fetch=fallback,
                allow_fallback=False,
                sleep_fn=lambda _: None,
            )
        self.assertEqual(primary.call_count, 3)
        fallback.assert_not_called()

    def test_unapproved_fallback_is_never_called(self):
        primary = Mock(side_effect=RuntimeError("offline"))
        fallback = Mock()
        with self.assertRaises(mod.BenchmarkProbeError):
            mod.benchmark_preflight(
                self.root,
                self.run_dir,
                "run",
                "2026-07-30",
                "000300",
                client=self.client,
                primary_fetch=primary,
                fallback_fetch=fallback,
                allow_fallback=False,
                sleep_fn=lambda _: None,
            )
        fallback.assert_not_called()

    def test_fallback_identity_mismatch_blocks(self):
        with self.assertRaises(mod.BenchmarkProbeError) as caught:
            mod.benchmark_preflight(
                self.root,
                self.run_dir,
                "run",
                "2026-07-30",
                "000300",
                client=self.client,
                primary_fetch=Mock(side_effect=RuntimeError("offline")),
                fallback_fetch=Mock(return_value=benchmark_raw(code="000852")),
                sleep_fn=lambda _: None,
            )
        self.assertEqual(caught.exception.reason_code, "INDEX_IDENTITY_MISMATCH")

    def test_fallback_overlap_conflict_blocks(self):
        with self.assertRaises(mod.BenchmarkProbeError) as caught:
            mod.benchmark_preflight(
                self.root,
                self.run_dir,
                "run",
                "2026-07-30",
                "000300",
                client=self.client,
                primary_fetch=Mock(side_effect=RuntimeError("offline")),
                fallback_fetch=Mock(return_value=benchmark_raw((20.0, 21.0))),
                sleep_fn=lambda _: None,
            )
        self.assertEqual(caught.exception.reason_code, "INDEX_IDENTITY_MISMATCH")

    def test_successful_primary_resolves_end_and_does_not_use_fallback(self):
        fallback = Mock()
        _, resolved, frame, source = mod.benchmark_preflight(
            self.root,
            self.run_dir,
            "run",
            "2026-07-30",
            "000300",
            client=self.client,
            primary_fetch=Mock(return_value=benchmark_raw()),
            fallback_fetch=fallback,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(resolved, "2026-07-29")
        self.assertEqual(source, "ak.index_zh_a_hist")
        self.assertEqual(set(frame["instrument_type"]), {"index"})
        fallback.assert_not_called()

    def test_benchmark_failure_does_not_enter_inventory_or_stock_phase(self):
        with (
            patch.object(mod, "collect_protected_hashes", return_value={"x": "y"}),
            patch.object(mod, "load_recent_hash_snapshot", return_value={"x": "y"}),
            patch.object(
                mod,
                "benchmark_preflight",
                side_effect=mod.BenchmarkProbeError(
                    "REMOTE_DISCONNECTED", "offline"
                ),
            ),
            patch.object(mod, "build_inventory") as inventory,
        ):
            with self.assertRaises(RuntimeError):
                mod.prepare_run(self.root, "smoke", "2026-07-30", 3, 0)
        inventory.assert_not_called()
        self.assertFalse((self.root / "data/sandbox/all_a_daily_v1/raw").exists())

    def test_successful_benchmark_preflight_enters_phase_two(self):
        universe_raw = pd.DataFrame(
            {
                "代码": ["600519", "000001", "920000"],
                "名称": ["SH", "SZ", "BJ"],
            }
        )
        fake_client = SimpleNamespace(
            version="test",
            stock_universe=Mock(return_value=universe_raw),
        )
        benchmark = mod.normalize_benchmark_response(
            benchmark_raw(),
            benchmark_code="000300",
            endpoint_name="ak.index_zh_a_hist",
            requested_as_of="2026-07-30",
        )
        with (
            patch.object(mod, "collect_protected_hashes", return_value={"x": "y"}),
            patch.object(mod, "load_recent_hash_snapshot", return_value={"x": "y"}),
            patch.object(
                mod,
                "benchmark_preflight",
                return_value=(
                    pd.DatetimeIndex(pd.to_datetime(benchmark["trade_date"])),
                    "2026-07-29",
                    benchmark,
                    "ak.index_zh_a_hist",
                ),
            ),
            patch.object(mod, "build_inventory", return_value=pd.DataFrame()) as inventory,
            patch.object(mod, "AkSharePublicClient", return_value=fake_client),
        ):
            _, manifest, _, _ = mod.prepare_run(
                self.root, "smoke", "2026-07-30", 3, 0
            )
        inventory.assert_called_once()
        self.assertTrue(manifest["benchmark_preflight_pass"])


class GateTests(unittest.TestCase):
    def test_all_protected_hashes_unchanged(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.csv"
            self.assertTrue(mod.write_hash_audit({"a": "x"}, {"a": "x"}, path))
            self.assertFalse(mod.write_hash_audit({"a": "x"}, {"a": "y"}, path))

    def test_full_run_requires_explicit_approval(self):
        with TemporaryDirectory() as tmp:
            with patch.object(
                sys,
                "argv",
                [
                    "update_all_a_daily_v1.py",
                    "run",
                    "--project-root",
                    tmp,
                ],
            ):
                self.assertEqual(mod.main(), 2)


if __name__ == "__main__":
    unittest.main()
