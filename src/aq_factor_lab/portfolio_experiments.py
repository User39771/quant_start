from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .backtest_engine import BacktestConfig, MonthlyRebalanceBacktester


@dataclass(frozen=True)
class PortfolioExperimentConfig:
    name: str
    top_n: int
    buy_rank: int
    sell_rank: int
    max_turnover: float | None = None
    min_position_weight: float = 0.0
    dust_threshold: float = 0.0
    max_positions: int | None = None
    sell_priority: str = "worst_rank_first"
    weighting_method: str = "equal_weight"


def default_portfolio_experiments() -> list[PortfolioExperimentConfig]:
    return [
        PortfolioExperimentConfig("baseline_top50_equal_no_buffer", top_n=50, buy_rank=50, sell_rank=50),
        PortfolioExperimentConfig("top100_equal", top_n=100, buy_rank=100, sell_rank=100),
        PortfolioExperimentConfig("top200_equal", top_n=200, buy_rank=200, sell_rank=200),
        PortfolioExperimentConfig("top50_buy50_sell150", top_n=50, buy_rank=50, sell_rank=150),
        PortfolioExperimentConfig("top100_buy100_sell300", top_n=100, buy_rank=100, sell_rank=300),
        PortfolioExperimentConfig(
            "top100_buy100_sell300_max_turnover_0.5",
            top_n=100,
            buy_rank=100,
            sell_rank=300,
            max_turnover=0.5,
        ),
        PortfolioExperimentConfig(
            "top100_buy100_sell300_max_turnover_0.5_dust_maxpos300",
            top_n=100,
            buy_rank=100,
            sell_rank=300,
            max_turnover=0.5,
            min_position_weight=0.001,
            dust_threshold=0.0005,
            max_positions=300,
        ),
    ]


def run_portfolio_experiments(
    panel: pd.DataFrame,
    experiments: list[PortfolioExperimentConfig] | None = None,
    *,
    factor_col: str = "composite_alpha_ic_weighted",
    transaction_cost_rate: float = 0.002,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    configs = experiments if experiments is not None else default_portfolio_experiments()
    metric_rows: list[dict[str, object]] = []
    nav_rows: list[pd.DataFrame] = []
    for experiment in configs:
        backtest_config = BacktestConfig(
            factor_col=factor_col,
            top_n=experiment.top_n,
            buy_rank=experiment.buy_rank,
            sell_rank=experiment.sell_rank,
            keep_rank_threshold=experiment.sell_rank,
            max_turnover=experiment.max_turnover,
            min_position_weight=experiment.min_position_weight,
            dust_threshold=experiment.dust_threshold,
            max_positions=experiment.max_positions,
            sell_priority=experiment.sell_priority,
            weighting_method=experiment.weighting_method,
            transaction_cost_rate=transaction_cost_rate,
        )
        result = MonthlyRebalanceBacktester(backtest_config).run(panel)
        metrics = _metrics_dict(result.metrics)
        metric_rows.append(
            {
                "experiment": experiment.name,
                "factor": factor_col,
                "top_n": experiment.top_n,
                "buy_rank": experiment.buy_rank,
                "sell_rank": experiment.sell_rank,
                "max_turnover": experiment.max_turnover,
                "min_position_weight": experiment.min_position_weight,
                "dust_threshold": experiment.dust_threshold,
                "max_positions": experiment.max_positions,
                "sell_priority": experiment.sell_priority,
                "weighting_method": experiment.weighting_method,
                "annualized_return": metrics.get("annualized_return"),
                "annualized_excess_return": metrics.get("annualized_excess_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "excess_max_drawdown": metrics.get("excess_max_drawdown"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "information_ratio": metrics.get("information_ratio"),
                "annualized_turnover": metrics.get("annualized_turnover"),
                "average_holding_count": metrics.get("average_holding_count"),
                "median_holding_count": metrics.get("median_holding_count"),
                "max_holding_count": metrics.get("max_holding_count"),
                "min_holding_count": metrics.get("min_holding_count"),
                "average_trade_count": metrics.get("average_trade_count"),
                "average_buy_count": metrics.get("average_buy_count"),
                "average_sell_count": metrics.get("average_sell_count"),
                "average_partial_sell_count": metrics.get("average_partial_sell_count"),
                "average_attempted_sell_count": metrics.get("average_attempted_sell_count"),
                "average_blocked_sell_count": metrics.get("average_blocked_sell_count"),
                "average_blocked_sell_weight": metrics.get("average_blocked_sell_weight"),
                "average_forced_hold_count": metrics.get("average_forced_hold_count"),
                "average_forced_hold_weight": metrics.get("average_forced_hold_weight"),
                "average_transaction_cost": metrics.get("average_transaction_cost"),
                "average_positions_below_5bp": metrics.get("average_positions_below_5bp"),
                "average_positions_below_10bp": metrics.get("average_positions_below_10bp"),
                "average_positions_below_20bp": metrics.get("average_positions_below_20bp"),
                "average_weight_below_10bp": metrics.get("average_weight_below_10bp"),
                "average_top10_weight": metrics.get("average_top10_weight"),
                "average_top20_weight": metrics.get("average_top20_weight"),
                "average_effective_number_of_positions": metrics.get("average_effective_number_of_positions"),
                "turnover_from_buys": metrics.get("turnover_from_buys"),
                "turnover_from_sells": metrics.get("turnover_from_sells"),
                "average_portfolio_factor_score": metrics.get("average_portfolio_factor_score"),
                "average_benchmark_factor_score": metrics.get("average_benchmark_factor_score"),
                "average_active_factor_score": metrics.get("average_active_factor_score"),
            }
        )
        if not result.nav.empty:
            nav = result.nav.copy()
            nav.insert(0, "experiment", experiment.name)
            nav_rows.append(nav)
    nav_frame = pd.concat(nav_rows, ignore_index=True) if nav_rows else pd.DataFrame()
    return pd.DataFrame(metric_rows), nav_frame


def save_portfolio_experiment_outputs(
    metrics: pd.DataFrame,
    nav: pd.DataFrame,
    output_dir: Path,
    report_dir: Path,
    walk_forward_metrics: pd.DataFrame | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output_dir / "portfolio_experiment_metrics.csv", index=False, encoding="utf-8-sig")
    nav.to_csv(output_dir / "portfolio_experiment_nav.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / "portfolio_construction_report.md"
    report_path.write_text(render_portfolio_construction_report(metrics, walk_forward_metrics), encoding="utf-8")
    return report_path


def render_portfolio_construction_report(
    metrics: pd.DataFrame,
    walk_forward_metrics: pd.DataFrame | None = None,
) -> str:
    lines = [
        "# Portfolio Construction Experiment Report",
        "",
        "- objective=turn_existing_factor_scores_into_tradable_portfolios",
        "- factor=composite_alpha_ic_weighted",
        "- rebalance_frequency=monthly",
        "- benchmark=tradable_universe_equal_weight",
        "- transaction_cost_rate=0.002_one_way_per_traded_notional",
        "- sample_inference=in_sample_comparison_only",
        "",
        "## Why IC Is Not Portfolio Alpha",
        "",
        "- IC strong does not guarantee portfolio alpha because IC measures cross-sectional ordering, while a live portfolio realizes only selected names, weights, turnover, costs, and constraint drag.",
        "- A narrow Top 50 portfolio can amplify fast-factor noise: small rank changes force full exits and entries even when the score spread is economically weak.",
        "- Turnover directly reduces NAV through transaction_cost = turnover * one_way_cost_rate; high annualized turnover can erase a statistically useful signal.",
        "- max_turnover can also create tail positions when weight changes are only partially executed; dust and max_positions controls are used to diagnose and limit that behavior.",
        "",
        "## Experiment Metrics",
        "",
    ]
    if metrics.empty:
        lines.append("No experiment metrics were generated.")
    else:
        lines += _metrics_table(metrics)
        lines += ["", "## Interpretation", ""]
        lines += _interpretation(metrics)
        lines += ["", "## Walk-Forward Comparison", ""]
        lines += _walk_forward_section(walk_forward_metrics)
    lines += [
        "",
        "## Caveats",
        "",
        "- sample_inference=in_sample_comparison_only; do not use the best full-sample parameter as proof of strategy validity.",
        "- next_required_validation=walk_forward_or_out_of_sample",
        "- survivorship_bias_caveat=current universe membership may omit delisted historical stocks.",
        "- total_market_cap_return_proxy=not_strict_adjusted_price_return",
        "- sell_side_constraints=same_day_untradable_forced_hold_minimal_model; explicit limit-down exit prices remain incomplete",
    ]
    return "\n".join(lines)


def _walk_forward_section(walk_forward_metrics: pd.DataFrame | None) -> list[str]:
    if walk_forward_metrics is None or walk_forward_metrics.empty:
        return ["- walk_forward_status=not_run_in_this_report"]
    columns = [
        "split",
        "selected_experiment",
        "test_annualized_return",
        "test_annualized_excess_return",
        "test_information_ratio",
        "test_annualized_turnover",
    ]
    display = walk_forward_metrics[[column for column in columns if column in walk_forward_metrics]].copy()
    lines = dataframe_to_markdown(display)
    excess = pd.to_numeric(walk_forward_metrics["test_annualized_excess_return"], errors="coerce")
    selected = walk_forward_metrics["selected_experiment"].dropna().astype(str)
    lines += [
        "",
        f"- walk_forward_average_test_excess={_fmt(excess.mean())}",
        f"- walk_forward_parameter_stability={'stable' if selected.nunique() <= 1 else 'unstable'}",
        f"- walk_forward_negative_excess={'yes' if excess.mean() < 0 else 'no'}",
    ]
    if excess.mean() < 0:
        lines.append("- validation_status=failed_out_of_sample_excess_remains_negative")
    return lines


def _metrics_dict(metrics: pd.DataFrame) -> dict[str, float]:
    if metrics.empty or not {"metric", "value"}.issubset(metrics.columns):
        return {}
    values = metrics.set_index("metric")["value"]
    return {str(key): value for key, value in values.items()}


def _metrics_table(metrics: pd.DataFrame) -> list[str]:
    columns = [
        "experiment",
        "annualized_return",
        "annualized_excess_return",
        "max_drawdown",
        "excess_max_drawdown",
        "sharpe_ratio",
        "information_ratio",
        "annualized_turnover",
        "average_holding_count",
        "median_holding_count",
        "max_holding_count",
        "average_positions_below_10bp",
        "average_top10_weight",
        "average_effective_number_of_positions",
        "average_trade_count",
        "average_buy_count",
        "average_sell_count",
        "average_blocked_sell_count",
        "average_forced_hold_weight",
        "average_transaction_cost",
        "average_active_factor_score",
    ]
    display = metrics[[column for column in columns if column in metrics]].copy()
    return dataframe_to_markdown(display)


def dataframe_to_markdown(frame: pd.DataFrame) -> list[str]:
    display = frame.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    return display.to_markdown(index=False).splitlines()


def _interpretation(metrics: pd.DataFrame) -> list[str]:
    baseline = metrics[metrics["experiment"] == "baseline_top50_equal_no_buffer"]
    candidates = metrics.copy()
    numeric_cols = ["annualized_excess_return", "annualized_turnover", "information_ratio", "max_drawdown"]
    for column in numeric_cols:
        if column in candidates:
            candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    lines: list[str] = []
    if not baseline.empty:
        base = baseline.iloc[0]
        base_excess = pd.to_numeric(pd.Series([base.get("annualized_excess_return")]), errors="coerce").iloc[0]
        base_turnover = pd.to_numeric(pd.Series([base.get("annualized_turnover")]), errors="coerce").iloc[0]
        lines.append(f"- baseline_annualized_excess_return={_fmt(base_excess)}")
        lines.append(f"- baseline_annualized_turnover={_fmt(base_turnover)}")
    valid = candidates.dropna(subset=["annualized_excess_return"])
    if not valid.empty:
        best = valid.sort_values(["annualized_excess_return", "information_ratio"], ascending=[False, False]).iloc[0]
        lines.append(f"- best_in_sample_by_excess_return={best['experiment']}")
        lines.append(f"- best_in_sample_annualized_excess_return={_fmt(best['annualized_excess_return'])}")
        lines.append(f"- best_in_sample_information_ratio={_fmt(best.get('information_ratio'))}")
        if not baseline.empty:
            delta_excess = float(best["annualized_excess_return"]) - float(base_excess)
            delta_turnover = float(best.get("annualized_turnover")) - float(base_turnover)
            lines.append(f"- excess_return_improvement_vs_baseline={_fmt(delta_excess)}")
            lines.append(f"- turnover_change_vs_baseline={_fmt(delta_turnover)}")
            if delta_excess > 0:
                if float(best["annualized_excess_return"]) > 0:
                    lines.append("- result_diagnosis=positive_excess_return_improved_not_only_lower_risk")
                else:
                    lines.append("- result_diagnosis=excess_return_improved_but_remains_negative")
            else:
                lines.append("- result_diagnosis=did_not_improve_excess_return; risk_or_turnover_reduction_alone_is_insufficient")
    tail = candidates[candidates["experiment"].astype(str).str.contains("max_turnover_0.5", regex=False)]
    if not tail.empty and "average_holding_count" in tail:
        for _idx, row in tail.iterrows():
            lines.append(
                f"- holding_count_diagnostic.{row['experiment']}={_fmt(row.get('average_holding_count'))}"
            )
    return lines


def _fmt(value: object) -> str:
    if value is None or pd.isna(value):
        return "NaN"
    return f"{float(value):.10g}"
