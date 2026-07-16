from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from aq_factor_lab.theme_concepts import (
    REQUIRED_MAPPING_COLUMNS,
    apply_manual_overrides,
    build_business_materiality_diagnostics,
    build_constituent_table,
    build_high_confidence_business_mismatch_queue,
    build_stock_business_profile_template,
    build_theme_stock_purity_diagnostics,
    build_theme_stock_review_queue,
    build_theme_stock_universe,
    clean_concept_mapping,
    load_manual_overrides,
    load_purity_rules,
    load_stock_business_profiles,
    load_stock_overrides,
    normalize_stock_code,
    select_validated_concepts,
    validate_akshare_concepts,
)
from scripts.build_theme_concept_universe import main as build_universe_main
from scripts.validate_akshare_concepts import main as validate_concepts_main


def mapping_frame(**overrides) -> pd.DataFrame:
    row = {
        "theme": " AI ",
        "source_priority": "1",
        "source_id": "AI02",
        "source_title": "Policy",
        "source_type": "official_policy",
        "source_org": "Org",
        "source_date": "2024/07/03",
        "source_url": "https://example.com/a",
        "official_or_market_term": "AI",
        "industry_chain_layer": " core ",
        "possible_akshare_concept": " 人工智能 ",
        "ring": " p0 ",
        "include_default": " YES ",
        "evidence_summary": " Evidence ",
        "risk_note": " Risk ",
        "input_reason": " Reason ",
        "akshare_next_step": "Validate",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def concept_names() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "concept_code": ["BK0800", "BK0810", "BKSPACE"],
            "concept_name": ["人工智能", "算力租赁", "商业航天"],
        }
    )


class ThemeConceptTests(unittest.TestCase):
    def test_clean_mapping_requires_columns_and_preserves_evidence(self):
        missing = mapping_frame().drop(columns=["source_url"])

        with self.assertRaises(ValueError):
            clean_concept_mapping(missing, input_file="manual.csv", generated_at="2026-06-28T00:00:00Z")

        clean, warnings = clean_concept_mapping(
            mapping_frame(),
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )

        self.assertTrue(warnings.empty)
        self.assertEqual(clean.loc[0, "mapping_row_id"], 1)
        self.assertEqual(clean.loc[0, "theme"], "AI")
        self.assertEqual(clean.loc[0, "ring"], "P0")
        self.assertEqual(clean.loc[0, "include_default"], "yes")
        self.assertEqual(clean.loc[0, "source_date"], "2024-07-03")
        self.assertEqual(clean.loc[0, "evidence_summary"], "Evidence")
        self.assertEqual(clean.loc[0, "risk_note"], "Risk")
        self.assertEqual(clean.loc[0, "input_reason"], "Reason")
        self.assertEqual(clean.loc[0, "input_file"], "manual.csv")

    def test_invalid_ring_and_include_default_are_auditable_but_invalid(self):
        clean, warnings = clean_concept_mapping(
            mapping_frame(ring="P3", include_default="maybe"),
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )

        self.assertFalse(warnings.empty)
        self.assertIn("invalid_ring", clean.loc[0, "validation_warning"])
        self.assertIn("invalid_include_default", clean.loc[0, "validation_warning"])
        validation = validate_akshare_concepts(
            clean,
            concept_names(),
            generated_at="2026-06-28T00:00:00Z",
            input_file="manual.csv",
            refresh=False,
            akshare_cache_status="cache_hit",
        ).resolved

        self.assertEqual(validation.loc[0, "match_status"], "invalid_input")
        self.assertEqual(validation.loc[0, "action_required"], "fix_invalid_input")

    def test_duplicate_source_rows_are_preserved_in_clean_mapping(self):
        raw = pd.concat([mapping_frame(), mapping_frame(input_reason="Second reason")], ignore_index=True)

        clean, _warnings = clean_concept_mapping(
            raw,
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )

        self.assertEqual(len(clean), 2)
        self.assertEqual(clean["mapping_row_id"].tolist(), [1, 2])
        self.assertEqual(clean.loc[1, "input_reason"], "Second reason")

    def test_exact_and_fuzzy_matches_do_not_auto_confirm_fuzzy(self):
        clean_exact, _ = clean_concept_mapping(
            mapping_frame(possible_akshare_concept="人工智能"),
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )
        clean_fuzzy, _ = clean_concept_mapping(
            mapping_frame(possible_akshare_concept="算力概念"),
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )
        clean = pd.concat([clean_exact, clean_fuzzy], ignore_index=True)

        validation = validate_akshare_concepts(
            clean,
            concept_names(),
            generated_at="2026-06-28T00:00:00Z",
            input_file="manual.csv",
            refresh=True,
            akshare_cache_status="refreshed",
            fuzzy_cutoff=0.45,
        ).resolved

        self.assertEqual(validation.loc[0, "match_status"], "exact")
        self.assertEqual(validation.loc[0, "matched_akshare_concept"], "人工智能")
        self.assertEqual(validation.loc[0, "match_score"], 1.0)
        self.assertEqual(validation.loc[1, "match_status"], "fuzzy_candidate")
        self.assertEqual(validation.loc[1, "matched_akshare_concept"], "")
        self.assertIn("算力租赁", validation.loc[1, "fuzzy_candidates"])
        self.assertEqual(validation.loc[1, "action_required"], "review_fuzzy_candidates")

    def test_manual_overrides_confirm_and_reject_without_editing_generated_files(self):
        clean, _ = clean_concept_mapping(
            pd.concat(
                [
                    mapping_frame(possible_akshare_concept="算力概念"),
                    mapping_frame(possible_akshare_concept="大模型"),
                ],
                ignore_index=True,
            ),
            input_file="manual.csv",
            generated_at="2026-06-28T00:00:00Z",
        )
        validation = validate_akshare_concepts(
            clean,
            concept_names(),
            generated_at="2026-06-28T00:00:00Z",
            input_file="manual.csv",
            refresh=False,
            akshare_cache_status="cache_hit",
            fuzzy_cutoff=0.45,
        ).resolved
        overrides = pd.DataFrame(
            [
                {
                    "theme": "AI",
                    "possible_akshare_concept": "算力概念",
                    "override_action": "confirm",
                    "matched_akshare_concept": "算力租赁",
                    "matched_akshare_code": "BK0810",
                    "override_reason": "Manual review",
                },
                {
                    "theme": "AI",
                    "possible_akshare_concept": "大模型",
                    "override_action": "reject",
                    "matched_akshare_concept": "",
                    "matched_akshare_code": "",
                    "override_reason": "No EM board",
                },
            ]
        )

        out = apply_manual_overrides(validation, overrides)

        self.assertEqual(out.loc[0, "match_status"], "manual_confirmed")
        self.assertEqual(out.loc[0, "matched_akshare_concept"], "算力租赁")
        self.assertEqual(out.loc[0, "manual_override_reason"], "Manual review")
        self.assertEqual(out.loc[1, "match_status"], "manual_rejected")
        self.assertEqual(out.loc[1, "action_required"], "manual_override_rejected")

    def test_missing_override_file_is_allowed_and_present_file_is_validated(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "theme_concept_overrides.csv"
            self.assertTrue(load_manual_overrides(missing).empty)

            path = Path(tmp) / "theme_concept_overrides.csv"
            pd.DataFrame(
                [
                    {
                        "theme": "AI",
                        "possible_akshare_concept": "算力概念",
                        "override_action": "confirm",
                        "matched_akshare_concept": "算力租赁",
                        "matched_akshare_code": "BK0810",
                        "override_reason": "Manual review",
                    }
                ]
            ).to_csv(path, index=False, encoding="utf-8-sig")

            overrides = load_manual_overrides(path)

        self.assertEqual(overrides.loc[0, "override_action"], "confirm")

    def test_selection_defaults_and_flags(self):
        rows = []
        for concept, ring, include_default, status in [
            ("人工智能", "P0", "yes", "exact"),
            ("DeepSeek概念", "P0", "conditional", "exact"),
            ("半导体材料", "P2", "no", "exact"),
            ("大模型", "P0", "yes", "fuzzy_candidate"),
            ("算力租赁", "P1", "yes", "manual_confirmed"),
        ]:
            base = mapping_frame(
                possible_akshare_concept=concept,
                ring=ring,
                include_default=include_default,
            )
            clean, _ = clean_concept_mapping(
                base,
                input_file="manual.csv",
                generated_at="2026-06-28T00:00:00Z",
            )
            row = clean.iloc[0].to_dict()
            row.update(
                {
                    "match_status": status,
                    "matched_akshare_concept": concept,
                    "matched_akshare_code": f"BK{len(rows)}",
                }
            )
            rows.append(row)
        validation = pd.DataFrame(rows)

        default = select_validated_concepts(validation, default_only=True)
        conditional = select_validated_concepts(validation, include_conditional=True)
        audit = select_validated_concepts(
            validation,
            default_only=False,
            include_conditional=True,
            include_p2=True,
            include_excluded_for_audit=True,
            rings=["P0", "P1", "P2"],
        )

        self.assertEqual(default["possible_akshare_concept"].tolist(), ["人工智能"])
        self.assertIn("DeepSeek概念", set(conditional["possible_akshare_concept"]))
        self.assertIn("半导体材料", set(audit["possible_akshare_concept"]))
        self.assertNotIn("大模型", set(audit["possible_akshare_concept"]))

    def test_dry_run_and_max_concepts_selection(self):
        validation = pd.DataFrame(
            [
                {
                    "theme": "AI",
                    "possible_akshare_concept": name,
                    "matched_akshare_concept": name,
                    "matched_akshare_code": code,
                    "match_status": "exact",
                    "ring": "P0",
                    "include_default": "yes",
                    "source_type": "official_policy",
                    "source_id": f"S{idx}",
                    "source_url": "https://example.com",
                    "evidence_summary": "Evidence",
                    "risk_note": "Risk",
                    "industry_chain_layer": "core",
                }
                for idx, (name, code) in enumerate([("人工智能", "BK1"), ("商业航天", "BK2")], start=1)
            ]
        )

        selected = select_validated_concepts(validation, max_concepts=1)
        constituents, failures = build_constituent_table(
            selected,
            fetch_members=lambda _name: pd.DataFrame({"raw_code": ["600519"], "name": ["贵州茅台"]}),
            dry_run=True,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )

        self.assertEqual(selected["matched_akshare_concept"].tolist(), ["人工智能"])
        self.assertTrue(failures.empty)
        self.assertTrue(constituents.empty)

    def test_raw_code_preserved_and_code_normalized(self):
        self.assertEqual(normalize_stock_code("SZ300750"), "300750")
        self.assertEqual(normalize_stock_code("1"), "000001")

        validation = pd.DataFrame(
            [
                {
                    "theme": "AI",
                    "possible_akshare_concept": "人工智能",
                    "matched_akshare_concept": "人工智能",
                    "matched_akshare_code": "BK1",
                    "match_status": "exact",
                    "ring": "P0",
                    "include_default": "yes",
                    "source_type": "official_policy",
                    "source_id": "AI02",
                    "source_url": "https://example.com",
                    "evidence_summary": "Evidence",
                    "risk_note": "Risk",
                    "industry_chain_layer": "core",
                }
            ]
        )

        constituents, failures = build_constituent_table(
            validation,
            fetch_members=lambda _name: pd.DataFrame({"代码": ["SZ300750"], "名称": ["宁德时代"]}),
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )

        self.assertTrue(failures.empty)
        self.assertEqual(constituents.loc[0, "raw_code"], "SZ300750")
        self.assertEqual(constituents.loc[0, "code"], "300750")
        self.assertEqual(constituents.loc[0, "name"], "宁德时代")

    def test_universe_scoring_is_deterministic_and_deduplicates_source_concept_stock(self):
        constituents = pd.DataFrame(
            [
                {
                    "raw_code": "SZ300750",
                    "code": "300750",
                    "name": "宁德时代",
                    "theme": "AI",
                    "matched_akshare_concept": "人工智能",
                    "original_possible_concept": "人工智能",
                    "ring": "P0",
                    "include_default": "yes",
                    "industry_chain_layer": "core",
                    "source_id": "AI02",
                    "source_url": "https://example.com/a",
                    "concept_source_weight": 3.75,
                    "evidence_summary": "Strong evidence",
                    "risk_note": "Risk A",
                },
                {
                    "raw_code": "SZ300750",
                    "code": "300750",
                    "name": "宁德时代",
                    "theme": "AI",
                    "matched_akshare_concept": "人工智能",
                    "original_possible_concept": "人工智能",
                    "ring": "P0",
                    "include_default": "yes",
                    "industry_chain_layer": "core",
                    "source_id": "AI02",
                    "source_url": "https://example.com/a",
                    "concept_source_weight": 3.75,
                    "evidence_summary": "Duplicate source",
                    "risk_note": "Risk duplicate",
                },
                {
                    "raw_code": "SZ300750",
                    "code": "300750",
                    "name": "宁德时代",
                    "theme": "AI",
                    "matched_akshare_concept": "算力租赁",
                    "original_possible_concept": "算力租赁",
                    "ring": "P1",
                    "include_default": "conditional",
                    "industry_chain_layer": "infrastructure",
                    "source_id": "AI05",
                    "source_url": "https://example.com/b",
                    "concept_source_weight": 1.5,
                    "evidence_summary": "Secondary evidence",
                    "risk_note": "Risk B",
                },
            ]
        )

        universe = build_theme_stock_universe(
            constituents,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )

        self.assertEqual(len(universe), 1)
        self.assertEqual(universe.loc[0, "matched_concept_count"], 2)
        self.assertEqual(universe.loc[0, "p0_concept_count"], 1)
        self.assertEqual(universe.loc[0, "p1_concept_count"], 1)
        self.assertEqual(universe.loc[0, "concept_exposure_score"], 5.5)
        self.assertEqual(universe.loc[0, "theme_relevance_score"], 5.5)
        self.assertEqual(universe.loc[0, "universe_inclusion_status"], "default")
        self.assertEqual(universe.loc[0, "verification_status"], "concept_matched")
        self.assertEqual(universe.loc[0, "supporting_source_ids"], "AI02|AI05")
        self.assertEqual(universe.loc[0, "supporting_industry_chain_layers"], "core|infrastructure")

    def test_purity_rules_load_from_config_and_fallback_when_missing(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing_rules.json"
            fallback = load_purity_rules(missing)
            self.assertIn("AI", fallback["broad_concepts"])

            path = Path(tmp) / "theme_concept_purity_rules.json"
            path.write_text(
                """
{
  "broad_concepts": {"AI": ["BroadOnly"]},
  "specific_concepts": {"AI": ["SpecificOnly"]},
  "thresholds": {"low_exposure_score": 2.25, "liquidity_amount_20d": 1000000}
}
""",
                encoding="utf-8",
            )

            rules = load_purity_rules(path)

        self.assertEqual(rules["broad_concepts"]["AI"], ["BroadOnly"])
        self.assertEqual(rules["specific_concepts"]["AI"], ["SpecificOnly"])
        self.assertEqual(rules["thresholds"]["low_exposure_score"], 2.25)

    def test_purity_high_confidence_requires_specific_and_multiple_support(self):
        constituents = pd.DataFrame(
            [
                constituent_row("600001", "Broad A", "S1", weight=3.0),
                constituent_row("600001", "Broad B", "S2", weight=3.0),
                constituent_row("600002", "Broad A", "S1", weight=3.0),
                constituent_row("600002", "Specific A", "S2", weight=3.0),
            ]
        )
        universe = build_theme_stock_universe(
            constituents,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )
        rules = {
            "broad_concepts": {"AI": ["Broad A", "Broad B"]},
            "specific_concepts": {"AI": ["Specific A"]},
            "weak_concept_patterns": [],
            "thresholds": {"low_exposure_score": 2.0, "liquidity_amount_20d": 50000000},
        }

        diagnostics = build_theme_stock_purity_diagnostics(
            universe,
            constituents,
            purity_rules=rules,
            stock_overrides=pd.DataFrame(),
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"input_file": "constituents.csv"},
        ).sort_values("code").reset_index(drop=True)

        self.assertEqual(diagnostics.loc[0, "code"], "600001")
        self.assertEqual(diagnostics.loc[0, "concept_purity_bucket"], "broad_concept_only")
        self.assertFalse(bool(diagnostics.loc[0, "specific_concept_support"]))
        self.assertEqual(diagnostics.loc[1, "code"], "600002")
        self.assertEqual(diagnostics.loc[1, "concept_purity_bucket"], "high_confidence")
        self.assertTrue(bool(diagnostics.loc[1, "specific_concept_support"]))

    def test_mojibake_diagnostics_route_rows_to_review_without_deleting(self):
        constituents = pd.DataFrame([constituent_row("600003", "Broad A", "S1", name="��ɣ���", weight=3.0)])
        universe = build_theme_stock_universe(
            constituents,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )
        rules = {
            "broad_concepts": {"AI": ["Broad A"]},
            "specific_concepts": {"AI": []},
            "weak_concept_patterns": [],
            "thresholds": {"low_exposure_score": 2.0, "liquidity_amount_20d": 50000000},
        }

        diagnostics = build_theme_stock_purity_diagnostics(
            universe,
            constituents,
            purity_rules=rules,
            stock_overrides=pd.DataFrame(),
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"input_file": "constituents.csv"},
        )

        self.assertEqual(len(diagnostics), 1)
        self.assertTrue(bool(diagnostics.loc[0, "mojibake_flag"]))
        self.assertGreater(diagnostics.loc[0, "mojibake_field_count"], 0)
        self.assertIn("mojibake", diagnostics.loc[0, "encoding_warning"])
        self.assertEqual(diagnostics.loc[0, "concept_purity_bucket"], "needs_manual_review")

    def test_stock_overrides_and_market_readiness_are_separate_from_purity_bucket(self):
        constituents = pd.DataFrame(
            [
                constituent_row("600004", "Broad A", "S1", weight=3.0),
                constituent_row("600004", "Specific A", "S2", weight=3.0),
                constituent_row("600005", "Specific A", "S3", weight=3.0),
            ]
        )
        universe = build_theme_stock_universe(
            constituents,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )
        overrides = pd.DataFrame(
            [
                {
                    "code": "600004",
                    "name": "Alpha",
                    "theme": "AI",
                    "override_status": "watchlist",
                    "reason": "Needs issuer check",
                    "reviewer": "analyst",
                    "review_date": "2026-06-28",
                },
                {
                    "code": "600005",
                    "name": "Beta",
                    "theme": "AI",
                    "override_status": "reject",
                    "reason": "Wrong business",
                    "reviewer": "analyst",
                    "review_date": "2026-06-28",
                },
            ]
        )
        rules = {
            "broad_concepts": {"AI": ["Broad A"]},
            "specific_concepts": {"AI": ["Specific A"]},
            "weak_concept_patterns": [],
            "thresholds": {"low_exposure_score": 2.0, "liquidity_amount_20d": 50000000},
        }

        diagnostics = build_theme_stock_purity_diagnostics(
            universe,
            constituents,
            purity_rules=rules,
            stock_overrides=overrides,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"input_file": "constituents.csv"},
        ).set_index("code")

        self.assertEqual(diagnostics.loc["600004", "concept_purity_bucket"], "needs_manual_review")
        self.assertEqual(diagnostics.loc["600004", "override_status"], "watchlist")
        self.assertEqual(diagnostics.loc["600005", "concept_purity_bucket"], "exclude_candidate")
        self.assertIn("liquidity_pass", diagnostics.columns)
        self.assertNotEqual(diagnostics.loc["600004", "concept_purity_bucket"], diagnostics.loc["600004", "midfreq_ready"])

    def test_stock_overrides_missing_file_allowed_and_invalid_status_rejected(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "theme_stock_overrides.csv"
            self.assertTrue(load_stock_overrides(missing).empty)
            path = Path(tmp) / "theme_stock_overrides.csv"
            pd.DataFrame(
                [
                    {
                        "code": "600004",
                        "name": "Alpha",
                        "theme": "AI",
                        "override_status": "invalid",
                        "reason": "bad",
                        "reviewer": "analyst",
                        "review_date": "2026-06-28",
                    }
                ]
            ).to_csv(path, index=False, encoding="utf-8-sig")

            with self.assertRaises(ValueError):
                load_stock_overrides(path)

    def test_local_price_cache_readiness_and_freshness_metadata(self):
        constituents = pd.DataFrame([constituent_row("600006", "Specific A", "S1", weight=3.0)])
        universe = build_theme_stock_universe(
            constituents,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"refresh": False},
        )
        rules = {
            "broad_concepts": {"AI": []},
            "specific_concepts": {"AI": ["Specific A"]},
            "weak_concept_patterns": [],
            "thresholds": {"low_exposure_score": 2.0, "liquidity_amount_20d": 50000000},
        }
        with TemporaryDirectory() as tmp:
            price_dir = Path(tmp) / "price"
            price_dir.mkdir()
            dates = pd.date_range("2026-06-01", periods=20, freq="D")
            pd.DataFrame(
                {
                    "date": dates.strftime("%Y-%m-%d"),
                    "close": [10 + i * 0.1 for i in range(20)],
                    "amount": [100000000.0] * 20,
                    "high": [11.0] * 20,
                    "low": [9.0] * 20,
                    "total_market_cap": [10000000000.0] * 20,
                    "code": ["600006"] * 20,
                }
            ).to_csv(price_dir / "600006.csv", index=False, encoding="utf-8-sig")

            diagnostics = build_theme_stock_purity_diagnostics(
                universe,
                constituents,
                purity_rules=rules,
                stock_overrides=pd.DataFrame(),
                generated_at="2026-06-28T00:00:00Z",
                run_metadata={"input_file": "constituents.csv"},
                price_cache_dir=price_dir,
            )

        self.assertTrue(bool(diagnostics.loc[0, "liquidity_pass"]))
        self.assertTrue(bool(diagnostics.loc[0, "tradability_pass"]))
        self.assertEqual(diagnostics.loc[0, "price_cache_asof"], "2026-06-20")
        self.assertEqual(diagnostics.loc[0, "price_cache_staleness_days"], 8)
        self.assertEqual(diagnostics.loc[0, "concept_constituents_asof"], "2026-06-28")

    def test_review_queue_prioritizes_broad_low_confidence_and_mojibake(self):
        diagnostics = pd.DataFrame(
            [
                {
                    "code": "600010",
                    "name": "Good",
                    "theme": "AI",
                    "concept_purity_bucket": "high_confidence",
                    "broad_concept_only": False,
                    "matched_concept_count": 2,
                    "concept_exposure_score": 6.0,
                    "mojibake_flag": False,
                    "supporting_concepts": "Specific A",
                },
                {
                    "code": "600011",
                    "name": "Loose",
                    "theme": "AI",
                    "concept_purity_bucket": "broad_concept_only",
                    "broad_concept_only": True,
                    "matched_concept_count": 1,
                    "concept_exposure_score": 1.0,
                    "mojibake_flag": True,
                    "supporting_concepts": "Broad A",
                },
            ]
        )

        queue = build_theme_stock_review_queue(diagnostics)

        self.assertEqual(queue.loc[0, "code"], "600011")
        self.assertEqual(queue.loc[0, "suggested_action"], "review")

    def test_business_profiles_missing_file_schema_and_enums(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "stock_business_profile.csv"
            self.assertTrue(load_stock_business_profiles(missing).empty)

            incomplete = Path(tmp) / "incomplete.csv"
            pd.DataFrame([{"code": "300911"}]).to_csv(incomplete, index=False, encoding="utf-8-sig")
            with self.assertRaises(ValueError):
                load_stock_business_profiles(incomplete)

            invalid = Path(tmp) / "invalid.csv"
            pd.DataFrame(
                [
                    business_profile_row(
                        code="300911",
                        review_status="bad_status",
                        evidence_level="unknown",
                    )
                ]
            ).to_csv(invalid, index=False, encoding="utf-8-sig")
            with self.assertRaises(ValueError):
                load_stock_business_profiles(invalid)

            invalid_evidence = Path(tmp) / "invalid_evidence.csv"
            pd.DataFrame(
                [
                    business_profile_row(
                        code="300911",
                        review_status="unknown",
                        evidence_level="chat_room",
                    )
                ]
            ).to_csv(invalid_evidence, index=False, encoding="utf-8-sig")
            with self.assertRaises(ValueError):
                load_stock_business_profiles(invalid_evidence)

    def test_business_materiality_concept_only_transition_core_and_manual_reject(self):
        purity = pd.DataFrame(
            [
                purity_row("300911", "Kitchen Co", "high_confidence", "AIGC|Computing", 2),
                purity_row("300912", "Transition Co", "high_confidence", "Computing", 2),
                purity_row("300913", "Core AI Co", "medium_confidence", "AI Agent", 1),
                purity_row("300914", "Rejected Co", "high_confidence", "Computing", 2),
                purity_row("", "", "high_confidence", "Computing", 1),
            ]
        )
        profiles = pd.DataFrame(
            [
                business_profile_row(
                    code="300911",
                    name="Kitchen Co",
                    primary_business="integrated kitchen appliances",
                    sw_industry="home appliances",
                    theme_business_description="",
                    theme_revenue_materiality="unknown",
                    evidence_summary="No disclosed AI revenue",
                    review_status="unknown",
                ),
                business_profile_row(
                    code="300912",
                    name="Transition Co",
                    primary_business="legacy equipment",
                    sw_industry="machinery",
                    theme_business_description="company is piloting computing transition",
                    theme_revenue_materiality="transition",
                    evidence_summary="Investor relations mentions pilot AI computing business",
                    review_status="unknown",
                ),
                business_profile_row(
                    code="300913",
                    name="Core AI Co",
                    primary_business="AI software platform",
                    sw_industry="software",
                    theme_business_description="AI platform is core product and revenue source",
                    theme_revenue_materiality="core",
                    evidence_summary="Annual report discloses AI platform revenue",
                    review_status="unknown",
                ),
                business_profile_row(
                    code="300914",
                    name="Rejected Co",
                    primary_business="computing services",
                    sw_industry="software",
                    theme_business_description="computing service",
                    theme_revenue_materiality="core",
                    evidence_summary="Disclosed revenue",
                    review_status="core",
                ),
            ]
        )
        overrides = pd.DataFrame(
            [
                {
                    "code": "300914",
                    "name": "Rejected Co",
                    "theme": "AI",
                    "override_status": "reject",
                    "reason": "Manual review rejected",
                    "reviewer": "analyst",
                    "review_date": "2026-06-28",
                }
            ]
        )

        diagnostics = build_business_materiality_diagnostics(
            purity,
            profiles,
            stock_overrides=overrides,
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"input_file": "theme_stock_purity_diagnostics.csv"},
        ).set_index("code", drop=False)

        self.assertTrue(bool(diagnostics.loc["300911", "concept_only_flag"]))
        self.assertTrue(bool(diagnostics.loc["300911", "business_mismatch_flag"]))
        self.assertEqual(diagnostics.loc["300911", "final_review_suggestion"], "review")
        self.assertTrue(bool(diagnostics.loc["300912", "transition_story_flag"]))
        self.assertEqual(diagnostics.loc["300912", "final_review_suggestion"], "conditional")
        self.assertEqual(diagnostics.loc["300913", "final_review_suggestion"], "core")
        self.assertEqual(diagnostics.loc["300914", "final_review_suggestion"], "reject_candidate")
        impossible = diagnostics[diagnostics["code"] == ""].iloc[0]
        self.assertEqual(impossible["final_review_suggestion"], "reject_candidate")

    def test_business_materiality_missing_profile_routes_to_review(self):
        purity = pd.DataFrame([purity_row("300915", "No Profile Co", "high_confidence", "AI Agent", 2)])

        diagnostics = build_business_materiality_diagnostics(
            purity,
            pd.DataFrame(),
            stock_overrides=pd.DataFrame(),
            generated_at="2026-06-28T00:00:00Z",
            run_metadata={"input_file": "theme_stock_purity_diagnostics.csv"},
        )

        self.assertFalse(bool(diagnostics.loc[0, "business_profile_available"]))
        self.assertTrue(bool(diagnostics.loc[0, "concept_only_flag"]))
        self.assertEqual(diagnostics.loc[0, "final_review_suggestion"], "review")

    def test_high_confidence_mismatch_queue_and_profile_template_priority(self):
        materiality = pd.DataFrame(
            [
                materiality_row("300911", "Kitchen Co", "high_confidence", True, False, "review", 2),
                materiality_row("300912", "Transition Co", "high_confidence", False, True, "conditional", 2),
                materiality_row("300913", "Core AI Co", "high_confidence", False, False, "core", 2),
                materiality_row("300914", "Broad Co", "broad_concept_only", True, False, "review", 1),
            ]
        )

        queue = build_high_confidence_business_mismatch_queue(materiality)
        template = build_stock_business_profile_template(materiality, queue, max_rows=3)

        self.assertEqual(queue["code"].tolist(), ["300911", "300912"])
        self.assertEqual(template.loc[0, "code"], "300911")
        self.assertIn("suggested_initial_review_status", template.columns)
        self.assertEqual(template.loc[0, "suggested_initial_review_status"], "unknown")
        self.assertIn("reason_for_review", template.columns)


def constituent_row(
    code: str,
    concept: str,
    source_id: str,
    *,
    name: str = "Alpha",
    theme: str = "AI",
    ring: str = "P0",
    include_default: str = "yes",
    layer: str = "core",
    weight: float = 3.0,
) -> dict[str, object]:
    return {
        "raw_code": code,
        "code": code,
        "name": name,
        "theme": theme,
        "matched_akshare_concept": concept,
        "original_possible_concept": concept,
        "ring": ring,
        "include_default": include_default,
        "industry_chain_layer": layer,
        "source_id": source_id,
        "source_url": "https://example.com",
        "concept_source_weight": weight,
        "evidence_summary": f"Evidence {source_id}",
        "risk_note": "Risk",
    }


def purity_row(
    code: str,
    name: str,
    bucket: str,
    concepts: str,
    matched_concept_count: int,
    *,
    theme: str = "AI",
) -> dict[str, object]:
    return {
        "raw_code": code,
        "code": code,
        "name": name,
        "theme": theme,
        "concept_exposure_score": 6.0,
        "theme_relevance_score": 6.0,
        "matched_concept_count": matched_concept_count,
        "p0_concept_count": matched_concept_count,
        "p1_concept_count": 0,
        "p2_concept_count": 0,
        "supporting_concepts": concepts,
        "supporting_source_ids": "S1|S2" if matched_concept_count > 1 else "S1",
        "supporting_industry_chain_layers": "core",
        "strongest_evidence_summary": "Concept evidence",
        "main_risk_note": "Risk",
        "broad_concept_only": bucket == "broad_concept_only",
        "multi_concept_support": matched_concept_count > 1,
        "specific_concept_support": bucket != "broad_concept_only",
        "concept_purity_bucket": bucket,
        "override_status": "",
        "override_reason": "",
        "generated_at": "2026-06-28T00:00:00Z",
    }


def business_profile_row(
    *,
    code: str = "300911",
    name: str = "Kitchen Co",
    theme: str = "AI",
    primary_business: str = "integrated kitchen appliances",
    revenue_segments: str = "kitchen appliances",
    sw_industry: str = "home appliances",
    theme_business_description: str = "",
    theme_revenue_materiality: str = "unknown",
    theme_revenue_ratio: str = "",
    theme_revenue_amount: str = "",
    evidence_level: str = "official_report",
    evidence_source: str = "annual report",
    evidence_url: str = "https://example.com/report",
    evidence_date: str = "2026-06-01",
    evidence_summary: str = "Evidence summary",
    reviewer: str = "analyst",
    review_status: str = "unknown",
) -> dict[str, object]:
    return {
        "code": code,
        "name": name,
        "theme": theme,
        "primary_business": primary_business,
        "revenue_segments": revenue_segments,
        "sw_industry": sw_industry,
        "theme_business_description": theme_business_description,
        "theme_revenue_materiality": theme_revenue_materiality,
        "theme_revenue_ratio": theme_revenue_ratio,
        "theme_revenue_amount": theme_revenue_amount,
        "evidence_level": evidence_level,
        "evidence_source": evidence_source,
        "evidence_url": evidence_url,
        "evidence_date": evidence_date,
        "evidence_summary": evidence_summary,
        "reviewer": reviewer,
        "review_status": review_status,
    }


def materiality_row(
    code: str,
    name: str,
    bucket: str,
    mismatch: bool,
    transition: bool,
    suggestion: str,
    matched_concept_count: int,
) -> dict[str, object]:
    row = purity_row(code, name, bucket, "AIGC|Computing", matched_concept_count)
    row.update(
        {
            "business_profile_available": True,
            "primary_business_match": not mismatch,
            "theme_business_disclosed": not mismatch or transition,
            "theme_revenue_materiality_bucket": "transition" if transition else "unknown" if mismatch else "core",
            "business_mismatch_flag": mismatch,
            "transition_story_flag": transition,
            "concept_only_flag": mismatch,
            "final_review_suggestion": suggestion,
            "business_materiality_warning": "",
            "review_status": "unknown",
        }
    )
    return row


class ThemeConceptContractTests(unittest.TestCase):
    def test_required_mapping_columns_match_plan(self):
        self.assertIn("source_url", REQUIRED_MAPPING_COLUMNS)
        self.assertIn("possible_akshare_concept", REQUIRED_MAPPING_COLUMNS)
        self.assertIn("akshare_next_step", REQUIRED_MAPPING_COLUMNS)


class ThemeConceptScriptTests(unittest.TestCase):
    def test_validate_script_uses_cached_em_names_and_writes_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "source_concept_mapping.csv"
            cache_path = root / "stock_board_concept_name_em.csv"
            clean_output = root / "theme_concept_mapping_clean.csv"
            validation_output = root / "akshare_concept_validation.csv"
            report_path = root / "akshare_concept_validation_report.md"
            mapping_frame().to_csv(input_path, index=False, encoding="utf-8-sig")
            concept_names().to_csv(cache_path, index=False, encoding="utf-8-sig")

            with patch("scripts.validate_akshare_concepts.CONCEPT_NAME_CACHE", cache_path), patch(
                "scripts.validate_akshare_concepts.AkSharePublicClient"
            ) as client_class:
                client_class.return_value.concept_names.side_effect = AssertionError("cache should be used")
                exit_code = validate_concepts_main(
                    [
                        "--input",
                        str(input_path),
                        "--clean-output",
                        str(clean_output),
                        "--output",
                        str(validation_output),
                        "--report",
                        str(report_path),
                    ]
                )

            validation = pd.read_csv(validation_output)
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertEqual(validation.loc[0, "match_status"], "exact")
            self.assertEqual(validation.loc[0, "akshare_cache_status"], "cache_hit")
            self.assertIn("reviewed concept taxonomy", report)
            self.assertIn("validated only against Eastmoney", report)

    def test_build_script_dry_run_and_max_concepts_write_metadata_outputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            validation_path = root / "akshare_concept_validation.csv"
            constituent_output = root / "theme_concept_constituents.csv"
            universe_output = root / "theme_stock_universe.csv"
            report_path = root / "theme_stock_universe_report.md"
            materiality_output = root / "theme_business_materiality_diagnostics.csv"
            mismatch_output = root / "high_confidence_business_mismatch_queue.csv"
            profile_template_output = root / "stock_business_profile_template.csv"
            materiality_report_path = root / "theme_business_materiality_report.md"
            validation = pd.DataFrame(
                [
                    {
                        "theme": "AI",
                        "possible_akshare_concept": name,
                        "matched_akshare_concept": name,
                        "matched_akshare_code": code,
                        "match_status": "exact",
                        "ring": "P0",
                        "include_default": "yes",
                        "source_type": "official_policy",
                        "source_id": f"S{idx}",
                        "source_url": "https://example.com",
                        "evidence_summary": "Evidence",
                        "risk_note": "Risk",
                        "industry_chain_layer": "core",
                    }
                    for idx, (name, code) in enumerate([("人工智能", "BK1"), ("商业航天", "BK2")], start=1)
                ]
            )
            validation.to_csv(validation_path, index=False, encoding="utf-8-sig")

            with patch("scripts.build_theme_concept_universe.AkSharePublicClient") as client_class:
                client_class.return_value.concept_members.side_effect = AssertionError("dry run should not fetch")
                exit_code = build_universe_main(
                    [
                        "--validation",
                        str(validation_path),
                        "--output-constituents",
                        str(constituent_output),
                        "--output-universe",
                        str(universe_output),
                        "--report",
                        str(report_path),
                        "--themes",
                        "AI",
                        "--rings",
                        "P0",
                        "--dry-run",
                        "--max-concepts",
                        "1",
                    ]
                )

            constituents = pd.read_csv(constituent_output)
            universe = pd.read_csv(universe_output)
            materiality = pd.read_csv(materiality_output)
            mismatch = pd.read_csv(mismatch_output)
            profile_template = pd.read_csv(profile_template_output)
            report = report_path.read_text(encoding="utf-8")
            materiality_report = materiality_report_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertTrue(constituents.empty)
            self.assertTrue(universe.empty)
            self.assertTrue(materiality.empty)
            self.assertTrue(mismatch.empty)
            self.assertTrue(profile_template.empty)
            self.assertIn("selected_concepts=1", report)
            self.assertIn("dry_run=True", report)
            self.assertIn("concept_exposure_score measures concept-board exposure", report)
            self.assertIn("Concept board support is not business materiality", materiality_report)


if __name__ == "__main__":
    unittest.main()
