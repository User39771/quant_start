from __future__ import annotations

import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from aq_factor_lab.db_source import (
    DatabaseConfig,
    MappingError,
    SyncPlanner,
    apply_price_adjustment_probe,
    atomic_write_csv,
    build_query_plan,
    cache_datetime,
    cache_iso_date,
    deduplicate_cache_frame,
    load_db_mapping,
    validate_db_mapping,
)
from scripts.sync_database_cache import (
    cache_query_windows,
    sync_endpoint,
    sync_price,
    transform_endpoint_frame,
    write_sync_outputs,
)


class DatabaseMappingTests(unittest.TestCase):
    def test_disabled_endpoint_does_not_require_table_or_fields(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "universe": {"enabled": False},
                "price": {"enabled": False},
                "cashflow": {"enabled": False, "date_column": "bad"},
            },
        }

        validate_db_mapping(mapping, available_columns={})

    def test_enabled_price_requires_adjustment_and_units(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "price": {
                    "enabled": True,
                    "schema": "public",
                    "table": "daily_price",
                    "symbol_column": "symbol",
                    "date_column": "trade_date",
                    "required_fields": {"close": "close"},
                    "optional_fields": {"amount": "amount"},
                    "adjustment": "bad",
                    "units": {"close": {"multiplier": 1}},
                }
            },
        }

        with self.assertRaisesRegex(MappingError, "adjustment"):
            validate_db_mapping(mapping, available_columns={("public", "daily_price"): {"symbol", "trade_date", "close", "amount"}})

    def test_enabled_financial_endpoint_rejects_date_column(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "cashflow": {
                    "enabled": True,
                    "schema": "public",
                    "table": "cashflow",
                    "symbol_column": "symbol",
                    "date_column": "date",
                    "report_date_column": "report_date",
                    "required_fields": {"operating_cashflow": "ocf"},
                    "units": {"operating_cashflow": {"multiplier": 1}},
                }
            },
        }

        with self.assertRaisesRegex(MappingError, "date_column"):
            validate_db_mapping(mapping, available_columns={("public", "cashflow"): {"symbol", "date", "report_date", "ocf"}})

    def test_load_mapping_requires_explicit_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"

            with self.assertRaises(FileNotFoundError):
                load_db_mapping(path)


class DatabaseSyncUtilityTests(unittest.TestCase):
    def test_database_config_from_env_uses_readonly_options_without_exposing_password(self):
        env = {
            "DB_HOST": "localhost",
            "DB_PORT": "15432",
            "DB_NAME": "deeppivot",
            "DB_USER": "tester",
            "DB_PASSWORD": "secret",
        }

        config = DatabaseConfig.from_env(env)

        self.assertIn("default_transaction_read_only=on", config.options)
        self.assertIn("statement_timeout", config.options)
        self.assertNotIn("secret", repr(config))

    def test_build_query_plan_has_identifier_objects_and_parameter_values(self):
        endpoint = {
            "enabled": True,
            "schema": "public",
            "table": "daily_price",
            "symbol_column": "symbol",
            "date_column": "trade_date",
            "required_fields": {"close": "close"},
            "optional_fields": {"amount": "amount"},
            "adjustment": "raw",
            "units": {"close": {"multiplier": 1}, "amount": {"multiplier": 1}},
        }

        plan = build_query_plan("price", endpoint, ["600519"], "2025-01-01", "2025-12-31")

        self.assertEqual(plan.endpoint, "price")
        self.assertEqual(plan.params["symbols"], ["600519"])
        self.assertNotIsInstance(plan.query, str)
        self.assertIn("close", plan.output_columns)

    def test_stock_prices_mapping_accepts_turnover_and_updated_at(self):
        endpoint = {
            "enabled": True,
            "schema": "public",
            "table": "stock_prices",
            "symbol_column": "company_id",
            "date_column": "trade_date",
            "updated_at_column": "updated_at",
            "required_fields": {"close": "close_price"},
            "optional_fields": {
                "amount": "amount",
                "high": "high_price",
                "low": "low_price",
                "turnover": "turnover",
                "total_market_cap": "total_market_cap",
                "circulating_market_cap": "circulating_market_cap",
            },
            "adjustment": "unknown",
            "units": {
                "close": {"multiplier": 1},
                "amount": {"multiplier": 1},
                "high": {"multiplier": 1},
                "low": {"multiplier": 1},
                "turnover": {"multiplier": 1},
                "total_market_cap": {"multiplier": 1},
                "circulating_market_cap": {"multiplier": 1},
            },
        }
        mapping = {"version": 1, "endpoints": {"price": endpoint}}
        available = {
            ("public", "stock_prices"): {
                "company_id",
                "trade_date",
                "close_price",
                "amount",
                "high_price",
                "low_price",
                "turnover",
                "total_market_cap",
                "circulating_market_cap",
                "updated_at",
            }
        }

        validate_db_mapping(mapping, available_columns=available)
        plan = build_query_plan("price", endpoint, ["SZ_000001"], "2020-01-02", "2026-06-12")

        self.assertEqual(plan.table, "stock_prices")
        self.assertIn("high_price", plan.selected_columns)
        self.assertIn("low_price", plan.selected_columns)
        self.assertIn("high", plan.output_columns)
        self.assertIn("low", plan.output_columns)
        self.assertIn("turnover", plan.selected_columns)
        self.assertIn("total_market_cap", plan.selected_columns)
        self.assertIn("circulating_market_cap", plan.selected_columns)
        self.assertIn("updated_at", plan.selected_columns)

    def test_price_adjustment_probe_adds_available_columns(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "price": {
                    "enabled": True,
                    "schema": "public",
                    "table": "stock_prices",
                    "symbol_column": "company_id",
                    "date_column": "trade_date",
                    "required_fields": {"close": "close_price"},
                    "optional_fields": {"amount": "amount"},
                    "adjustment": "unknown",
                    "units": {"close": {"multiplier": 1}, "amount": {"multiplier": 1}},
                }
            },
        }
        available = {
            ("public", "stock_prices"): {
                "company_id",
                "trade_date",
                "close_price",
                "amount",
                "adj_factor",
                "pre_close",
                "is_adjusted",
            }
        }

        probed = apply_price_adjustment_probe(mapping, available)
        price = probed["endpoints"]["price"]

        self.assertEqual(price["optional_fields"]["adj_factor"], "adj_factor")
        self.assertEqual(price["optional_fields"]["pre_close"], "pre_close")
        self.assertEqual(price["optional_fields"]["is_adjusted"], "is_adjusted")
        self.assertEqual(price["units"]["adj_factor"]["unit"], "factor")
        self.assertEqual(price["adjustment_probe"]["fields_found"], ["adj_factor", "pre_close", "is_adjusted"])
        self.assertIn("adjusted_close", price["adjustment_probe"]["fields_checked"])
        self.assertFalse(price["adjustment_probe"]["warning"])

    def test_price_adjustment_probe_warns_when_no_adjustment_fields_exist(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "price": {
                    "enabled": True,
                    "schema": "public",
                    "table": "stock_prices",
                    "symbol_column": "company_id",
                    "date_column": "trade_date",
                    "required_fields": {"close": "close_price"},
                    "optional_fields": {},
                    "adjustment": "unknown",
                    "units": {"close": {"multiplier": 1}},
                }
            },
        }

        probed = apply_price_adjustment_probe(
            mapping,
            {("public", "stock_prices"): {"company_id", "trade_date", "close_price"}},
        )

        probe = probed["endpoints"]["price"]["adjustment_probe"]
        self.assertEqual(probe["fields_found"], [])
        self.assertIn("价格未复权", probe["warning"])

    def test_dry_run_returns_plan_without_writing_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = {
                "version": 1,
                "endpoints": {
                    "price": {
                        "enabled": True,
                        "schema": "public",
                        "table": "daily_price",
                        "symbol_column": "symbol",
                        "date_column": "trade_date",
                        "required_fields": {"close": "close"},
                        "optional_fields": {},
                        "adjustment": "raw",
                        "units": {"close": {"multiplier": 1}},
                    }
                },
            }
            planner = SyncPlanner(
                root_dir=root,
                mapping=mapping,
                available_columns={("public", "daily_price"): {"symbol", "trade_date", "close"}},
            )

            rows = planner.dry_run(["price"], ["600519"], "2025-01-01", "2025-12-31")

            self.assertEqual(rows[0]["endpoint"], "price")
            self.assertFalse((root / "data" / "cache" / "price").exists())

    def test_atomic_write_sorts_deduplicates_and_records_warning(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "600519.csv"
            warnings: list[dict[str, object]] = []
            frame = pd.DataFrame(
                {
                    "code": ["600519", "600519", "600519"],
                    "date": pd.to_datetime(["2025-01-03", "2025-01-02", "2025-01-02"]),
                    "close": [3.0, 2.0, 2.5],
                    "updated_at": pd.to_datetime(["2025-01-03", "2025-01-02", "2025-01-04"]),
                }
            )

            out = deduplicate_cache_frame(frame, "price", warnings)
            atomic_write_csv(out, path, required_columns=["code", "date", "close"])
            saved = pd.read_csv(path)

            self.assertEqual(list(saved["date"]), ["2025-01-02", "2025-01-03"])
            self.assertEqual(saved.loc[0, "close"], 2.5)
            self.assertEqual(len(warnings), 1)

    def test_deduplicate_normalizes_leading_zero_codes_before_merge(self):
        warnings: list[dict[str, object]] = []
        frame = pd.DataFrame(
            {
                "code": [1, "000001"],
                "date": ["2026-06-15", "2026-06-15"],
                "close": [10.0, 11.0],
                "updated_at": ["2026-06-15 08:00:00", "2026-06-15 09:00:00"],
            }
        )

        out = deduplicate_cache_frame(frame, "price", warnings)

        self.assertEqual(out.shape[0], 1)
        self.assertEqual(out.loc[0, "code"], "000001")
        self.assertEqual(out.loc[0, "close"], 11.0)
        self.assertEqual(len(warnings), 1)

    def test_cache_query_windows_only_returns_missing_edges(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "600519.csv"
            pd.DataFrame(
                {
                    "code": ["600519", "600519"],
                    "date": ["2025-01-10", "2025-01-20"],
                    "close": [10.0, 20.0],
                }
            ).to_csv(path, index=False)

            status, windows = cache_query_windows(path, "2025-01-01", "2025-01-31", False)

            self.assertEqual(status, "partial")
            self.assertEqual(windows, [("2025-01-01", "2025-01-09"), ("2025-01-21", "2025-01-31")])

    def test_sync_price_records_backfill_no_rows_instead_of_failed(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache" / "price"
            cache_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "code": ["000001"],
                    "date": ["2026-06-04"],
                    "close": [10.0],
                }
            ).to_csv(cache_dir / "000001.csv", index=False)
            mapping = {
                "endpoints": {
                    "price": {
                        "enabled": True,
                        "schema": "public",
                        "table": "stock_prices",
                        "symbol_column": "company_id",
                        "date_column": "trade_date",
                        "required_fields": {"close": "close_price"},
                        "optional_fields": {},
                        "adjustment": "unknown",
                        "units": {"close": {"multiplier": 1}},
                    }
                }
            }
            args = type("Args", (), {"refresh_existing": False})()

            summary = sync_price(
                EmptyConnection(),
                mapping,
                ["SZ_000001"],
                "2020-01-02",
                "2026-06-12",
                args,
                [],
                root_dir=Path(tmp),
            )

            self.assertEqual(summary[0]["status"], "backfill_no_rows")

    def test_sync_cashflow_writes_report_date_cache(self):
        with TemporaryDirectory() as tmp:
            mapping = {
                "endpoints": {
                    "cashflow": {
                        "enabled": True,
                        "schema": "public",
                        "table": "cash_flow_sheets",
                        "symbol_column": "company_id",
                        "report_date_column": "report_date",
                        "ann_date_column": "notice_date",
                        "updated_at_column": "updated_at",
                        "required_fields": {"operating_cashflow": "netcash_operate"},
                        "optional_fields": {},
                        "units": {"operating_cashflow": {"multiplier": 1}},
                    }
                }
            }
            rows = [
                ("SZ_000001", "2024-03-31", "2024-04-30", 100.0, "2024-04-30 08:00:00"),
                ("SZ_000001", "2024-03-31", "2024-05-01", 110.0, "2024-05-01 08:00:00"),
            ]
            conn = StaticConnection(rows, ["company_id", "report_date", "notice_date", "netcash_operate", "updated_at"])
            args = type("Args", (), {"refresh_existing": True})()
            warnings_rows: list[dict[str, object]] = []

            summary = sync_endpoint(
                conn,
                mapping,
                "cashflow",
                ["SZ_000001"],
                "2020-01-01",
                "2026-06-12",
                args,
                warnings_rows,
                root_dir=Path(tmp),
            )

            out = pd.read_csv(Path(tmp) / "data" / "cache" / "cashflow" / "000001.csv", dtype={"code": str})
            self.assertEqual(summary[0]["status"], "success")
            self.assertEqual(summary[0]["rows_fetched"], 2)
            self.assertEqual(out.shape[0], 1)
            self.assertEqual(out.loc[0, "code"], "000001")
            self.assertEqual(out.loc[0, "report_date"], "2024-03-31")
            self.assertEqual(out.loc[0, "announce_date"], "2024-05-01")
            self.assertEqual(out.loc[0, "operating_cashflow"], 110.0)
            self.assertEqual(len(warnings_rows), 1)

    def test_sync_price_records_cache_coverage_and_elapsed_ms_for_skipped(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache" / "price"
            cache_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "code": ["000001", "000001"],
                    "date": ["2020-01-02", "2026-06-12"],
                    "close": [10.0, 11.0],
                }
            ).to_csv(cache_dir / "000001.csv", index=False)
            mapping = {
                "endpoints": {
                    "price": {
                        "enabled": True,
                        "schema": "public",
                        "table": "stock_prices",
                        "symbol_column": "company_id",
                        "date_column": "trade_date",
                        "required_fields": {"close": "close_price"},
                        "optional_fields": {},
                        "adjustment": "unknown",
                        "units": {"close": {"multiplier": 1}},
                    }
                }
            }
            args = type("Args", (), {"refresh_existing": False})()

            summary = sync_price(
                EmptyConnection(),
                mapping,
                ["SZ_000001"],
                "2020-01-02",
                "2026-06-12",
                args,
                [],
                root_dir=Path(tmp),
            )

            row = summary[0]
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["cache_before_rows"], 2)
            self.assertEqual(row["cache_before_min_date"], "2020-01-02")
            self.assertEqual(row["cache_before_max_date"], "2026-06-12")
            self.assertEqual(row["query_windows"], "")
            self.assertEqual(row["rows_fetched"], 0)
            self.assertEqual(row["cache_after_rows"], 2)
            self.assertGreaterEqual(row["elapsed_ms"], 0)

    def test_write_sync_outputs_creates_run_manifest_and_latest_summary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "data" / "processed"
            summary = [
                {
                    "db_symbol": "SZ_000001",
                    "code": "000001",
                    "exchange": "SZ",
                    "endpoint": "price",
                    "status": "success",
                    "rows_fetched": 10,
                    "elapsed_ms": 25,
                }
            ]
            warnings_rows: list[dict[str, object]] = []
            args = type("Args", (), {"refresh_existing": True, "dry_run": False})()
            db_config = DatabaseConfig("10.20.30.40", 15432, "deeppivot", "reader", "secret")

            output = write_sync_outputs(
                processed,
                summary,
                warnings_rows,
                args,
                db_config,
                endpoints=["price"],
                symbols=["SZ_000001"],
                start_date="2020-01-02",
                end_date="2026-06-12",
                run_id="test-run",
                started_at="2026-06-16T08:00:00",
            )

            run_dir = processed / "db_sync_runs" / "test-run"
            self.assertEqual(output["run_dir"], run_dir)
            self.assertTrue((run_dir / "db_sync_summary.csv").exists())
            self.assertTrue((run_dir / "db_sync_manifest.json").exists())
            self.assertTrue((processed / "db_sync_summary.csv").exists())
            manifest = pd.read_json(run_dir / "db_sync_manifest.json", typ="series")
            self.assertEqual(manifest["db_host"], "10.20.30.***")
            self.assertEqual(manifest["status_counts"]["success"], 1)
            self.assertEqual(manifest["rows_fetched"], 10)

    def test_cache_date_parsers_use_explicit_formats_without_inference_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dates = cache_iso_date(pd.Series(["2026-06-12", "bad"]))
            datetimes = cache_datetime(
                pd.Series(["2026-06-12 07:32:40", "2026-06-12 07:32:40.562506", "bad"])
            )

        self.assertEqual(dates.iloc[0].date().isoformat(), "2026-06-12")
        self.assertTrue(pd.isna(dates.iloc[1]))
        self.assertEqual(datetimes.iloc[0].second, 40)
        self.assertEqual(datetimes.iloc[1].microsecond, 562506)
        self.assertTrue(pd.isna(datetimes.iloc[2]))
        self.assertFalse(any("Could not infer format" in str(item.message) for item in caught))

    def test_transform_industry_sw_normalizes_yyyymmdd_dates_and_preserves_codes(self):
        mapping = {
            "symbol_column": "company_id",
            "required_fields": {
                "l1_index_code": "l1_index_code",
                "l2_index_code": "l2_index_code",
                "l3_index_code": "l3_index_code",
                "in_date": "in_date",
                "out_date": "out_date",
                "is_new": "is_new",
                "updated_at": "updated_at",
            },
            "optional_fields": {"l1_industry_name": "l1_industry_name"},
            "units": {
                "l1_index_code": {"unit": "text", "multiplier": 1},
                "l2_index_code": {"unit": "text", "multiplier": 1},
                "l3_index_code": {"unit": "text", "multiplier": 1},
                "in_date": {"unit": "text", "multiplier": 1},
                "out_date": {"unit": "text", "multiplier": 1},
                "is_new": {"unit": "text", "multiplier": 1},
                "updated_at": {"unit": "text", "multiplier": 1},
                "l1_industry_name": {"unit": "text", "multiplier": 1},
            },
        }
        raw = pd.DataFrame(
            {
                "company_id": ["SZ_000001", "SH_600519"],
                "l1_index_code": ["801780", "801120"],
                "l2_index_code": ["801781", "801121"],
                "l3_index_code": ["851911", "851921"],
                "l1_industry_name": ["银行", "食品饮料"],
                "in_date": ["19991110", "2001-01-01"],
                "out_date": [None, ""],
                "is_new": ["1", "1"],
                "updated_at": ["2026-06-01 08:00:00", "2026-06-02 08:00:00"],
            }
        )

        out = transform_endpoint_frame("industry_sw", raw, mapping)

        self.assertEqual(out.loc[0, "code"], "000001")
        self.assertEqual(out.loc[0, "db_symbol"], "SZ_000001")
        self.assertEqual(out.loc[0, "l1_index_code"], "801780")
        self.assertEqual(out.loc[0, "in_date"], "1999-11-10")
        self.assertTrue(pd.isna(out.loc[0, "out_date"]))
        self.assertTrue(pd.isna(out.loc[1, "out_date"]))

    def test_transform_price_constructs_adjusted_close_from_adj_factor(self):
        mapping = {
            "symbol_column": "company_id",
            "date_column": "trade_date",
            "required_fields": {"close": "close_price"},
            "optional_fields": {"adj_factor": "adj_factor"},
            "units": {"close": {"multiplier": 1}, "adj_factor": {"multiplier": 1}},
        }
        raw = pd.DataFrame(
            {
                "company_id": ["SZ_000001"],
                "trade_date": ["2025-01-31"],
                "close_price": [10.0],
                "adj_factor": [1.2],
            }
        )

        out = transform_endpoint_frame("price", raw, mapping)

        self.assertIn("adjusted_close", out.columns)
        self.assertAlmostEqual(out.loc[0, "adjusted_close"], 12.0)

    def test_transform_industry_sw_emits_required_sw_cache_fields(self):
        mapping = {
            "symbol_column": "company_id",
            "required_fields": {
                "sw_l1_code": "l1_index_code",
                "sw_l2_code": "l2_index_code",
                "sw_l3_code": "l3_index_code",
                "in_date": "in_date",
                "out_date": "out_date",
            },
            "optional_fields": {
                "sw_l1_name": "l1_industry_name",
                "sw_l2_name": "l2_industry_name",
                "sw_l3_name": "l3_industry_name",
            },
            "units": {
                "sw_l1_code": {"unit": "text", "multiplier": 1},
                "sw_l2_code": {"unit": "text", "multiplier": 1},
                "sw_l3_code": {"unit": "text", "multiplier": 1},
                "sw_l1_name": {"unit": "text", "multiplier": 1},
                "sw_l2_name": {"unit": "text", "multiplier": 1},
                "sw_l3_name": {"unit": "text", "multiplier": 1},
                "in_date": {"unit": "text", "multiplier": 1},
                "out_date": {"unit": "text", "multiplier": 1},
            },
        }
        raw = pd.DataFrame(
            {
                "company_id": ["SZ_000001"],
                "l1_index_code": ["801780"],
                "l2_index_code": ["801781"],
                "l3_index_code": ["851911"],
                "l1_industry_name": ["bank"],
                "l2_industry_name": ["bank_l2"],
                "l3_industry_name": ["bank_l3"],
                "in_date": ["19991110"],
                "out_date": [""],
            }
        )

        out = transform_endpoint_frame("industry_sw", raw, mapping)

        self.assertEqual(out.loc[0, "code"], "000001")
        self.assertEqual(out.loc[0, "sw_l1_code"], "801780")
        self.assertEqual(out.loc[0, "sw_l2_code"], "801781")
        self.assertEqual(out.loc[0, "sw_l3_code"], "851911")
        self.assertEqual(out.loc[0, "sw_l1_name"], "bank")
        self.assertEqual(out.loc[0, "sw_l2_name"], "bank_l2")
        self.assertEqual(out.loc[0, "sw_l3_name"], "bank_l3")
        self.assertEqual(out.loc[0, "in_date"], "1999-11-10")
        self.assertTrue(pd.isna(out.loc[0, "out_date"]))

    def test_industry_sw_mapping_accepts_required_cache_fields(self):
        mapping = {
            "version": 1,
            "endpoints": {
                "industry_sw": {
                    "enabled": True,
                    "schema": "public",
                    "table": "map_company_industry_sw",
                    "symbol_column": "company_id",
                    "required_fields": {
                        "sw_l1_code": "l1_index_code",
                        "sw_l2_code": "l2_index_code",
                        "sw_l3_code": "l3_index_code",
                        "in_date": "in_date",
                        "out_date": "out_date",
                    },
                    "optional_fields": {},
                    "units": {
                        "sw_l1_code": {"unit": "text", "multiplier": 1},
                        "sw_l2_code": {"unit": "text", "multiplier": 1},
                        "sw_l3_code": {"unit": "text", "multiplier": 1},
                        "in_date": {"unit": "text", "multiplier": 1},
                        "out_date": {"unit": "text", "multiplier": 1},
                    },
                }
            },
        }
        available = {
            ("public", "map_company_industry_sw"): {
                "company_id",
                "l1_index_code",
                "l2_index_code",
                "l3_index_code",
                "in_date",
                "out_date",
            }
        }

        validate_db_mapping(mapping, available_columns=available)


class EmptyCursor:
    description = [("company_id",), ("trade_date",), ("close_price",)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params):
        return None

    def fetchall(self):
        return []


class EmptyConnection:
    def cursor(self):
        return EmptyCursor()


class StaticCursor:
    def __init__(self, rows, columns):
        self._rows = rows
        self.description = [(column,) for column in columns]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params):
        return None

    def fetchall(self):
        return self._rows


class StaticConnection:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns

    def cursor(self):
        return StaticCursor(self._rows, self._columns)


if __name__ == "__main__":
    unittest.main()
