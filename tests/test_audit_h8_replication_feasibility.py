import ast
import inspect
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import audit_h8_replication_feasibility as audit


class H8FeasibilityTests(unittest.TestCase):
    def test_stock_availability_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / audit.BAO).mkdir(parents=True)
            dates = pd.bdate_range("2025-01-01", periods=30)
            frame = pd.DataFrame({
                "trade_date": dates, "open": 10., "high": 11., "low": 9.,
                "close": 10., "volume_shares": 100.,
                "baostock_circulating_turnover": 0.01,
                "trading_status": 1, "is_st": 0,
            })
            frame.to_csv(root / audit.BAO / "000001.csv", index=False)
            sample, ready = audit.inspect_stock(root, "000001", dates)
            self.assertEqual(sample["potential_p1_rows"], 7)
            self.assertEqual(ready["zero_current_return_rows"], 29)

    def test_no_network_imports(self):
        tree = ast.parse(inspect.getsource(audit))
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [x.name for n in ast.walk(tree) if isinstance(n, ast.Import) for x in n.names]
        self.assertFalse(set(imports) & {"requests", "httpx", "urllib", "socket", "baostock"})

    def test_no_regression_or_model_calls(self):
        source = inspect.getsource(audit)
        for term in (".fit(", "OLS(", "arch_model(", "lstsq(", "polyfit("):
            self.assertNotIn(term, source)

    def test_no_gamma_estimation(self):
        tree = ast.parse(inspect.getsource(audit))
        assigned = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        self.assertFalse(any(n.startswith("gamma") for n in assigned))

    def test_no_future_performance_comparison(self):
        source = inspect.getsource(audit.inspect_stock)
        for term in ("pct_change", ".corr(", "spearman", "future_return", "np.log"):
            self.assertNotIn(term, source)

    def test_h7_metadata_readonly(self):
        self.assertNotIn("write", inspect.getsource(audit.h7_metadata))
        self.assertNotIn("import run_h7", inspect.getsource(audit))

    def test_exact22_is_backward(self):
        valid = pd.Series([True] * 30)
        exact, _ = audit.window_flags(valid)
        self.assertFalse(exact.iloc[:22].any())
        self.assertTrue(exact.iloc[22:].all())

    def test_current_not_in_baseline(self):
        values = pd.Series([1.0] * 22 + [np.e])
        self.assertAlmostEqual(audit.toy_truncation(values).iloc[22], 1.0)

    def test_truncation_formula(self):
        values = pd.Series([2.0] * 22 + [1.0])
        self.assertEqual(audit.toy_truncation(values).iloc[-1], 0.0)

    def test_zero_truncated_rows_retained(self):
        values = pd.Series([2.0] * 22 + [1.0, 1.0])
        out = audit.toy_truncation(values)
        self.assertEqual(len(out), len(values))
        self.assertTrue(out.iloc[-2:].notna().all())

    def test_paper_sign_dummies(self):
        neg, pos = audit.sign_dummies(np.array([-1.0, 0.0, 1.0]))
        self.assertEqual(neg.tolist(), [True, False, False])
        self.assertEqual(pos.tolist(), [False, True, True])

    def test_zero_count_not_relation(self):
        source = inspect.getsource(audit.inspect_stock)
        self.assertIn("raw.close.eq(raw.close.shift(1))", source)

    def test_component_identity(self):
        daily, overnight, intraday = audit.toy_components(100.0, 110.0, 99.0)
        self.assertAlmostEqual(1 + daily, (1 + overnight) * (1 + intraday))
        self.assertNotAlmostEqual(daily, overnight + intraday)

    def test_qfq_risk_documented(self):
        self.assertIn("QFQ_OVERNIGHT_REPLICATION_RISK=true", inspect.getsource(audit.run))

    def test_no_fake_ah(self):
        self.assertIn("P3_INSTITUTION_FEASIBLE=false", inspect.getsource(audit.run))

    def test_no_fake_limit(self):
        self.assertIn("LOCAL_LIMIT_STATUS_CONSTRUCTIBLE=false", inspect.getsource(audit.run))
        self.assertNotIn("raw.close.eq(raw.low)", inspect.getsource(audit.inspect_stock))

    def test_no_threshold_selected(self):
        source = inspect.getsource(audit.inspect_stock)
        self.assertIn("history >= 2400", source)
        self.assertNotIn("history >= 750", source)

    def test_no_other_research_import(self):
        source = inspect.getsource(audit)
        for term in ("from scripts.run_", "from aq_factor_lab", "import statsmodels"):
            self.assertNotIn(term, source)

    def test_no_strategy_calculations(self):
        source = inspect.getsource(audit.inspect_stock)
        for term in ("cumprod", "sharpe", "portfolio", "rank("):
            self.assertNotIn(term, source)

    def test_suspension_gap_preserved(self):
        valid = pd.Series([True] * 55)
        valid.iloc[25] = False
        exact, active = audit.window_flags(valid)
        self.assertFalse(exact.iloc[26:48].any())
        self.assertTrue(active.iloc[26:48].all())
        self.assertFalse(active.iloc[25])

    def test_board_301_is_not_main(self):
        self.assertEqual(audit.board("301171"), "CHINEXT")
        self.assertEqual(audit.board("000001"), "SZ_MAIN")
        self.assertEqual(audit.board("688001"), "STAR")

    def test_equation_mapping_exists_and_unresolved_is_explicit(self):
        text = Path(audit.OUT / "h8_equation_mapping.md").read_text(encoding="utf-8")
        self.assertIn("RETURN_DECOMPOSITION_CONTRACT_STATUS=UNRESOLVED", text)
        self.assertIn("D_POS=1{r_t>=0}", text)


if __name__ == "__main__":
    unittest.main()
