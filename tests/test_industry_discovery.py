from __future__ import annotations

import unittest

import pandas as pd

from scripts.discover_industry_classification import discover_industry_tables, render_discovery_log


class IndustryDiscoveryTests(unittest.TestCase):
    def test_discovers_shenwan_industry_tables_from_schema_csv(self):
        schema = pd.DataFrame(
            {
                "schema": ["public", "public", "public", "public"],
                "table": [
                    "map_company_industry_sw",
                    "dim_industry_categories_sw",
                    "stock_prices",
                    "companies",
                ],
                "column": ["company_id", "industry_name", "close_price", "industry"],
                "data_type": ["character varying", "character varying", "numeric", "character varying"],
            }
        )

        matches = discover_industry_tables(schema)
        table_names = {match["table"] for match in matches}
        log = render_discovery_log(matches, db_samples=[])

        self.assertIn("map_company_industry_sw", table_names)
        self.assertIn("dim_industry_categories_sw", table_names)
        self.assertIn("申万", log)
        self.assertIn("sw_found_applied", log)
        self.assertIn("public.map_company_industry_sw", log)
        self.assertIn("public.dim_industry_categories_sw", log)


if __name__ == "__main__":
    unittest.main()
