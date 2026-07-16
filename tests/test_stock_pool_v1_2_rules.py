from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "data" / "stockPool" / "build_stock_pool_v1_2.py"
SPEC = importlib.util.spec_from_file_location("build_stock_pool_v1_2", MODULE_PATH)
stock_pool_v1_2 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stock_pool_v1_2)


def base_row(code: str, theme: str = "AI", decision: str = "excluded_by_rules") -> dict[str, str]:
    return {
        "code": code,
        "name": "TestCo",
        "theme": theme,
        "business_evidence_decision": "theme_confirmed",
        "evidence_strength": "strong",
        "evidence_url": "https://example.com/report.pdf",
        "trading_pool_decision": decision,
        "answer_q4_pool_decision": decision,
    }


def score(
    *,
    is_st: str = "false",
    financial_quality_flag: str = "pass",
    market_cap: str = "5000000000",
    avg_amount_20d: str = "200000000",
    debt_to_asset: str = "81.0",
    valuation_flag: str = "normal",
) -> dict[str, str]:
    return {
        "is_st": is_st,
        "financial_quality_flag": financial_quality_flag,
        "market_cap": market_cap,
        "avg_amount_20d": avg_amount_20d,
        "debt_to_asset": debt_to_asset,
        "valuation_flag": valuation_flag,
    }


class StockPoolV12RuleTests(unittest.TestCase):
    def test_debt_above_80_alone_moves_from_excluded_to_expanded(self):
        row = base_row("123456")
        out = stock_pool_v1_2.apply_v1_2_decision(row, score())

        self.assertEqual(out["trading_pool_decision"], "expanded")
        self.assertEqual(out["rule_exception_resolution"], "auto_allow_expanded_debt_only")
        self.assertEqual(out["leverage_risk_flag"], "yes")
        self.assertEqual(out["default_pool_allowed"], "no")
        self.assertEqual(out["explicit_hard_rule_hit"], "none")

    def test_debt_above_80_blocks_default_pool(self):
        row = base_row("123457", decision="default")
        out = stock_pool_v1_2.apply_v1_2_decision(row, score())

        self.assertEqual(out["trading_pool_decision"], "expanded")
        self.assertEqual(out["rule_exception_resolution"], "downgrade_default_for_leverage")
        self.assertEqual(out["default_pool_allowed"], "no")

    def test_explicit_hard_rule_keeps_row_excluded(self):
        row = base_row("123458")
        out = stock_pool_v1_2.apply_v1_2_decision(
            row,
            score(financial_quality_flag="fail", market_cap="2500000000"),
        )

        self.assertEqual(out["trading_pool_decision"], "excluded_by_rules")
        self.assertIn("financial_quality_flag=fail", out["explicit_hard_rule_hit"])
        self.assertIn("market_cap<30亿", out["explicit_hard_rule_hit"])

    def test_manual_cases_resolve_to_expected_decisions(self):
        cases = {
            "000938": ("expanded", "allow_expanded", "medium"),
            "300857": ("expanded", "allow_expanded_with_high_risk_flag", "high"),
            "002313": ("excluded_by_rules", "keep_excluded_explicit_hard_rules", "high"),
            "300212": ("excluded_by_rules", "keep_excluded_explicit_hard_rules", "high"),
        }
        score_by_code = {
            "000938": score(),
            "300857": score(),
            "002313": score(
                financial_quality_flag="fail",
                market_cap="2500000000",
                avg_amount_20d="50000000",
                debt_to_asset="98.0",
            ),
            "300212": score(is_st="true", financial_quality_flag="fail", debt_to_asset="113.0"),
        }

        for code, expected in cases.items():
            with self.subTest(code=code):
                out = stock_pool_v1_2.apply_v1_2_decision(base_row(code), score_by_code[code])
                self.assertEqual(out["trading_pool_decision"], expected[0])
                self.assertEqual(out["rule_exception_resolution"], expected[1])
                self.assertEqual(out["financial_risk_level"], expected[2])
                self.assertEqual(out["leverage_risk_flag"], "yes")


if __name__ == "__main__":
    unittest.main()
