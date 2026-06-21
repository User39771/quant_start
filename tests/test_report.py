from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from aq_factor_lab.backtest_engine import BacktestConfig, BacktestResult
from aq_factor_lab.report import (
    render_backtest_report,
    render_markdown_report,
    save_backtest_outputs,
)


class ReportTests(unittest.TestCase):
    def test_saved_backtest_report_uses_default_ic_weighted_factor_and_rank_buffer(self):
        result = BacktestResult(
            nav=pd.DataFrame(),
            holdings=pd.DataFrame(),
            trades=pd.DataFrame(),
            metrics=pd.DataFrame(),
            warnings=pd.DataFrame(),
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = save_backtest_outputs(
                result,
                root / "data",
                root / "reports",
                BacktestConfig(),
            )

            report = report_path.read_text(encoding="utf-8")

        self.assertIn("factor=composite_alpha_ic_weighted", report)
        self.assertIn("keep_rank_threshold=100", report)
        self.assertIn("benchmark=tradable_universe_equal_weight", report)

    def test_backtest_report_includes_strategy_metrics_and_qa(self):
        nav = pd.DataFrame(
            {
                "date": ["2025-02-28", "2025-03-31"],
                "nav": [1.01, 0.99],
                "gross_return": [0.012, -0.019],
                "net_return": [0.01, -0.0198],
                "turnover": [1.0, 0.4],
                "transaction_cost": [0.002, 0.0008],
                "selected_count": [50, 48],
                "liquidity_filtered_count": [10, 14],
                "untradable_filtered_count": [2, 4],
                "buyable_count": [70, 60],
                "return_source": ["total_market_cap_month_end", "total_market_cap_month_end"],
                "benchmark_return": [0.006, -0.01],
                "benchmark_count": [100, 98],
                "benchmark_nav": [1.006, 0.99594],
                "excess_return": [0.004, -0.0098],
                "excess_nav": [1.004, 0.9941608],
            }
        )
        metrics = pd.DataFrame(
            {
                "metric": [
                    "annualized_return",
                    "max_drawdown",
                    "sharpe_ratio",
                    "annualized_turnover",
                    "annualized_excess_return",
                    "excess_max_drawdown",
                    "information_ratio",
                    "average_liquidity_filtered_count",
                    "average_untradable_filtered_count",
                ],
                "value": [0.12, -0.05, 1.2, 8.4, 0.03, -0.02, 0.4, 12.0, 3.0],
                "note": ["", "", "", "", "", "", "", "", ""],
            }
        )
        warnings = pd.DataFrame(
            {
                "warning_type": ["selected_count_below_top_n", "missing_period_return"],
                "count": [1, 3],
            }
        )

        report = render_backtest_report(
            nav=nav,
            metrics=metrics,
            warnings=warnings,
            factor="cf_yield_neutral",
            top_n=50,
            transaction_cost_rate=0.002,
            keep_rank_threshold=100,
        )

        self.assertIn("strategy=monthly_rebalanced_top50_equal_weight", report)
        self.assertIn("factor=cf_yield_neutral", report)
        self.assertIn("keep_rank_threshold=100", report)
        self.assertIn("liquidity_filter=amount_20d>=50000000", report)
        self.assertIn("tradability_filter=amount>0_and_high_ne_low", report)
        self.assertIn("buy_side_constraints=enabled", report)
        self.assertIn("return_source=total_market_cap_month_end", report)
        self.assertIn("benchmark=tradable_universe_equal_weight", report)
        self.assertIn("benchmark_liquidity_filter=amount_20d>=50000000", report)
        self.assertIn("benchmark_tradability_filter=amount>0_and_high_ne_low", report)
        self.assertIn("benchmark_return_source=total_market_cap_month_end", report)
        self.assertIn("ending_benchmark_nav=0.99594", report)
        self.assertIn("ending_excess_nav=0.9941608", report)
        self.assertIn("annualized_return=0.12", report)
        self.assertIn("annualized_excess_return=0.03", report)
        self.assertIn("excess_max_drawdown=-0.02", report)
        self.assertIn("information_ratio=0.4", report)
        self.assertIn("average_benchmark_count=99", report)
        self.assertIn("min_benchmark_count=98", report)
        self.assertIn("max_benchmark_count=100", report)
        self.assertIn("average_liquidity_filtered_count=12", report)
        self.assertIn("average_untradable_filtered_count=3", report)
        self.assertIn("average_buyable_count=65", report)
        self.assertIn("min_buyable_count=60", report)
        self.assertIn("max_buyable_count=70", report)
        self.assertIn("average_monthly_benchmark_return=-0.002", report)
        self.assertIn("average_monthly_excess_return=-0.0029", report)
        self.assertIn("benchmark_missing_periods=0", report)
        self.assertIn("valid_excess_periods=2", report)
        self.assertIn("selected_count_below_top_n=1", report)
        self.assertIn("missing_period_return=3", report)
        self.assertIn("Excess return = strategy net return - benchmark return.", report)
        self.assertIn("amount_20d is the trailing 20-trading-day mean of raw CNY amount.", report)
        self.assertIn("Rank Buffer retains previous holdings that remain buyable and rank within keep_rank_threshold.", report)
        self.assertIn("transaction_cost_rate is a one-way rate per traded notional", report)
        self.assertIn("Buy-side liquidity filter removes stocks with amount_20d < 50,000,000 or missing amount_20d.", report)
        self.assertIn("Buy-side tradability filter removes stocks with amount == 0, high == low, or missing tradability fields.", report)
        self.assertIn("Benchmark applies the same rebalance-date liquidity and tradability filters as strategy buys.", report)
        self.assertIn("Sell-side execution model blocks same-day exits", report)
        self.assertIn("Current phase still does not fully model explicit limit-down exit prices", report)
        self.assertIn("IR = mean(excess_return) / std(excess_return) * sqrt(12).", report)

    def test_report_flags_insufficient_sample(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31", "2025-01-31"]),
                "code": ["600519", "000001"],
                "cashflow_quality_score": [0.1, 0.2],
                "main_moneyflow_score": [None, None],
                "forward_return_20d": [0.01, -0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-31"]),
                    "stocks": [2],
                    "main_moneyflow_score_coverage": [0.0],
                }
            ),
            "ic_summary": pd.DataFrame({"factor": ["cashflow_quality_score"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "universe_size": 20,
                "effective_stocks": 2,
                "price_usable_rate": 0.1,
                "price_success_rate": 0.2,
                "cache_fallbacks": 1,
                "fetch_failures": 3,
            },
        )

        self.assertIn("10.0%", report)
        self.assertIn("IC", report)

    def test_report_marks_unknown_price_adjustment_as_exploratory(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cashflow_quality_score": [0.1],
                "main_moneyflow_score": [None],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cashflow_quality_score"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "data_source": "db_cache",
                "price_adjustment": "unknown",
                "price_missing_rate": 0.125,
                "endpoint_coverage": {"price": 0.9},
                "sync_counts": {"failed": 1, "skipped": 2, "partial": 3},
                "unit_summary": {"amount": "yuan x1"},
                "price_date_ranges": {"600519": "2025-01-01..2025-01-31"},
            },
        )

        self.assertIn("data_source=db_cache", report)
        self.assertIn("price_adjustment=unknown", report)
        self.assertIn("exploratory / not for decision", report)
        self.assertIn("price_missing_rate=12.5%", report)

    def test_report_marks_unadjusted_price_warning_as_mathematically_invalid(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cashflow_quality_score": [0.1],
                "main_moneyflow_score": [None],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-31"]),
                    "stocks": [1],
                    "main_moneyflow_score_coverage": [0.0],
                }
            ),
            "ic_summary": pd.DataFrame({"factor": ["cashflow_quality_score"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "price_adjustment": "unknown",
                "price_adjustment_warning": "警告：价格未复权，收益率计算包含除权除息带来的极度失真，后续必须引入复权因子。",
                "moneyflow_status": "disabled_or_missing",
            },
        )

        self.assertIn("警告：价格未复权", report)
        self.assertIn("mathematically invalid", report)
        self.assertIn("moneyflow_status=disabled_or_missing", report)

    def test_report_marks_market_cap_proxy_methodology_without_invalid_warning(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cashflow_quality_score": [0.1],
                "cf_yield": [0.05],
                "main_moneyflow_score": [None],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cf_yield"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "data_source": "db_cache",
                "price_adjustment": "market_cap_proxy",
                "return_source": "total_market_cap",
                "market_cap_unit_multiplier": 10000,
                "cf_yield_unit_guard_status": "ok",
                "methodology_note": "由于底层数据库缺乏复权因子，本次回测使用总市值变化率近似替代个股收益率，成功排除了拆股带来的断崖式噪音，但微幅低估了实际的现金分红回报。",
            },
        )

        self.assertIn("price_adjustment=market_cap_proxy", report)
        self.assertIn("return_source=total_market_cap", report)
        self.assertIn("market_cap_unit_multiplier=10000", report)
        self.assertIn("总市值变化率", report)
        self.assertNotIn("mathematically invalid", report)
        self.assertNotIn("exploratory / not for decision", report)

    def test_report_includes_factor_processing_metadata(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cashflow_quality_score_neutral": [0.1],
                "cf_yield_neutral": [0.05],
                "main_moneyflow_score": [None],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cf_yield_neutral"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "factor_processing": "mad_zscore_market_cap_neutralized",
                "factor_processing_mad_multiplier": 3.5,
                "factor_processing_ols_x": "ln_total_market_cap",
                "factor_processing_min_regression_samples": 20,
                "neutral_factor_coverage": {"cf_yield_neutral": "96.9%"},
                "industry_neutralization_status": "sw_found_not_applied",
            },
        )

        self.assertIn("factor_processing=mad_zscore_market_cap_neutralized", report)
        self.assertIn("factor_processing_mad_multiplier=3.5", report)
        self.assertIn("factor_processing_ols_x=ln_total_market_cap", report)
        self.assertIn("neutral_factor_coverage.cf_yield_neutral=96.9%", report)
        self.assertIn("industry_neutralization_status=sw_found_not_applied", report)

    def test_report_includes_ic_weighted_composite_metadata(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cf_yield_neutral": [0.05],
                "reversal_20d_neutral": [0.1],
                "volatility_20d_neutral": [-0.1],
                "composite_alpha_ic_weighted": [0.12],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cf_yield_neutral"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "ic_weight_source": "data/processed/ic_summary.csv",
                "ic_weight": {
                    "cf_yield_neutral.rank_ic_mean": 0.03,
                    "cf_yield_neutral.direction": 1.0,
                    "cf_yield_neutral.weight": 0.18,
                    "volatility_20d_neutral.rank_ic_mean": -0.09,
                    "volatility_20d_neutral.direction": -1.0,
                    "volatility_20d_neutral.weight": 0.55,
                },
            },
        )

        self.assertIn("ic_weight_source=data/processed/ic_summary.csv", report)
        self.assertIn("ic_weight.cf_yield_neutral.rank_ic_mean=0.03", report)
        self.assertIn("ic_weight.volatility_20d_neutral.direction=-1.0", report)
        self.assertIn("ic_weight.volatility_20d_neutral.weight=0.55", report)

    def test_report_includes_quant_methodology_risk_caveats(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cf_yield_neutral": [0.05],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cf_yield_neutral"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "universe_survivorship_status": "current_universe_price_history_only",
                "financial_available_date_policy": "announce_date_else_report_date_plus_120d",
                "cashflow_statement_basis": "ttm_from_cumulative_quarterly_flows",
                "sell_side_execution_constraints": "same_day_untradable_forced_hold_minimal_model",
            },
        )

        self.assertIn("universe_survivorship_status=current_universe_price_history_only", report)
        self.assertIn("survivorship_bias_caveat", report)
        self.assertIn("financial_available_date_policy=announce_date_else_report_date_plus_120d", report)
        self.assertIn("cashflow_statement_basis=ttm_from_cumulative_quarterly_flows", report)
        self.assertIn("sell_side_execution_constraints=same_day_untradable_forced_hold_minimal_model", report)

    def test_report_includes_factor_correlation_diagnostics_without_dropping_sections(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cf_yield_neutral": [0.05],
                "reversal_20d_neutral": [0.1],
                "volatility_20d_neutral": [-0.1],
                "forward_return_20d": [0.01],
            }
        )
        factor_correlation = pd.DataFrame(
            {
                "cf_yield_neutral": [1.0, 0.2, -0.15],
                "reversal_20d_neutral": [0.2, 1.0, -0.72],
                "volatility_20d_neutral": [-0.15, -0.72, 1.0],
            },
            index=["cf_yield_neutral", "reversal_20d_neutral", "volatility_20d_neutral"],
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame(
                {
                    "factor": ["cf_yield_neutral"],
                    "metric": ["rank_ic"],
                    "periods": [1],
                    "mean": [0.2],
                }
            ),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
            "factor_correlation": factor_correlation,
        }

        report = render_markdown_report(panel, results)

        self.assertIn("## Factor Correlation Diagnostics", report)
        self.assertIn("method=spearman", report)
        self.assertIn("cf_yield_neutral vs reversal_20d_neutral=0.2000", report)
        self.assertIn("reversal_20d_neutral vs volatility_20d_neutral=-0.7200", report)
        self.assertIn("high_collinearity=yes", report)
        self.assertIn("direction_conflict_risk=yes", report)
        self.assertIn("## IC", report)
        self.assertIn("## 分组收益", report)
        self.assertIn("## 覆盖率提示", report)

    def test_report_includes_shenwan_industry_neutralization_metadata(self):
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-31"]),
                "code": ["600519"],
                "cashflow_quality_score_neutral": [0.1],
                "cf_yield_neutral": [0.05],
                "main_moneyflow_score": [None],
                "forward_return_20d": [0.01],
            }
        )
        results = {
            "coverage": pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "stocks": [1]}),
            "ic_summary": pd.DataFrame({"factor": ["cf_yield_neutral"], "periods": [0]}),
            "yearly_ic": pd.DataFrame(),
            "groups": pd.DataFrame(),
        }

        report = render_markdown_report(
            panel,
            results,
            {
                "factor_processing": "mad_zscore_market_cap_industry_neutralized",
                "industry_neutralization": "shenwan_l1",
                "industry_coverage": 0.875,
                "industry_neutralization_fallback_rate": 0.125,
                "methodology_note": "本轮因子已对总市值与申万一级行业进行截面中性化；行业缺失或截面样本不足时回退为仅市值中性化。",
            },
        )

        self.assertIn("factor_processing=mad_zscore_market_cap_industry_neutralized", report)
        self.assertIn("industry_neutralization=shenwan_l1", report)
        self.assertIn("industry_coverage=87.5%", report)
        self.assertIn("industry_neutralization_fallback_rate=12.5%", report)
        self.assertIn("本轮因子已对总市值与申万一级行业进行截面中性化", report)


if __name__ == "__main__":
    unittest.main()
