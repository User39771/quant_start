import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.refresh_lowvol_prospective_data_v1_5_1 import (
    CONTINUITY_COLUMNS,
    apply_continuity_bridge,
    approved_segment,
    new_run_id,
    prepare,
    publish,
    read_approvals,
    run_dir,
    sha256,
)
from scripts.run_lowvol_prospective_append_v1_5_1 import resolve_approved_refresh


class ProspectiveRefreshV151Tests(unittest.TestCase):
    codes = [f"{number:06d}" for number in range(1, 57)]
    benchmarks = ("000300", "000852", "399006")
    dates = ("2026-07-09", "2026-07-10")

    @staticmethod
    def approve(root: Path, run_id: str) -> int:
        return publish(root, run_id, True, "fixture_user", "fixture approval")

    def project(self, root: Path) -> None:
        processed = root / "data/processed"
        processed.mkdir(parents=True)
        pd.DataFrame({"code": self.codes}).to_csv(
            processed / "research_universe_lowvol_freeze_20260711.csv", index=False
        )
        stocks = []
        for number, code in enumerate(self.codes, 1):
            for offset, date in enumerate(self.dates):
                close = 10 + number / 100 + offset / 10
                stocks.append({
                    "stock_code": code, "trade_date": date, "qfq_close": close,
                    "source_qfq": "frozen", "adjusted_close": close, "adjusted_flag": True,
                })
        pd.DataFrame(stocks).to_csv(processed / "adjusted_price_panel_v1_5.csv", index=False)
        rows = []
        for number, code in enumerate(self.benchmarks, 1):
            for offset, date in enumerate(self.dates):
                rows.append({
                    "benchmark_code": code, "trade_date": date, "close": 1000 + number + offset,
                    "instrument_type": "index", "instrument_name": {"000300": "CSI 300", "000852": "CSI 1000", "399006": "ChiNext Index"}[code],
                    "source": "frozen",
                })
        pd.DataFrame(rows).to_csv(processed / "hybrid_benchmark_panel_v1_5.csv", index=False)

    def fetchers(self, new_date="2026-07-13", stocks_have_new=True, fail_code=None, changed_overlap=False):
        def stock(code, start, end):
            if code == fail_code:
                raise RuntimeError("fixture endpoint failure")
            number = int(code)
            overlap = 10 + number / 100 + 0.1 + (1 if changed_overlap and code == "000001" else 0)
            dates, closes = [start], [overlap]
            if stocks_have_new:
                dates.append(new_date)
                closes.append(overlap + 0.1)
            return pd.DataFrame({"date": dates, "close": closes})

        def benchmark(code, start, end):
            number = self.benchmarks.index(code) + 1
            return pd.DataFrame({"date": [start, new_date], "close": [1000 + number + 1, 1000 + number + 2]})

        return stock, benchmark

    def prepare_ok(self, root: Path, run_id: str, new_date="2026-07-13", stocks_have_new=True):
        stock, benchmark = self.fetchers(new_date, stocks_have_new)
        return prepare(
            root, new_date, True, stock, stock, benchmark, benchmark, refresh_run_id=run_id
        )

    def continuity_fixture(self, root: Path, code="002230", scale=1.0023207240659):
        overlap_dates = pd.bdate_range("2026-06-25", "2026-07-10")
        refreshed = [43.09] * len(overlap_dates)
        frozen = [43.19] * len(overlap_dates)
        frame = pd.DataFrame({
            "stock_code": code,
            "trade_date": [*overlap_dates.strftime("%Y-%m-%d"), "2026-07-13"],
            "qfq_close": [*refreshed, 41.90],
            "source_qfq": "ak.stock_zh_a_daily",
        })
        parent = pd.DataFrame({
            "stock_code": code, "trade_date": overlap_dates,
            "qfq_close": frozen, "source_qfq": "frozen",
            "adjusted_close": frozen, "adjusted_flag": True,
        })
        evidence_dir = root / "evidence"
        evidence_dir.mkdir(parents=True)
        evidence_paths = {}
        for name in ("action.csv", "factor_raw.csv", "factor_normalized.csv", "report.md"):
            path = evidence_dir / name
            path.write_text(name + "\n", encoding="utf-8")
            evidence_paths[name] = path
        values = {
            "stock_code": code,
            "continuity_segment_id": f"{code}_segment",
            "frozen_anchor_date": "2026-07-10",
            "new_segment_start_date": "2026-07-13",
            "approved_overlap_start_date": "2026-06-25",
            "approved_overlap_end_date": "2026-07-10",
            "bridge_type": "explicit_factor_bridge",
            "bridge_parameter": str(scale),
            "old_frozen_factor": "1.0",
            "current_refreshed_factor": "1.0023207240659",
            "factor_definition": "QFQ=raw/qfq_factor",
            "factor_direction": "current_refreshed_factor/old_frozen_factor",
            "factor_effective_date": "2025-07-04",
            "next_factor_effective_date": "2026-07-13",
            "guard_mode": "no_later_factor_or_corporate_action",
            "primary_qfq_source": "ak.stock_zh_a_daily",
            "independent_raw_source": "tencent",
            "cash_per_share": "0.1",
            "record_date": "2026-07-10",
            "ex_date": "2026-07-13",
            "official_action_path": str(evidence_paths["action.csv"].relative_to(root)),
            "official_action_sha256": sha256(evidence_paths["action.csv"]),
            "factor_raw_path": str(evidence_paths["factor_raw.csv"].relative_to(root)),
            "factor_raw_sha256": sha256(evidence_paths["factor_raw.csv"]),
            "factor_normalized_path": str(evidence_paths["factor_normalized.csv"].relative_to(root)),
            "factor_version_sha256": sha256(evidence_paths["factor_normalized.csv"]),
            "forensic_report_path": str(evidence_paths["report.md"].relative_to(root)),
            "forensic_report_sha256": sha256(evidence_paths["report.md"]),
            "evidence_status": "confirmed", "approval_status": "approved",
            "approved_by": "fixture_user", "approved_at": "2026-07-14T00:00:00Z",
            "qfq_display_decimals": "2", "raw_display_decimals": "2",
            "factor_decimal_places": "13", "bridge_parameter_decimal_places": "13",
            "notes": "fixture",
        }
        row = pd.Series(values).reindex(CONTINUITY_COLUMNS)
        raw = pd.DataFrame({"trade_date": ["2026-07-10", "2026-07-13"], "raw_close": [43.19, 41.90]})
        evidence = {
            "primary_raw_response": raw.copy(), "primary_raw": raw.copy(),
            "independent_raw_response": raw.copy(), "independent_raw": raw.copy(),
            "factor_response": pd.DataFrame(),
            "factor": pd.DataFrame({
                "trade_date": ["2025-07-04", "2026-07-13"],
                "qfq_factor": [1.0023207240659, 1.0],
            }),
            "actions_response": pd.DataFrame(),
            "actions": pd.DataFrame({
                "record_date": ["2026-07-10"], "ex_date": ["2026-07-13"],
                "cash_dividend_per_10": [1.0],
            }),
        }
        return frame, parent, row, evidence

    def test_run_ids_are_unique_and_well_formed(self):
        first, second = new_run_id(), new_run_id()
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^\d{8}T\d{12}Z_[0-9a-f]{8}$")

    def test_prepare_writes_immutable_candidate_with_parent_prefix(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            code, run_id = self.prepare_ok(root, "run_one")
            self.assertEqual((code, run_id), (0, "run_one"))
            target = run_dir(root, run_id)
            parent = root / "data/processed/adjusted_price_panel_v1_5.csv"
            candidate = target / "processed/adjusted_price_panel_prospective_v1_5_1.csv"
            self.assertTrue(candidate.read_bytes().startswith(parent.read_bytes()))
            self.assertEqual(len(pd.read_csv(target / "manifest.csv")), 59)
            with self.assertRaises(ValueError):
                self.prepare_ok(root, "run_one")
            slice_path = target / "slices/stocks/000001.csv"
            slice_path.write_bytes(slice_path.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                self.approve(root, run_id)

    def test_success_no_new_rows_is_not_suspension(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            code, run_id = self.prepare_ok(root, "no_stock_rows", stocks_have_new=False)
            self.assertEqual(code, 0)
            manifest = pd.read_csv(run_dir(root, run_id) / "manifest.csv", dtype=str)
            stock_status = manifest.loc[manifest["asset_type"].eq("stock"), "status"]
            self.assertTrue(stock_status.eq("success_no_new_rows").all())
            report = (run_dir(root, run_id) / "refresh_qa.md").read_text(encoding="utf-8").lower()
            self.assertNotIn("confirmed_suspension", report)

    def test_overlap_change_and_partial_failure_block_publication(self):
        for run_id, changed, failed in (("changed", True, None), ("failed", False, "000001")):
            with self.subTest(run_id=run_id), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                self.project(root)
                stock, benchmark = self.fetchers(changed_overlap=changed, fail_code=failed)
                code, _ = prepare(root, "2026-07-13", True, stock, stock, benchmark, benchmark, refresh_run_id=run_id)
                self.assertEqual(code, 2)
                with self.assertRaises(ValueError):
                    self.approve(root, run_id)
                self.assertTrue(read_approvals(root).empty)

    def test_invalid_endpoint_rows_and_new_precutoff_rows_are_rejected(self):
        cases = ("duplicate", "nonpositive", "qfq_conflict", "precutoff")
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                self.project(root)
                good_stock, benchmark = self.fetchers()
                def stock(code, start, end):
                    frame = good_stock(code, start, end)
                    if code != "000001":
                        return frame
                    if case == "duplicate":
                        return pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
                    if case == "nonpositive":
                        frame.loc[0, "close"] = 0
                    elif case == "qfq_conflict":
                        frame = frame.rename(columns={"close": "qfq_close"})
                        frame["adjusted_close"] = frame["qfq_close"] + 1
                    else:
                        frame = pd.concat([pd.DataFrame({"date": ["2026-07-08"], "close": [9.0]}), frame], ignore_index=True)
                    return frame
                code, _ = prepare(root, "2026-07-13", True, stock, stock, benchmark, benchmark, refresh_run_id=case)
                self.assertEqual(code, 2)

    def test_no_calendar_advancement_is_valid_nonpublishable_run(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            code, run_id = prepare(root, "2026-07-10", True, refresh_run_id="waiting")
            self.assertEqual(code, 1)
            target = run_dir(root, run_id)
            self.assertTrue((target / "manifest.csv").exists())
            self.assertTrue((target / "failures.csv").exists())
            with self.assertRaises(ValueError):
                self.approve(root, run_id)

    def test_fallback_succeeds_after_primary_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            stock, benchmark = self.fetchers()
            def primary(*args):
                raise RuntimeError("primary unavailable")
            code, run_id = prepare(root, "2026-07-13", True, primary, stock, primary, benchmark, refresh_run_id="fallback")
            self.assertEqual(code, 0)
            manifest = pd.read_csv(run_dir(root, run_id) / "manifest.csv", dtype=str)
            self.assertTrue(manifest["fallback_attempted"].str.lower().eq("true").all())
            self.assertTrue(manifest["status"].eq("primary_failed_fallback_succeeded").all())

    def test_publish_appends_ledger_and_caches_then_chains_parent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            frozen = {
                path: path.read_bytes() for path in (
                    root / "data/processed/adjusted_price_panel_v1_5.csv",
                    root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
                    root / "data/processed/research_universe_lowvol_freeze_20260711.csv",
                )
            }
            self.prepare_ok(root, "first")
            self.assertEqual(self.approve(root, "first"), 0)
            cache = root / "data/cache/prospective_lowvol_v1_5_1/stocks/000001.csv"
            cache_prefix = cache.read_bytes()
            first_panel = run_dir(root, "first") / "processed/adjusted_price_panel_prospective_v1_5_1.csv"
            first_prefix = first_panel.read_bytes()
            stock, benchmark = self.fetchers("2026-07-14")
            # The second overlap must match the first approved prospective close.
            def second_stock(code, start, end):
                frame = stock(code, start, end)
                frame.loc[0, "close"] = 10 + int(code) / 100 + 0.2
                return frame
            def second_benchmark(code, start, end):
                frame = benchmark(code, start, end)
                frame.loc[0, "close"] = 1000 + self.benchmarks.index(code) + 3
                return frame
            code, _ = prepare(root, "2026-07-14", True, second_stock, second_stock, second_benchmark, second_benchmark, refresh_run_id="second")
            self.assertEqual(code, 0)
            second_panel = run_dir(root, "second") / "processed/adjusted_price_panel_prospective_v1_5_1.csv"
            self.assertTrue(second_panel.read_bytes().startswith(first_prefix))
            self.assertEqual(self.approve(root, "second"), 0)
            self.assertTrue(cache.read_bytes().startswith(cache_prefix))
            self.assertEqual(read_approvals(root)["refresh_run_id"].tolist(), ["first", "second"])
            self.assertTrue(all(path.read_bytes() == content for path, content in frozen.items()))
            with self.assertRaises(ValueError):
                self.approve(root, "second")

    def test_only_latest_approved_refresh_resolves(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            self.prepare_ok(root, "first")
            self.approve(root, "first")
            price, benchmark, cutoff = resolve_approved_refresh(root, "first")
            self.assertTrue(price.exists() and benchmark.exists())
            self.assertEqual(cutoff, "2026-07-13")
            cache = root / "data/cache/prospective_lowvol_v1_5_1/stocks/000001.csv"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text("deliberately,different\n", encoding="utf-8")
            resolved_price, resolved_benchmark, _ = resolve_approved_refresh(root, "first")
            self.assertEqual(resolved_price, price)
            self.assertEqual(resolved_benchmark, benchmark)
            with self.assertRaises(ValueError):
                resolve_approved_refresh(root, "missing")

    def test_technical_qa_without_approval_cannot_be_resolved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            code, run_id = self.prepare_ok(root, "prepared_only")
            self.assertEqual(code, 0)
            qa = pd.read_csv(run_dir(root, run_id) / "refresh_qa.csv")
            self.assertTrue(bool(qa.iloc[0]["observe_allowed"]))
            with self.assertRaises(ValueError):
                resolve_approved_refresh(root, run_id)

    def test_publish_requires_human_identity_and_notes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            self.prepare_ok(root, "approval_fields")
            with self.assertRaises(ValueError):
                publish(root, "approval_fields", True, "", "")

    def test_confirmed_pending_segment_cannot_activate(self):
        row = pd.Series({column: "" for column in CONTINUITY_COLUMNS})
        row.update({
            "stock_code": "002230", "continuity_segment_id": "pending",
            "new_segment_start_date": "2026-07-13", "evidence_status": "confirmed",
            "approval_status": "pending",
        })
        with self.assertRaisesRegex(ValueError, "not approved"):
            approved_segment(pd.DataFrame([row], columns=CONTINUITY_COLUMNS), "002230", pd.Timestamp("2026-07-13"))

    def test_correct_factor_bridge_maps_only_post_cutoff_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frame, parent, row, evidence = self.continuity_fixture(root)
            new, qa = apply_continuity_bridge(
                root, root / "run", frame, parent, row, "ak.stock_zh_a_daily",
                pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-13"), lambda *args: evidence,
            )
            self.assertEqual(qa["overlap_count"], 12)
            self.assertEqual(qa["overlap_failure_count"], 0)
            self.assertTrue(qa["raw_identity_pass"] and qa["corporate_action_return_pass"])
            self.assertEqual(new["trade_date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-07-13"])
            self.assertAlmostEqual(new.iloc[0]["qfq_close"], 41.90 * 1.0023207240659)
            self.assertEqual(parent.iloc[-1]["qfq_close"], 43.19)

    def test_002044_stable_rescaling_uses_independent_raw_economics(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frame, parent, row, evidence = self.continuity_fixture(root, code="002044", scale=1.0020183299389003)
            frame.loc[frame["trade_date"].ne("2026-07-13"), "qfq_close"] = 4.63
            frame.loc[frame["trade_date"].eq("2026-07-13"), "qfq_close"] = 4.34
            parent["qfq_close"] = parent["adjusted_close"] = 4.64
            row.update({
                "bridge_type": "stable_empirical_rescaling", "bridge_parameter": "1.0020183299389003",
                "current_refreshed_factor": "1.0019434247463", "cash_per_share": "0.009",
                "bridge_parameter_decimal_places": "16",
            })
            evidence["primary_raw"] = pd.DataFrame(columns=["trade_date", "raw_close"])
            evidence["factor"] = pd.DataFrame({
                "trade_date": ["2025-07-04", "2026-07-13"],
                "qfq_factor": [1.0019434247463, 1.0],
            })
            evidence["independent_raw"] = pd.DataFrame({
                "trade_date": ["2026-07-10", "2026-07-13"], "raw_close": [4.64, 4.34],
            })
            evidence["actions"] = pd.DataFrame({
                "record_date": ["2026-07-10"], "ex_date": ["2026-07-13"],
                "cash_dividend_per_10": [0.09],
            })
            new, qa = apply_continuity_bridge(
                root, root / "run", frame, parent, row, "ak.stock_zh_a_daily",
                pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-13"), lambda *args: evidence,
            )
            self.assertEqual(qa["overlap_count"], 12)
            self.assertTrue(qa["corporate_action_return_pass"] and qa["independent_raw_pass"])
            self.assertAlmostEqual(new.iloc[0]["qfq_close"], 4.34 * 1.0020183299389003)

    def test_inverse_factor_direction_and_hash_mismatch_fail(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frame, parent, row, evidence = self.continuity_fixture(root, scale=1 / 1.0023207240659)
            with self.assertRaisesRegex(ValueError, "overlap reconstruction"):
                apply_continuity_bridge(
                    root, root / "inverse", frame, parent, row, "ak.stock_zh_a_daily",
                    pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-13"), lambda *args: evidence,
                )
            row["bridge_parameter"] = "1.0023207240659"
            for field in ("factor_raw_sha256", "factor_version_sha256"):
                with self.subTest(field=field):
                    changed = row.copy()
                    changed[field] = "0" * 64
                    with self.assertRaisesRegex(ValueError, "hash mismatch"):
                        apply_continuity_bridge(
                            root, root / ("hash_" + field), frame, parent, changed, "ak.stock_zh_a_daily",
                            pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-13"), lambda *args: evidence,
                        )

    def test_segment_identity_approval_and_date_are_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frame, parent, row, evidence = self.continuity_fixture(root)
            registry = pd.DataFrame([row], columns=CONTINUITY_COLUMNS)
            self.assertIsNone(approved_segment(registry, "002044", pd.Timestamp("2026-07-13")))
            self.assertIsNone(approved_segment(registry, "002230", pd.Timestamp("2026-07-12")))
            row["approved_by"] = ""
            with self.assertRaisesRegex(ValueError, "identity"):
                approved_segment(pd.DataFrame([row], columns=CONTINUITY_COLUMNS), "002230", pd.Timestamp("2026-07-13"))
            row["approved_by"] = "fixture_user"
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                apply_continuity_bridge(
                    root, root / "wrong_source", frame, parent, row, "ak.stock_zh_a_hist",
                    pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-13"), lambda *args: evidence,
                )

    def test_prepare_applies_one_approved_bridge_end_to_end(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.project(root)
            pd.DataFrame({"code": [*self.codes[:-1], "002230"]}).to_csv(
                root / "data/processed/research_universe_lowvol_freeze_20260711.csv", index=False
            )
            bridge_frame, bridge_parent, row, evidence = self.continuity_fixture(root)
            bridge_parent["trade_date"] = pd.to_datetime(bridge_parent["trade_date"]).dt.strftime("%Y-%m-%d")
            panel_path = root / "data/processed/adjusted_price_panel_v1_5.csv"
            panel = pd.read_csv(panel_path, dtype={"stock_code": str})
            panel = pd.concat([
                panel[panel["stock_code"].ne("002230")], bridge_parent,
            ], ignore_index=True)
            panel.to_csv(panel_path, index=False)
            registry_path = root / "registry.csv"
            pd.DataFrame([row], columns=CONTINUITY_COLUMNS).to_csv(registry_path, index=False)
            regular_stock, benchmark = self.fetchers()

            def stock(code, start, end):
                if code == "002230":
                    return bridge_frame[["trade_date", "qfq_close"]].rename(
                        columns={"trade_date": "date", "qfq_close": "close"}
                    )
                return regular_stock(code, start, end)

            code, run_id = prepare(
                root, "2026-07-13", True, stock, stock, benchmark, benchmark,
                refresh_run_id="bridged", continuity_registry=registry_path,
                continuity_evidence_fetcher=lambda *args: evidence,
            )
            failure_text = "\n".join(
                (run_dir(root, run_id) / name).read_text(encoding="utf-8")
                for name in ("failures.csv", "continuity_bridges.csv", "refresh_qa.csv")
            )
            self.assertEqual((code, run_id), (0, "bridged"), failure_text)
            run = run_dir(root, run_id)
            bridge_qa = pd.read_csv(run / "continuity_bridges.csv")
            self.assertEqual(bridge_qa["status"].tolist(), ["applied"])
            qa = pd.read_csv(run / "refresh_qa.csv").iloc[0]
            self.assertEqual((qa["continuity_approved_count"], qa["continuity_applied_count"]), (1, 1))
            self.assertTrue(bool(qa["critical_qa_pass"]))
            candidate = run / "processed/adjusted_price_panel_prospective_v1_5_1.csv"
            self.assertTrue(candidate.read_bytes().startswith(panel_path.read_bytes()))

    def test_later_factor_or_action_requires_new_segment(self):
        for kind in ("factor", "action"):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frame, parent, row, evidence = self.continuity_fixture(root)
                if kind == "factor":
                    evidence["factor"] = pd.concat([
                        evidence["factor"],
                        pd.DataFrame({"trade_date": ["2026-07-14"], "qfq_factor": [0.99]}),
                    ], ignore_index=True)
                else:
                    evidence["actions"] = pd.concat([
                        evidence["actions"],
                        pd.DataFrame({
                            "record_date": ["2026-07-13"], "ex_date": ["2026-07-14"],
                            "cash_dividend_per_10": [0.1],
                        }),
                    ], ignore_index=True)
                with self.assertRaisesRegex(ValueError, "Later"):
                    apply_continuity_bridge(
                        root, root / kind, frame, parent, row, "ak.stock_zh_a_daily",
                        pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-14"), lambda *args: evidence,
                    )


if __name__ == "__main__":
    unittest.main()
