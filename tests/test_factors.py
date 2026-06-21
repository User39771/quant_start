import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from aq_factor_lab.data import StockData
from aq_factor_lab.evaluation import evaluate_factor_panel
from aq_factor_lab.factors import (
    DEFAULT_NEUTRAL_FACTORS,
    FactorProcessor,
    add_composite_alpha,
    add_grouped_price_momentum_features,
    apply_cf_yield_unit_guard,
    attach_industry_sw,
    build_factor_panel,
    make_financial_features,
    make_price_features,
    score_cross_section,
    stock_observation_panel,
)


class FactorTests(unittest.TestCase):
    def test_financial_features_use_positive_profit_denominator(self):
        report_dates = pd.to_datetime(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"])
        cash = pd.DataFrame(
            {
                "report_date": report_dates,
                "announce_date": report_dates + pd.Timedelta(days=30),
                "operating_cashflow": [100.0, 220.0, 360.0, 520.0],
            }
        )
        profit = pd.DataFrame(
            {
                "report_date": report_dates,
                "announce_date": report_dates + pd.Timedelta(days=30),
                "revenue": [1000.0, 2000.0, 3000.0, 4000.0],
                "parent_net_profit": [50.0, 100.0, 150.0, -10.0],
            }
        )
        out = make_financial_features(cash, profit)
        self.assertTrue(np.isnan(out.loc[2, "cf_to_profit"]))
        self.assertTrue(np.isnan(out.loc[3, "cf_to_profit"]))

    def test_financial_features_convert_cumulative_flows_to_ttm(self):
        report_dates = pd.to_datetime(
            ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
        )
        cash = pd.DataFrame(
            {
                "report_date": report_dates,
                "announce_date": report_dates + pd.Timedelta(days=30),
                "operating_cashflow": [10.0, 30.0, 60.0, 100.0, 15.0],
            }
        )
        profit = pd.DataFrame(
            {
                "report_date": report_dates,
                "announce_date": report_dates + pd.Timedelta(days=30),
                "revenue": [100.0, 250.0, 450.0, 700.0, 120.0],
                "parent_net_profit": [5.0, 15.0, 30.0, 50.0, 8.0],
            }
        )

        out = make_financial_features(cash, profit)

        self.assertIn("operating_cashflow_ttm", out.columns)
        self.assertIn("revenue_ttm", out.columns)
        self.assertIn("parent_net_profit_ttm", out.columns)
        self.assertAlmostEqual(out.loc[3, "operating_cashflow_ttm"], 100.0)
        self.assertAlmostEqual(out.loc[4, "operating_cashflow_ttm"], 105.0)
        self.assertAlmostEqual(out.loc[4, "revenue_ttm"], 720.0)
        self.assertAlmostEqual(out.loc[4, "parent_net_profit_ttm"], 53.0)
        self.assertAlmostEqual(out.loc[4, "cf_to_revenue"], 105.0 / 720.0)
        self.assertAlmostEqual(out.loc[4, "cf_to_profit"], 105.0 / 53.0)

    def test_cf_yield_uses_ttm_operating_cashflow_when_available(self):
        raw = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"] * 3),
                "code": ["000001", "000002", "000003"],
                "operating_cashflow": [10.0, 20.0, 30.0],
                "operating_cashflow_ttm": [40.0, 80.0, 120.0],
                "total_market_cap": [1000.0, 2000.0, 3000.0],
            }
        )

        out = apply_cf_yield_unit_guard(raw)

        self.assertTrue(np.allclose(out["cf_yield"], [0.04, 0.04, 0.04]))

    def test_score_direction_high_is_good(self):
        raw = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"] * 3),
                "code": ["000001", "000002", "000003"],
                "forward_return_20d": [0.01, 0.02, 0.03],
                "cf_to_revenue": [0.1, 0.2, 0.3],
                "cf_to_profit": [1.0, 2.0, 3.0],
                "ocf_yoy": [-0.1, 0.0, 0.1],
                "cf_yield": [0.01, 0.02, 0.03],
                "moneyflow_5d_amount_ratio": [-0.1, 0.0, 0.1],
                "moneyflow_20d_amount_ratio": [-0.2, 0.0, 0.2],
                "moneyflow_5d_pct": [-0.01, 0.0, 0.01],
                "moneyflow_20d_pct": [-0.02, 0.0, 0.02],
                "moneyflow_20d_float_mv_ratio": [-0.03, 0.0, 0.03],
            }
        )
        scored = score_cross_section(raw)
        best = scored.sort_values("cashflow_quality_score").iloc[-1]
        self.assertEqual(best["code"], "000003")
        money_best = scored.sort_values("main_moneyflow_score").iloc[-1]
        self.assertEqual(money_best["code"], "000003")
        self.assertIn("cf_yield_rank", scored.columns)

    def test_evaluation_outputs_tables(self):
        rows = []
        for month in pd.date_range("2024-01-31", periods=3, freq="ME"):
            for i in range(20):
                score = i / 19
                rows.append(
                    {
                        "date": month,
                        "code": f"{i:06d}",
                        "cashflow_quality_score": score,
                        "cf_yield": score,
                        "cashflow_quality_score_neutral": score,
                        "cf_yield_neutral": score,
                        "main_moneyflow_score": score,
                        "forward_return_20d": score * 0.1,
                    }
                )
        panel = pd.DataFrame(rows)
        results = evaluate_factor_panel(panel)
        self.assertFalse(results["ic_summary"].empty)
        self.assertGreater(results["ic_summary"]["mean"].dropna().mean(), 0)

    def test_evaluation_outputs_cross_sectional_factor_correlation_matrix(self):
        rows = []
        specs = [
            (
                "2024-01-31",
                [1.0, 2.0, 3.0, 4.0],
                [1.0, 2.0, 3.0, 4.0],
                [4.0, 3.0, 2.0, 1.0],
            ),
            (
                "2024-02-29",
                [1.0, 2.0, 3.0, 4.0],
                [4.0, 3.0, 2.0, 1.0],
                [1.0, 2.0, 3.0, 4.0],
            ),
        ]
        for date, cf_values, reversal_values, volatility_values in specs:
            for i, (cf_value, reversal_value, volatility_value) in enumerate(
                zip(cf_values, reversal_values, volatility_values, strict=True)
            ):
                rows.append(
                    {
                        "date": pd.Timestamp(date),
                        "code": f"{i:06d}",
                        "forward_return_20d": float(i) / 10.0,
                        "cf_yield_neutral": cf_value,
                        "reversal_20d_neutral": reversal_value,
                        "volatility_20d_neutral": volatility_value,
                    }
                )
        panel = pd.DataFrame(rows)

        result = evaluate_factor_panel(panel)["factor_correlation"]

        self.assertEqual(
            result.columns.tolist(),
            [
                "cf_yield_neutral",
                "reversal_20d_neutral",
                "volatility_20d_neutral",
            ],
        )
        self.assertEqual(
            result.index.tolist(),
            [
                "cf_yield_neutral",
                "reversal_20d_neutral",
                "volatility_20d_neutral",
            ],
        )
        self.assertAlmostEqual(result.loc["cf_yield_neutral", "reversal_20d_neutral"], 0.0)
        self.assertAlmostEqual(result.loc["cf_yield_neutral", "volatility_20d_neutral"], 0.0)
        self.assertAlmostEqual(result.loc["reversal_20d_neutral", "volatility_20d_neutral"], -1.0)

    def test_factor_panel_uses_unified_market_month_end_dates(self):
        stock_a = make_stock("000001", "2025-01-01", 160)
        stock_b = make_stock("000002", "2025-01-01", 145)

        panel = build_factor_panel([stock_a, stock_b], holding_days=20, min_history_days=120)

        counts = panel.groupby("date")["code"].nunique()
        self.assertFalse(counts.empty)
        self.assertTrue((counts >= 2).all())
        self.assertNotIn(pd.Timestamp("2025-05-25"), set(pd.to_datetime(panel["date"])))

    def test_price_features_use_market_cap_return_when_strict_adjusted_price_missing(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        price = pd.DataFrame(
            {
                "date": dates,
                "close": [100.0] * 20 + [50.0] + [50.0] * 4,
                "total_market_cap": [1000.0] * 25,
                "turnover": [1.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertAlmostEqual(out.loc[0, "forward_return_20d"], 0.0)
        self.assertEqual(out.loc[0, "return_source"], "total_market_cap")

    def test_price_features_prefer_adjusted_close_returns_when_available(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        price = pd.DataFrame(
            {
                "date": dates,
                "close": [100.0] * 20 + [50.0] + [50.0] * 4,
                "adjusted_close": [100.0] * 20 + [110.0] + [110.0] * 4,
                "total_market_cap": [1000.0] * 25,
                "turnover": [1.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertAlmostEqual(out.loc[0, "forward_return_20d"], 0.1)
        self.assertEqual(out.loc[0, "return_source"], "adjusted_close")

    def test_price_features_construct_adjusted_close_from_adj_factor_by_code(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        frame = pd.DataFrame(
            {
                "date": list(dates) + list(dates),
                "code": ["000001"] * 25 + ["000002"] * 25,
                "close": [10.0] * 25 + [20.0] * 25,
                "adj_factor": list(np.linspace(1.0, 1.24, 25)) + list(np.linspace(2.0, 2.48, 25)),
                "total_market_cap": [1000.0] * 50,
                "turnover": [1.0] * 50,
                "amount": [1000.0] * 50,
            }
        )

        out = add_grouped_price_momentum_features(frame.sample(frac=1.0, random_state=3), holding_days=20)

        for code, source in frame.groupby("code"):
            actual = out[out["code"] == code].sort_values("date").reset_index(drop=True)
            adjusted = (source["close"] * source["adj_factor"]).reset_index(drop=True)
            self.assertAlmostEqual(actual.loc[0, "adjusted_close"], adjusted.loc[0])
            self.assertAlmostEqual(actual.loc[0, "forward_return_20d"], adjusted.loc[20] / adjusted.loc[0] - 1.0)
            self.assertEqual(actual.loc[0, "return_source"], "close_times_adj_factor")

    def test_price_features_do_not_fall_back_to_close_when_market_cap_missing(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        price = pd.DataFrame(
            {
                "date": dates,
                "close": np.linspace(10.0, 20.0, 25),
                "total_market_cap": [np.nan] * 25,
                "turnover": [1.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertTrue(np.isnan(out.loc[0, "forward_return_20d"]))

    def test_price_features_market_cap_growth_sets_forward_return(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        cap = [1000.0] * 20 + [1100.0] + [1100.0] * 4
        price = pd.DataFrame(
            {
                "date": dates,
                "close": [10.0] * 25,
                "total_market_cap": cap,
                "turnover": [1.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertAlmostEqual(out.loc[0, "forward_return_20d"], 0.1)

    def test_price_features_generate_amount_20d_from_raw_amount(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        price = pd.DataFrame(
            {
                "date": dates,
                "total_market_cap": [1000.0] * 25,
                "turnover": [1.0] * 25,
                "amount": [float(i) for i in range(1, 26)],
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertIn("amount_20d", out.columns)
        self.assertTrue(np.isnan(out.loc[8, "amount_20d"]))
        self.assertAlmostEqual(out.loc[9, "amount_20d"], 5.5)
        self.assertAlmostEqual(out.loc[20, "amount_20d"], 11.5)

    def test_price_features_generate_reversal_and_volatility_20d_from_market_cap(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        cap = pd.Series([1000.0 + i * 10.0 for i in range(25)])
        price = pd.DataFrame(
            {
                "date": dates,
                "total_market_cap": cap,
                "turnover": [1.0] * 25,
                "amount": [1000.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        expected_reversal = -(cap / cap.shift(20) - 1.0)
        expected_volatility = cap.pct_change().rolling(20, min_periods=10).std()
        self.assertIn("reversal_20d", out.columns)
        self.assertIn("volatility_20d", out.columns)
        self.assertTrue(np.isnan(out.loc[19, "reversal_20d"]))
        self.assertAlmostEqual(out.loc[20, "reversal_20d"], expected_reversal.loc[20])
        self.assertTrue(np.isnan(out.loc[9, "volatility_20d"]))
        self.assertAlmostEqual(out.loc[10, "volatility_20d"], expected_volatility.loc[10])
        self.assertAlmostEqual(out.loc[24, "volatility_20d"], expected_volatility.loc[24])

    def test_price_features_tolerate_existing_code_column_without_duplicate_groupers(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        cap = pd.Series([1000.0 + i * 10.0 for i in range(25)])
        price = pd.DataFrame(
            {
                "date": dates,
                "code": ["000001"] * 25,
                "total_market_cap": cap,
                "turnover": [1.0] * 25,
                "amount": [1000.0] * 25,
            }
        )

        out = make_price_features(price, holding_days=20)

        self.assertNotIn("code", out.columns)
        self.assertAlmostEqual(out.loc[20, "reversal_20d"], -(cap.loc[20] / cap.loc[0] - 1.0))

    def test_price_features_do_not_cross_contaminate_between_codes(self):
        dates = pd.date_range("2025-01-01", periods=25, freq="D")
        frame = pd.DataFrame(
            {
                "date": list(dates) + list(dates),
                "code": ["000001"] * 25 + ["000002"] * 25,
                "total_market_cap": list(np.linspace(1000.0, 1240.0, 25))
                + list(np.linspace(5000.0, 6200.0, 25)),
                "turnover": list(np.linspace(0.1, 2.5, 25)) + list(np.linspace(2.0, 4.4, 25)),
                "amount": list(np.linspace(100.0, 2500.0, 25)) + list(np.linspace(3000.0, 5400.0, 25)),
            }
        )

        out = add_grouped_price_momentum_features(frame.sample(frac=1.0, random_state=7))

        for code, expected_source in frame.groupby("code", sort=False):
            actual = out[out["code"] == code].sort_values("date").reset_index(drop=True)
            cap = expected_source["total_market_cap"].reset_index(drop=True)
            expected_reversal = -(cap / cap.shift(20) - 1.0)
            expected_volatility = cap.pct_change(fill_method=None).rolling(20, min_periods=10).std()
            pd.testing.assert_series_equal(
                actual["reversal_20d"].reset_index(drop=True),
                expected_reversal,
                check_names=False,
            )
            pd.testing.assert_series_equal(
                actual["volatility_20d"].reset_index(drop=True),
                expected_volatility,
                check_names=False,
            )

        first_b = out[out["code"] == "000002"].sort_values("date").iloc[0]
        self.assertTrue(np.isnan(first_b["momentum_20d"]))
        self.assertTrue(np.isnan(first_b["reversal_20d"]))
        self.assertTrue(np.isnan(first_b["volatility_20d"]))

    def test_stock_observation_panel_outputs_buy_side_constraint_fields(self):
        stock = make_stock("000001", "2025-01-01", 160)

        panel = stock_observation_panel(stock, holding_days=20)

        for column in ["amount", "amount_20d", "high", "low"]:
            self.assertIn(column, panel.columns)
        self.assertTrue(panel["amount_20d"].notna().all())

    def test_stock_observation_panel_outputs_reversal_and_volatility_20d(self):
        stock = make_stock("000001", "2025-01-01", 160)

        panel = stock_observation_panel(stock, holding_days=20)

        self.assertIn("reversal_20d", panel.columns)
        self.assertIn("volatility_20d", panel.columns)
        self.assertTrue(panel["reversal_20d"].notna().any())
        self.assertTrue(panel["volatility_20d"].notna().any())

    def test_cf_yield_unit_guard_selects_cny_multiplier(self):
        frame = unit_guard_frame([5e9, 6e9, 7e9], [1e11, 1.2e11, 1.4e11])

        out = apply_cf_yield_unit_guard(frame)

        self.assertEqual(out["market_cap_unit_multiplier"].dropna().iloc[0], 1.0)
        self.assertAlmostEqual(out.loc[0, "cf_yield"], 0.05)
        self.assertEqual(out.loc[0, "cf_yield_unit_guard_status"], "ok")

    def test_cf_yield_unit_guard_selects_10k_yuan_multiplier(self):
        frame = unit_guard_frame([5e9, 6e9, 7e9], [1e7, 1.2e7, 1.4e7])

        out = apply_cf_yield_unit_guard(frame)

        self.assertEqual(out["market_cap_unit_multiplier"].dropna().iloc[0], 10000.0)
        self.assertAlmostEqual(out.loc[0, "cf_yield"], 0.05)

    def test_cf_yield_unit_guard_selects_100m_yuan_multiplier(self):
        frame = unit_guard_frame([5e9, 6e9, 7e9], [1000.0, 1200.0, 1400.0])

        out = apply_cf_yield_unit_guard(frame)

        self.assertEqual(out["market_cap_unit_multiplier"].dropna().iloc[0], 100000000.0)
        self.assertAlmostEqual(out.loc[0, "cf_yield"], 0.05)

    def test_cf_yield_unit_guard_marks_insufficient_sample(self):
        frame = unit_guard_frame([5e9, np.nan], [1e11, 1.2e11])

        out = apply_cf_yield_unit_guard(frame)

        self.assertTrue(out["cf_yield"].isna().all())
        self.assertEqual(out.loc[0, "cf_yield_unit_guard_status"], "failed_or_insufficient_sample")

    def test_factor_processor_mad_winsorizes_extreme_values(self):
        panel = processor_panel(
            values=[0.10] * 10 + [0.11] * 10 + [10.0],
            caps=np.linspace(1e10, 2e10, 21),
        )

        out = FactorProcessor(["cf_yield"]).process(panel)

        self.assertLess(out["cf_yield_winsor"].max(), 1.0)
        self.assertTrue(out["cf_yield"].max() > 1.0)

    def test_factor_processor_zscore_standardizes_cross_section(self):
        panel = processor_panel(
            values=list(np.linspace(-0.2, 0.2, 30)),
            caps=np.linspace(1e10, 2e10, 30),
        )

        out = FactorProcessor(["cf_yield"], neutralization_mode="market_cap").process(panel)
        z = out["cf_yield_z"].dropna()

        self.assertAlmostEqual(float(z.mean()), 0.0, places=10)
        self.assertAlmostEqual(float(z.std(ddof=0)), 1.0, places=10)

    def test_factor_processor_neutralizes_log_market_cap_exposure(self):
        caps = np.linspace(1e10, 5e10, 40)
        lncap = np.log(caps)
        values = 2.0 * lncap + np.sin(np.arange(40)) * 0.01
        panel = processor_panel(values=list(values), caps=caps)

        out = FactorProcessor(["cf_yield"], neutralization_mode="market_cap").process(panel)
        valid = out[["cf_yield_neutral", "ln_total_market_cap"]].dropna()

        corr = valid["cf_yield_neutral"].corr(valid["ln_total_market_cap"])
        self.assertAlmostEqual(float(corr), 0.0, places=10)
        self.assertEqual(set(out["cf_yield_neutral_status"]), {"ok"})

    def test_asof_industry_join_selects_active_row_by_observation_date(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-06-30", "2021-06-30"]),
                "code": ["000001", "000001"],
                "cf_yield": [0.01, 0.02],
            }
        )
        industry = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "l1_index_code": ["801010", "801020"],
                "l2_index_code": ["801011", "801021"],
                "l3_index_code": ["851011", "851021"],
                "l1_industry_name": ["旧行业", "新行业"],
                "in_date": ["2019-01-01", "2021-01-01"],
                "out_date": ["2020-12-31", None],
                "updated_at": ["2020-01-01 09:00:00", "2021-02-01 09:00:00"],
            }
        )

        out = attach_industry_sw(panel, industry)

        self.assertEqual(out.loc[0, "sw_l1_code"], "801010")
        self.assertEqual(out.loc[0, "sw_l1_name"], "旧行业")
        self.assertEqual(out.loc[1, "sw_l1_code"], "801020")
        self.assertEqual(out.loc[1, "industry_source"], "shenwan_l1")

    def test_asof_industry_join_marks_missing_source(self):
        panel = pd.DataFrame({"date": pd.to_datetime(["2020-06-30"]), "code": ["000002"]})
        industry = pd.DataFrame(
            {
                "code": ["000001"],
                "l1_index_code": ["801010"],
                "l2_index_code": ["801011"],
                "l3_index_code": ["851011"],
                "l1_industry_name": ["行业"],
                "in_date": ["2019-01-01"],
                "out_date": [None],
                "updated_at": ["2020-01-01 09:00:00"],
            }
        )

        out = attach_industry_sw(panel, industry)

        self.assertTrue(pd.isna(out.loc[0, "sw_l1_code"]))
        self.assertEqual(out.loc[0, "industry_source"], "missing")

    def test_asof_industry_join_uses_sw_cache_fields_and_warns_on_ambiguous_rows(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2022-06-30"]),
                "code": ["000001"],
                "cf_yield": [0.01],
            }
        )
        industry = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "sw_l1_code": ["801010", "801020"],
                "sw_l2_code": ["801011", "801021"],
                "sw_l3_code": ["851011", "851021"],
                "sw_l1_name": ["old", "new"],
                "sw_l2_name": ["old_l2", "new_l2"],
                "sw_l3_name": ["old_l3", "new_l3"],
                "in_date": ["2020-01-01", "2021-01-01"],
                "out_date": [None, None],
                "updated_at": ["2020-01-01 09:00:00", "2021-02-01 09:00:00"],
            }
        )
        warnings_rows: list[dict[str, object]] = []

        out = attach_industry_sw(panel, industry, warnings_rows=warnings_rows)

        self.assertEqual(out.loc[0, "sw_l1_code"], "801020")
        self.assertEqual(out.loc[0, "sw_l1_name"], "new")
        self.assertEqual(out.loc[0, "industry_source"], "ambiguous")
        self.assertEqual(len(warnings_rows), 1)
        self.assertEqual(warnings_rows[0]["warning_type"], "ambiguous_industry_match")

    def test_factor_processor_neutralizes_market_cap_and_industry_exposure(self):
        industries = np.array(["801010"] * 20 + ["801020"] * 20 + ["801030"] * 20)
        caps = np.linspace(1e10, 8e10, 60)
        lncap = np.log(caps)
        industry_effect = pd.Series(industries).map({"801010": -1.5, "801020": 0.25, "801030": 1.25}).to_numpy()
        values = 1.8 * lncap + industry_effect + np.sin(np.arange(60)) * 0.01
        panel = processor_panel(values=list(values), caps=caps)
        panel["sw_l1_code"] = industries

        out = FactorProcessor(["cf_yield"]).process(panel)
        valid = out[["cf_yield_neutral", "ln_total_market_cap", "sw_l1_code"]].dropna()

        corr = valid["cf_yield_neutral"].corr(valid["ln_total_market_cap"])
        group_means = valid.groupby("sw_l1_code")["cf_yield_neutral"].mean().abs()
        self.assertAlmostEqual(float(corr), 0.0, places=10)
        self.assertLess(float(group_means.max()), 1e-10)
        self.assertEqual(set(out["cf_yield_neutral_status"]), {"ok"})
        self.assertEqual(set(out["factor_neutralization_mode"]), {"market_cap_industry"})

    def test_factor_processor_falls_back_when_only_one_industry_exists(self):
        caps = np.linspace(1e10, 5e10, 40)
        panel = processor_panel(values=list(np.linspace(0.01, 0.05, 40)), caps=caps)
        panel["sw_l1_code"] = "801010"

        out = FactorProcessor(["cf_yield"]).process(panel)

        self.assertEqual(set(out["cf_yield_neutral_status"]), {"fallback_market_cap_only"})
        self.assertTrue(out["cf_yield_neutral"].notna().any())
        self.assertEqual(set(out["factor_neutralization_mode"]), {"market_cap_industry"})

    def test_factor_processor_marks_insufficient_sample(self):
        panel = processor_panel(values=list(np.linspace(0.01, 0.05, 10)), caps=np.linspace(1e10, 2e10, 10))

        out = FactorProcessor(["cf_yield"]).process(panel)

        self.assertTrue(out["cf_yield_neutral"].isna().all())
        self.assertEqual(set(out["cf_yield_neutral_status"]), {"insufficient_sample"})

    def test_default_neutral_factors_include_price_reserve_factors(self):
        self.assertIn("reversal_20d", DEFAULT_NEUTRAL_FACTORS)
        self.assertIn("volatility_20d", DEFAULT_NEUTRAL_FACTORS)

        panel = processor_panel(values=list(np.linspace(0.01, 0.05, 40)), caps=np.linspace(1e10, 5e10, 40))
        panel["cashflow_quality_score"] = np.linspace(0.2, 0.8, 40)
        panel["reversal_20d"] = np.sin(np.arange(40) / 3.0)
        panel["volatility_20d"] = np.cos(np.arange(40) / 4.0)

        out = FactorProcessor(DEFAULT_NEUTRAL_FACTORS, neutralization_mode="market_cap").process(panel)

        for column in [
            "cf_yield_neutral",
            "cashflow_quality_score_neutral",
            "reversal_20d_neutral",
            "volatility_20d_neutral",
        ]:
            self.assertIn(column, out.columns)
            self.assertTrue(out[column].notna().any())

    def test_add_composite_alpha_combines_complete_neutral_components(self):
        panel = pd.DataFrame(
            {
                "cf_yield_neutral": [1.0, 1.0, np.nan, 1.0],
                "reversal_20d_neutral": [0.5, np.nan, 0.5, 0.5],
                "volatility_20d_neutral": [0.25, 0.25, 0.25, np.nan],
            }
        )

        out = add_composite_alpha(panel)

        self.assertAlmostEqual(out.loc[0, "composite_alpha"], 1.25)
        self.assertTrue(np.isnan(out.loc[1, "composite_alpha"]))
        self.assertTrue(np.isnan(out.loc[2, "composite_alpha"]))
        self.assertTrue(np.isnan(out.loc[3, "composite_alpha"]))

    def test_add_composite_alpha_reads_rank_ic_weights_and_flips_negative_direction(self):
        panel = pd.DataFrame(
            {
                "cf_yield_neutral": [1.0],
                "reversal_20d_neutral": [2.0],
                "volatility_20d_neutral": [3.0],
            }
        )
        with TemporaryDirectory() as tmp:
            ic_path = Path(tmp) / "ic_summary.csv"
            pd.DataFrame(
                {
                    "factor": ["cf_yield_neutral", "reversal_20d_neutral", "volatility_20d_neutral"],
                    "metric": ["rank_ic", "rank_ic", "rank_ic"],
                    "mean": [0.1, 0.2, -0.7],
                }
            ).to_csv(ic_path, index=False)

            out = add_composite_alpha(panel, ic_summary_path=ic_path)

        self.assertAlmostEqual(out.loc[0, "composite_alpha"], 0.0)
        self.assertAlmostEqual(out.loc[0, "composite_alpha_ic_weighted"], 0.1 * 1.0 + 0.2 * 2.0 - 0.7 * 3.0)
        self.assertEqual(out.loc[0, "ic_weight_source"], str(ic_path).replace("\\", "/"))
        self.assertAlmostEqual(out.loc[0, "ic_weight_cf_yield_neutral"], 0.1)
        self.assertAlmostEqual(out.loc[0, "ic_weight_reversal_20d_neutral"], 0.2)
        self.assertAlmostEqual(out.loc[0, "ic_weight_volatility_20d_neutral"], 0.7)
        self.assertEqual(out.loc[0, "ic_direction_volatility_20d_neutral"], -1.0)

    def test_add_composite_alpha_falls_back_when_ic_summary_missing(self):
        panel = pd.DataFrame(
            {
                "cf_yield_neutral": [3.0],
                "reversal_20d_neutral": [6.0],
                "volatility_20d_neutral": [9.0],
            }
        )

        out = add_composite_alpha(panel, ic_summary_path=Path("missing_ic_summary.csv"))

        self.assertAlmostEqual(out.loc[0, "composite_alpha_ic_weighted"], 0.0)
        self.assertEqual(out.loc[0, "ic_weight_source"], "fallback")
        self.assertAlmostEqual(out.loc[0, "ic_weight_cf_yield_neutral"], 1.0 / 3.0)
        self.assertAlmostEqual(out.loc[0, "ic_weight_reversal_20d_neutral"], 1.0 / 3.0)
        self.assertAlmostEqual(out.loc[0, "ic_weight_volatility_20d_neutral"], 1.0 / 3.0)
        self.assertEqual(out.loc[0, "ic_direction_volatility_20d_neutral"], -1.0)

    def test_ic_weighted_composite_is_nan_when_any_component_is_missing(self):
        panel = pd.DataFrame(
            {
                "cf_yield_neutral": [1.0, 1.0],
                "reversal_20d_neutral": [2.0, np.nan],
                "volatility_20d_neutral": [3.0, 3.0],
            }
        )

        out = add_composite_alpha(panel, ic_summary_path=Path("missing_ic_summary.csv"))

        self.assertTrue(np.isfinite(out.loc[0, "composite_alpha_ic_weighted"]))
        self.assertTrue(np.isnan(out.loc[1, "composite_alpha_ic_weighted"]))

    def test_build_factor_panel_outputs_neutral_core_factors_and_industry_columns(self):
        periods = 220
        stocks = [
            make_stock_with_financials(f"{i:06d}", "2024-01-01", periods, 1e10 + i * 1e9, 100.0 + i)
            for i in range(40)
        ]
        path = np.linspace(0.0, 1.0, periods)
        for i, stock in enumerate(stocks):
            stock.price["total_market_cap"] = (1e10 + i * 1e9) * (
                1.0 + (0.04 + i * 0.002) * path + (0.01 * (i % 5)) * path**2
            )
        industry = pd.DataFrame(
            {
                "code": [stock.code for stock in stocks],
                "l1_index_code": ["801010" if i % 2 == 0 else "801020" for i, stock in enumerate(stocks)],
                "l2_index_code": ["801011" if i % 2 == 0 else "801021" for i, stock in enumerate(stocks)],
                "l3_index_code": ["851011" if i % 2 == 0 else "851021" for i, stock in enumerate(stocks)],
                "l1_industry_name": ["行业A" if i % 2 == 0 else "行业B" for i, stock in enumerate(stocks)],
                "in_date": ["2020-01-01"] * len(stocks),
                "out_date": [None] * len(stocks),
                "updated_at": ["2024-01-01 00:00:00"] * len(stocks),
            }
        )

        panel = build_factor_panel(stocks, holding_days=20, min_history_days=120, industry_sw=industry)

        self.assertIn("cf_yield_neutral", panel.columns)
        self.assertIn("cashflow_quality_score_neutral", panel.columns)
        self.assertIn("ln_total_market_cap", panel.columns)
        self.assertIn("sw_l1_code", panel.columns)
        self.assertIn("sw_l1_name", panel.columns)
        self.assertIn("industry_source", panel.columns)
        self.assertIn("factor_neutralization_mode", panel.columns)
        self.assertIn("reversal_20d", panel.columns)
        self.assertIn("volatility_20d", panel.columns)
        self.assertIn("reversal_20d_neutral", panel.columns)
        self.assertIn("volatility_20d_neutral", panel.columns)
        self.assertIn("composite_alpha", panel.columns)
        self.assertIn("composite_alpha_ic_weighted", panel.columns)
        self.assertGreater(panel["cf_yield_neutral"].notna().sum(), 0)
        self.assertGreater(panel["cashflow_quality_score_neutral"].notna().sum(), 0)
        self.assertGreater(panel["reversal_20d_neutral"].notna().sum(), 0)
        self.assertGreater(panel["volatility_20d_neutral"].notna().sum(), 0)


def make_stock(code: str, start: str, periods: int) -> StockData:
    dates = pd.date_range(start, periods=periods, freq="D")
    price = pd.DataFrame(
            {
                "date": dates,
                "close": np.linspace(10.0, 20.0, periods),
                "amount": [1000.0] * periods,
                "high": np.linspace(10.5, 20.5, periods),
                "low": np.linspace(9.5, 19.5, periods),
                "turnover": [0.5] * periods,
                "total_market_cap": np.linspace(1000.0, 2000.0, periods),
            }
        )
    return StockData(
        code=code,
        name=code,
        industry=None,
        market_cap=None,
        float_market_cap=None,
        price=price,
        cashflow=pd.DataFrame(),
        profit=pd.DataFrame(),
        moneyflow=pd.DataFrame(),
    )


def unit_guard_frame(operating_cashflow: list[float], total_market_cap: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-31"] * len(operating_cashflow)),
            "code": [f"{i:06d}" for i in range(len(operating_cashflow))],
            "operating_cashflow": operating_cashflow,
            "total_market_cap": total_market_cap,
        }
    )


def processor_panel(values: list[float], caps: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-31"] * len(values)),
            "code": [f"{i:06d}" for i in range(len(values))],
            "cf_yield": values,
            "total_market_cap_cny": caps,
        }
    )


def make_stock_with_financials(
    code: str,
    start: str,
    periods: int,
    start_cap: float,
    operating_cashflow: float,
) -> StockData:
    stock = make_stock(code, start, periods)
    stock.price["total_market_cap"] = np.linspace(start_cap, start_cap * 1.2, periods)
    stock.cashflow = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]),
            "announce_date": pd.to_datetime(["2023-04-30", "2023-08-30", "2023-10-30", "2024-04-30"]),
            "operating_cashflow": [
                operating_cashflow,
                operating_cashflow * 1.1,
                operating_cashflow * 1.2,
                operating_cashflow * 1.3,
            ],
        }
    )
    stock.profit = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]),
            "announce_date": pd.to_datetime(["2023-04-30", "2023-08-30", "2023-10-30", "2024-04-30"]),
            "revenue": [1000.0, 1100.0, 1200.0, 1300.0],
            "parent_net_profit": [50.0, 55.0, 60.0, 65.0],
        }
    )
    return stock


if __name__ == "__main__":
    unittest.main()
