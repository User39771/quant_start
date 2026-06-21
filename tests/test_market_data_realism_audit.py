import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.audit_market_data_realism import (
    build_audit_rows,
    render_audit_report,
    save_audit_outputs,
)


class MarketDataRealismAuditTests(unittest.TestCase):
    def test_schema_audit_detects_adj_factor_and_missing_lifecycle_history(self):
        schema = pd.DataFrame(
            [
                {"schema": "public", "table": "stock_prices_history", "column": "company_id", "data_type": "text"},
                {"schema": "public", "table": "stock_prices_history", "column": "trade_date", "data_type": "date"},
                {"schema": "public", "table": "stock_prices_history", "column": "close_price", "data_type": "numeric"},
                {"schema": "public", "table": "stock_prices_history", "column": "adj_factor", "data_type": "numeric"},
                {"schema": "public", "table": "companies", "column": "is_active", "data_type": "boolean"},
                {"schema": "public", "table": "map_company_industry_sw", "column": "in_date", "data_type": "text"},
                {"schema": "public", "table": "map_company_industry_sw", "column": "out_date", "data_type": "text"},
            ]
        )
        price_cache_columns = ["date", "close", "total_market_cap", "amount"]

        rows = build_audit_rows(schema, price_cache_columns=price_cache_columns)
        indexed = rows.set_index("check")

        self.assertEqual(indexed.loc["adjustment_factor", "status"], "available_not_cached")
        self.assertIn("stock_prices_history.adj_factor", indexed.loc["adjustment_factor", "evidence"])
        self.assertEqual(indexed.loc["strict_return_cache", "status"], "missing")
        self.assertEqual(indexed.loc["delist_date", "status"], "missing")
        self.assertEqual(indexed.loc["industry_asof_dates", "status"], "available")

    def test_audit_report_and_outputs_include_required_caveats(self):
        rows = pd.DataFrame(
            [
                {
                    "category": "return",
                    "check": "strict_return_cache",
                    "status": "missing",
                    "evidence": "price cache lacks adjusted_close",
                    "impact": "current returns may be distorted",
                    "required_action": "keep caveat",
                }
            ]
        )

        report = render_audit_report(rows)

        self.assertIn("strict_adjusted_return_unavailable", report)
        self.assertIn("current returns may be distorted", report)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_audit_outputs(rows, root / "data" / "processed", root / "reports")

            self.assertTrue((root / "data" / "processed" / "market_data_realism_audit.csv").exists())
            self.assertTrue((root / "reports" / "market_data_realism_audit.md").exists())


if __name__ == "__main__":
    unittest.main()
