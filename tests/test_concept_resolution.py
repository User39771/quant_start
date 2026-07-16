from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from aq_factor_lab.data_collection.concept_resolution import resolve_stock_concepts
from scripts.resolve_stock_concepts import main


class ConceptResolutionTests(unittest.TestCase):
    def test_exact_match_fetches_member_count(self):
        stock_candidates = pd.DataFrame(
            {
                "theme": ["AI"],
                "candidate_concept_name": ["人工智能"],
            }
        )
        concept_names = pd.DataFrame(
            {
                "板块名称": ["人工智能"],
                "板块代码": ["BK0800"],
            }
        )
        calls: list[str] = []

        result = resolve_stock_concepts(
            stock_candidates,
            concept_names,
            fetch_members=lambda name: calls.append(name)
            or pd.DataFrame({"代码": ["000001", "600519"]}),
        )

        self.assertEqual(calls, ["BK0800"])
        self.assertTrue(result.failures.empty)
        self.assertEqual(result.resolved.loc[0, "status"], "matched")
        self.assertEqual(result.resolved.loc[0, "matched_concept_name"], "人工智能")
        self.assertEqual(result.resolved.loc[0, "matched_concept_code"], "BK0800")
        self.assertEqual(result.resolved.loc[0, "rows"], 2)
        self.assertEqual(result.resolved.loc[0, "fuzzy_candidates"], "")

    def test_missing_exact_match_records_fuzzy_direction_without_fetching_members(self):
        stock_candidates = pd.DataFrame(
            {
                "theme": ["AI"],
                "candidate_concept_name": ["算力租赁"],
            }
        )
        concept_names = pd.DataFrame(
            {
                "板块名称": ["算力概念", "数据中心", "东数西算"],
                "板块代码": ["BK1", "BK2", "BK3"],
            }
        )
        calls: list[str] = []

        result = resolve_stock_concepts(
            stock_candidates,
            concept_names,
            fetch_members=lambda name: calls.append(name) or pd.DataFrame(),
            fuzzy_cutoff=0.45,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.resolved.loc[0, "status"], "fuzzy_candidates")
        self.assertIn("算力概念", result.resolved.loc[0, "fuzzy_candidates"])
        self.assertIn("remove_suffix", result.resolved.loc[0, "fuzzy_query_direction"])

    def test_member_fetch_failure_is_recorded(self):
        stock_candidates = pd.DataFrame(
            {
                "theme": ["商业航天"],
                "candidate_concept_name": ["商业航天"],
            }
        )
        concept_names = pd.DataFrame(
            {
                "板块名称": ["商业航天"],
                "板块代码": ["BKSPACE"],
            }
        )

        def fetch_members(_name: str) -> pd.DataFrame:
            raise RuntimeError("blocked")

        result = resolve_stock_concepts(stock_candidates, concept_names, fetch_members=fetch_members)

        self.assertEqual(result.resolved.loc[0, "status"], "matched_rows_failed")
        self.assertEqual(result.resolved.loc[0, "rows"], "")
        self.assertEqual(result.failures.loc[0, "stage"], "concept_members")
        self.assertEqual(result.failures.loc[0, "concept_name"], "商业航天")
        self.assertEqual(result.failures.loc[0, "error_type"], "RuntimeError")

    def test_cli_records_concept_list_fetch_failure(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "stocks.csv"
            output_path = root / "resolved.csv"
            failure_path = root / "failures.csv"
            pd.DataFrame({"candidate_concept_name": ["人工智能"]}).to_csv(
                input_path,
                index=False,
                encoding="utf-8-sig",
            )

            with patch("scripts.resolve_stock_concepts.AkSharePublicClient") as client_class:
                client_class.return_value.concept_names.side_effect = RuntimeError("blocked")

                exit_code = main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--failures",
                        str(failure_path),
                        "--concept-source",
                        "em",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse(output_path.exists())
            failures = pd.read_csv(failure_path)
            self.assertEqual(failures.loc[0, "stage"], "concept_names")
            self.assertEqual(failures.loc[0, "error_type"], "RuntimeError")

    def test_cli_auto_falls_back_to_ths_concept_names(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "stocks.csv"
            output_path = root / "resolved.csv"
            failure_path = root / "failures.csv"
            pd.DataFrame({"candidate_concept_name": ["AI PC"]}).to_csv(
                input_path,
                index=False,
                encoding="utf-8-sig",
            )

            with (
                patch("scripts.resolve_stock_concepts.AkSharePublicClient") as client_class,
                patch("scripts.resolve_stock_concepts.ak") as ak_module,
            ):
                client_class.return_value.concept_names.side_effect = RuntimeError("em blocked")
                ak_module.stock_board_concept_name_ths.return_value = pd.DataFrame(
                    [{"name": "AI PC", "code": "309121"}]
                )

                exit_code = main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--failures",
                        str(failure_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            resolved = pd.read_csv(output_path)
            self.assertEqual(resolved.loc[0, "status"], "matched")
            self.assertEqual(str(resolved.loc[0, "matched_concept_code"]), "309121")
            self.assertEqual(resolved.loc[0, "resolved_source"], "akshare.stock_board_concept_name_ths")
            self.assertEqual(str(resolved.loc[0, "rows"]), "nan")
            failures = pd.read_csv(failure_path)
            self.assertEqual(failures.loc[0, "stage"], "concept_names_em")


if __name__ == "__main__":
    unittest.main()
