from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from .backtest_engine import BacktestConfig, BacktestResult
from .evaluation import FACTOR_COLUMNS
from .utils import parse_cache_date


def save_outputs(
    panel: pd.DataFrame,
    results: dict[str, pd.DataFrame],
    output_dir: Path,
    report_dir: Path,
    data_quality: dict[str, Any] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_dir / "factor_panel.csv", index=False, encoding="utf-8-sig")
    for name, df in results.items():
        df.to_csv(
            output_dir / f"{name}.csv",
            index=True if name in {"correlations", "factor_correlation"} else False,
            encoding="utf-8-sig",
        )
    make_plots(results, report_dir)
    report_path = report_dir / "factor_reliability_report.md"
    report_path.write_text(render_markdown_report(panel, results, data_quality), encoding="utf-8")
    return report_path


def save_backtest_outputs(
    result: BacktestResult,
    output_dir: Path,
    report_dir: Path,
    config: BacktestConfig,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    result.nav.to_csv(output_dir / "backtest_nav.csv", index=False, encoding="utf-8-sig")
    result.holdings.to_csv(output_dir / "backtest_holdings.csv", index=False, encoding="utf-8-sig")
    result.trades.to_csv(output_dir / "backtest_trades.csv", index=False, encoding="utf-8-sig")
    result.metrics.to_csv(output_dir / "backtest_metrics.csv", index=False, encoding="utf-8-sig")
    result.warnings.to_csv(output_dir / "backtest_warnings.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / "backtest_report.md"
    report_path.write_text(
        render_backtest_report(
            nav=result.nav,
            metrics=result.metrics,
            warnings=result.warnings,
            factor=config.factor_col,
            top_n=config.top_n,
            buy_rank=config.buy_rank if config.buy_rank is not None else config.top_n,
            sell_rank=config.sell_rank if config.sell_rank is not None else config.keep_rank_threshold,
            keep_rank_threshold=config.keep_rank_threshold,
            max_turnover=config.max_turnover,
            weighting_method=config.weighting_method,
            transaction_cost_rate=config.transaction_cost_rate,
            min_amount_20d=config.min_amount_20d,
            enable_liquidity_filter=config.enable_liquidity_filter,
            enable_tradability_filter=config.enable_tradability_filter,
        ),
        encoding="utf-8",
    )
    return report_path


def render_backtest_report(
    nav: pd.DataFrame,
    metrics: pd.DataFrame,
    warnings: pd.DataFrame,
    factor: str,
    top_n: int,
    transaction_cost_rate: float,
    buy_rank: int | None = None,
    sell_rank: int | None = None,
    keep_rank_threshold: int = 100,
    max_turnover: float | None = None,
    weighting_method: str = "equal_weight",
    min_amount_20d: float = 50_000_000.0,
    enable_liquidity_filter: bool = True,
    enable_tradability_filter: bool = True,
) -> str:
    metric_values = (
        metrics.set_index("metric")["value"].to_dict()
        if not metrics.empty and {"metric", "value"}.issubset(metrics.columns)
        else {}
    )
    periods = int(nav.shape[0])
    start_date = str(nav["rebalance_date"].iloc[0]) if periods and "rebalance_date" in nav else ""
    end_date = str(nav["date"].iloc[-1]) if periods and "date" in nav else ""
    ending_nav = nav["nav"].iloc[-1] if periods and "nav" in nav else ""
    ending_benchmark_nav = nav["benchmark_nav"].iloc[-1] if periods and "benchmark_nav" in nav else ""
    ending_excess_nav = nav["excess_nav"].iloc[-1] if periods and "excess_nav" in nav else ""
    return_source = _dominant_value(nav, "return_source")
    selected = pd.to_numeric(nav["selected_count"], errors="coerce") if "selected_count" in nav else pd.Series(dtype=float)
    benchmark_count = (
        pd.to_numeric(nav["benchmark_count"], errors="coerce") if "benchmark_count" in nav else pd.Series(dtype=float)
    )
    benchmark_return = (
        pd.to_numeric(nav["benchmark_return"], errors="coerce") if "benchmark_return" in nav else pd.Series(dtype=float)
    )
    excess_return = (
        pd.to_numeric(nav["excess_return"], errors="coerce") if "excess_return" in nav else pd.Series(dtype=float)
    )
    turnover = pd.to_numeric(nav["turnover"], errors="coerce") if "turnover" in nav else pd.Series(dtype=float)
    cost = pd.to_numeric(nav["transaction_cost"], errors="coerce") if "transaction_cost" in nav else pd.Series(dtype=float)
    trade_count = pd.to_numeric(nav["trade_count"], errors="coerce") if "trade_count" in nav else pd.Series(dtype=float)
    attempted_sell = (
        pd.to_numeric(nav["attempted_sell_count"], errors="coerce")
        if "attempted_sell_count" in nav
        else pd.Series(dtype=float)
    )
    blocked_sell = (
        pd.to_numeric(nav["blocked_sell_count"], errors="coerce")
        if "blocked_sell_count" in nav
        else pd.Series(dtype=float)
    )
    forced_hold_weight = (
        pd.to_numeric(nav["forced_hold_weight"], errors="coerce")
        if "forced_hold_weight" in nav
        else pd.Series(dtype=float)
    )
    liquidity_filtered = (
        pd.to_numeric(nav["liquidity_filtered_count"], errors="coerce")
        if "liquidity_filtered_count" in nav
        else pd.Series(dtype=float)
    )
    untradable_filtered = (
        pd.to_numeric(nav["untradable_filtered_count"], errors="coerce")
        if "untradable_filtered_count" in nav
        else pd.Series(dtype=float)
    )
    buyable = pd.to_numeric(nav["buyable_count"], errors="coerce") if "buyable_count" in nav else pd.Series(dtype=float)
    warning_counts = _warning_counts(warnings)
    benchmark_missing_periods = int(benchmark_return.isna().sum()) if not benchmark_return.empty else 0
    valid_excess_periods = int(excess_return.notna().sum()) if not excess_return.empty else 0
    threshold = _format_threshold(min_amount_20d)
    liquidity_filter = f"amount_20d>={threshold}" if enable_liquidity_filter else "disabled"
    tradability_filter = "amount>0_and_high_ne_low" if enable_tradability_filter else "disabled"
    buy_side_constraints = "enabled" if enable_liquidity_filter or enable_tradability_filter else "disabled"

    lines = [
        "# Monthly Rebalanced Backtest Report",
        "",
        f"- strategy=monthly_rebalanced_top{top_n}_{weighting_method}",
        f"- factor={factor}",
        "- rebalance_frequency=monthly",
        f"- top_n={top_n}",
        f"- buy_rank={buy_rank if buy_rank is not None else top_n}",
        f"- sell_rank={sell_rank if sell_rank is not None else keep_rank_threshold}",
        f"- keep_rank_threshold={keep_rank_threshold}",
        f"- max_turnover={_format_metric(max_turnover) if max_turnover is not None else 'None'}",
        f"- weighting={weighting_method}",
        f"- transaction_cost_rate={transaction_cost_rate}",
        f"- liquidity_filter={liquidity_filter}",
        f"- tradability_filter={tradability_filter}",
        f"- buy_side_constraints={buy_side_constraints}",
        f"- return_source={return_source}",
        "- benchmark=tradable_universe_equal_weight",
        f"- benchmark_liquidity_filter={liquidity_filter}",
        f"- benchmark_tradability_filter={tradability_filter}",
        f"- benchmark_return_source={return_source}",
        f"- periods={periods}",
        f"- start_date={start_date}",
        f"- end_date={end_date}",
        f"- ending_nav={_format_metric(ending_nav)}",
        f"- ending_benchmark_nav={_format_metric(ending_benchmark_nav)}",
        f"- ending_excess_nav={_format_metric(ending_excess_nav)}",
        f"- annualized_return={_format_metric(metric_values.get('annualized_return'))}",
        f"- max_drawdown={_format_metric(metric_values.get('max_drawdown'))}",
        f"- sharpe_ratio={_format_metric(metric_values.get('sharpe_ratio'))}",
        f"- annualized_turnover={_format_metric(metric_values.get('annualized_turnover'))}",
        f"- annualized_excess_return={_format_metric(metric_values.get('annualized_excess_return'))}",
        f"- excess_max_drawdown={_format_metric(metric_values.get('excess_max_drawdown'))}",
        f"- information_ratio={_format_metric(metric_values.get('information_ratio'))}",
        "",
        "## QA",
        "",
        f"- average_selected_count={_format_metric(selected.mean() if not selected.empty else None)}",
        f"- min_selected_count={_format_metric(selected.min() if not selected.empty else None)}",
        f"- max_selected_count={_format_metric(selected.max() if not selected.empty else None)}",
        f"- average_benchmark_count={_format_metric(benchmark_count.mean() if not benchmark_count.empty else None)}",
        f"- min_benchmark_count={_format_metric(benchmark_count.min() if not benchmark_count.empty else None)}",
        f"- max_benchmark_count={_format_metric(benchmark_count.max() if not benchmark_count.empty else None)}",
        f"- average_liquidity_filtered_count={_format_metric(liquidity_filtered.mean() if not liquidity_filtered.empty else None)}",
        f"- average_untradable_filtered_count={_format_metric(untradable_filtered.mean() if not untradable_filtered.empty else None)}",
        f"- average_buyable_count={_format_metric(buyable.mean() if not buyable.empty else None)}",
        f"- min_buyable_count={_format_metric(buyable.min() if not buyable.empty else None)}",
        f"- max_buyable_count={_format_metric(buyable.max() if not buyable.empty else None)}",
        f"- average_monthly_benchmark_return={_format_metric(benchmark_return.mean() if not benchmark_return.empty else None)}",
        f"- average_monthly_excess_return={_format_metric(excess_return.mean() if not excess_return.empty else None)}",
        f"- benchmark_missing_periods={benchmark_missing_periods}",
        f"- valid_excess_periods={valid_excess_periods}",
        f"- average_monthly_turnover={_format_metric(turnover.mean() if not turnover.empty else None)}",
        f"- average_trade_count={_format_metric(trade_count.mean() if not trade_count.empty else None)}",
        f"- average_attempted_sell_count={_format_metric(attempted_sell.mean() if not attempted_sell.empty else None)}",
        f"- average_blocked_sell_count={_format_metric(blocked_sell.mean() if not blocked_sell.empty else None)}",
        f"- average_forced_hold_weight={_format_metric(forced_hold_weight.mean() if not forced_hold_weight.empty else None)}",
        f"- total_transaction_cost={_format_metric(cost.sum() if not cost.empty else None)}",
        f"- average_transaction_cost={_format_metric(cost.mean() if not cost.empty else None)}",
        f"- selected_count_below_top_n={warning_counts.get('selected_count_below_top_n', 0)}",
        f"- missing_period_return={warning_counts.get('missing_period_return', 0)}",
        "",
        "## Method",
        "",
        "- Rebalance dates are the last available trading date in each calendar month.",
        "- Holdings are selected using the current rebalance-date factor cross-section only.",
        "- Rank Buffer retains previous holdings that remain buyable and rank within sell_rank.",
        "- Rank Buffer retains previous holdings that remain buyable and rank within keep_rank_threshold.",
        "- Rank Buffer retains previous holdings that remain buyable and rank within keep_rank_threshold when sell_rank is not explicitly set.",
        "- New buys are restricted to buy_rank or better; remaining seats are filled from eligible non-retained stocks by current rank.",
        "- max_turnover, when set, scales desired weight changes toward the target portfolio and leaves residual cash if initial deployment is capped.",
        "- weighting_method controls target weights after selection: equal_weight, rank_weight, or score_weight.",
        "- Monthly return covers the holding period from the rebalance date to the next rebalance date.",
        "- Turnover is sum(abs(target_weight - previous_weight)); first entry turnover is 1.0.",
        "- Transaction cost is turnover * transaction_cost_rate; no additional factor of 2 is applied.",
        "- transaction_cost_rate is a one-way rate per traded notional; a full replacement has turnover=2.0 and costs 2 * transaction_cost_rate.",
        "- amount_20d is the trailing 20-trading-day mean of raw CNY amount.",
        f"- Buy-side liquidity filter removes stocks with amount_20d < {_format_threshold_with_commas(min_amount_20d)} or missing amount_20d.",
        "- Buy-side tradability filter removes stocks with amount == 0, high == low, or missing tradability fields.",
        "- Sell-side execution model blocks same-day exits when amount == 0, volume == 0, high == low, or available halt/status flags indicate suspension.",
        "- Blocked sells are forced holds; forced_hold_weight records the retained previous weight.",
        "- Benchmark applies the same rebalance-date liquidity and tradability filters as strategy buys.",
        "- Current phase still does not fully model explicit limit-down exit prices when limit_down data is unavailable.",
        "- Benchmark is each month tradable high-liquidity valid-stock equal-weight average period return.",
        "- Benchmark does not deduct transaction costs.",
        "- Excess return = strategy net return - benchmark return.",
        "- Excess NAV is compounded from monthly excess_return, not nav minus benchmark_nav.",
        "- IR = mean(excess_return) / std(excess_return) * sqrt(12).",
    ]
    if warning_counts:
        lines += ["", "## Warnings", ""]
        lines += [f"- {key}={value}" for key, value in sorted(warning_counts.items())]
    return "\n".join(lines)


def make_plots(results: dict[str, pd.DataFrame], report_dir: Path) -> None:
    ic = results.get("ic", pd.DataFrame())
    if not ic.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        for factor in FACTOR_COLUMNS:
            col = f"{factor}_rank_ic"
            if col in ic:
                ax.plot(parse_cache_date(ic["date"]), ic[col], marker="o", linewidth=1, label=col)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Rank IC by Month")
        ax.legend()
        fig.tight_layout()
        fig.savefig(report_dir / "rank_ic.png", dpi=150)
        plt.close(fig)

    coverage = results.get("coverage", pd.DataFrame())
    if not coverage.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        for factor in FACTOR_COLUMNS:
            col = f"{factor}_coverage"
            if col in coverage:
                ax.plot(parse_cache_date(coverage["date"]), coverage[col], marker="o", linewidth=1, label=factor)
        ax.set_ylim(0, 1.05)
        ax.set_title("Factor Coverage")
        ax.legend()
        fig.tight_layout()
        fig.savefig(report_dir / "coverage.png", dpi=150)
        plt.close(fig)

    groups = results.get("groups", pd.DataFrame())
    if not groups.empty:
        avg = groups.groupby(["factor", "bucket"])["mean_forward_return_20d"].mean().reset_index()
        for factor, df in avg.groupby("factor"):
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(df["bucket"].astype(str), df["mean_forward_return_20d"])
            ax.set_title(f"{factor} Average Forward 20D Return")
            ax.set_xlabel("Bucket: low to high")
            fig.tight_layout()
            fig.savefig(report_dir / f"{factor}_groups.png", dpi=150)
            plt.close(fig)


def render_markdown_report(
    panel: pd.DataFrame,
    results: dict[str, pd.DataFrame],
    data_quality: dict[str, Any] | None = None,
) -> str:
    lines = ["# A股现金流与主力资金因子可靠性报告", ""]
    if panel.empty:
        lines += [
            "没有生成可检验的因子面板。请先用较小股票池检查 AkShare 数据是否可访问。",
            "",
        ]
        lines += data_quality_section(panel, results, data_quality)
        return "\n".join(lines)

    panel_dates = parse_cache_date(panel["date"])
    start = panel_dates.min().date()
    end = panel_dates.max().date()
    lines += [
        "## 样本概况",
        "",
        f"- 观察期：{start} 至 {end}",
        f"- 有效股票数：{panel['code'].nunique()}",
        f"- 截面记录数：{len(panel)}",
        "- 未来收益窗口：20 个交易日",
        "",
    ]

    lines += data_quality_section(panel, results, data_quality)

    summary = results.get("ic_summary", pd.DataFrame())
    lines += ["## IC 摘要", ""]
    lines += dataframe_to_markdown(summary) if not summary.empty else ["暂无有效 IC。"]
    lines.append("")

    lines += factor_correlation_section(results.get("factor_correlation", pd.DataFrame()))

    yearly = results.get("yearly_ic", pd.DataFrame())
    lines += ["## 年度稳定性", ""]
    lines += dataframe_to_markdown(yearly) if not yearly.empty else ["暂无年度 IC。"]
    lines.append("")

    groups = results.get("groups", pd.DataFrame())
    lines += ["## 分组收益", ""]
    if not groups.empty:
        avg_groups = groups.groupby(["factor", "bucket"])["mean_forward_return_20d"].mean().reset_index()
        lines += dataframe_to_markdown(avg_groups)
    else:
        lines.append("暂无足够截面股票生成分组收益。")
    lines.append("")

    coverage = results.get("coverage", pd.DataFrame())
    lines += ["## 覆盖率提示", ""]
    if not coverage.empty:
        last = coverage.tail(1).T.reset_index()
        last.columns = ["metric", "latest_value"]
        lines += dataframe_to_markdown(last)
    else:
        lines.append("暂无覆盖率数据。")
    lines += [
        "",
        "## 方法备注",
        "",
        "- 财报若缺少公告日，使用报告期后 120 天作为可用日期，避免未来函数。",
        "- 财报因子使用公告日/披露日作为可用日期；缺失公告日时才使用 report_date + 120 天保守兜底。",
        "- 经营现金流、收入和归母净利润按累计报表拆分为单季流量后滚动四季求和，用于 TTM 口径因子。",
        "- universe_survivorship_status=current_universe_price_history_only 表示尚未接入完整上市/退市日期表；退市股票缺失仍可能造成幸存者偏差。",
        "- sell_side_constraints=not_modeled；当前回测不模拟卖出时停牌、跌停或无成交导致无法退出的约束。",
        "- 主力资金流受 AkShare/东财历史接口限制，报告以真实覆盖率为准。",
        "- 当前结果是因子可靠性检验，不包含交易成本、实盘约束或组合优化。",
        "",
        "## 图片",
        "",
        "- `rank_ic.png`",
        "- `coverage.png`",
        "- `cashflow_quality_score_neutral_groups.png`",
        "- `cf_yield_neutral_groups.png`",
        "- `main_moneyflow_score_groups.png`",
    ]
    return "\n".join(lines)


def data_quality_section(
    panel: pd.DataFrame,
    results: dict[str, pd.DataFrame],
    data_quality: dict[str, Any] | None,
) -> list[str]:
    coverage = results.get("coverage", pd.DataFrame())
    latest_moneyflow_coverage = latest_metric(coverage, "main_moneyflow_score_coverage")
    min_monthly_stocks = min_stocks_per_month(panel, coverage)
    ic_periods = max_ic_periods(results.get("ic_summary", pd.DataFrame()))

    universe_size = int(data_quality.get("universe_size", 0)) if data_quality else 0
    effective_stocks = (
        int(data_quality.get("effective_stocks", 0)) if data_quality else int(panel["code"].nunique() if not panel.empty else 0)
    )
    price_usable_rate = (
        float(data_quality.get("price_usable_rate", 0.0))
        if data_quality
        else (effective_stocks / universe_size if universe_size else 0.0)
    )
    price_success_rate = float(data_quality.get("price_success_rate", 0.0)) if data_quality else 0.0
    cache_fallbacks = int(data_quality.get("cache_fallbacks", 0)) if data_quality else 0
    fetch_failures = int(data_quality.get("fetch_failures", 0)) if data_quality else 0
    data_source = data_quality.get("data_source") if data_quality else None
    price_adjustment = data_quality.get("price_adjustment") if data_quality else None
    price_missing_rate = data_quality.get("price_missing_rate") if data_quality else None
    price_adjustment_warning = data_quality.get("price_adjustment_warning") if data_quality else None
    return_source = data_quality.get("return_source") if data_quality else None
    market_cap_unit_multiplier = data_quality.get("market_cap_unit_multiplier") if data_quality else None
    cf_yield_unit_guard_status = data_quality.get("cf_yield_unit_guard_status") if data_quality else None
    methodology_note = data_quality.get("methodology_note") if data_quality else None
    factor_processing = data_quality.get("factor_processing") if data_quality else None
    factor_processing_mad_multiplier = (
        data_quality.get("factor_processing_mad_multiplier") if data_quality else None
    )
    factor_processing_ols_x = data_quality.get("factor_processing_ols_x") if data_quality else None
    factor_processing_min_regression_samples = (
        data_quality.get("factor_processing_min_regression_samples") if data_quality else None
    )
    industry_neutralization_status = data_quality.get("industry_neutralization_status") if data_quality else None
    industry_neutralization = data_quality.get("industry_neutralization") if data_quality else None
    industry_coverage = data_quality.get("industry_coverage") if data_quality else None
    industry_neutralization_fallback_rate = (
        data_quality.get("industry_neutralization_fallback_rate") if data_quality else None
    )
    moneyflow_status = data_quality.get("moneyflow_status") if data_quality else None
    ic_weight_source = data_quality.get("ic_weight_source") if data_quality else None
    universe_survivorship_status = data_quality.get("universe_survivorship_status") if data_quality else None
    financial_available_date_policy = data_quality.get("financial_available_date_policy") if data_quality else None
    cashflow_statement_basis = data_quality.get("cashflow_statement_basis") if data_quality else None
    sell_side_execution_constraints = data_quality.get("sell_side_execution_constraints") if data_quality else None

    lines = [
        "## 数据质量提示",
        "",
        f"- 初始股票池数量：{universe_size if universe_size else '未知'}",
        f"- 最终有效股票数：{effective_stocks}",
        f"- 价格可用率：{price_usable_rate:.1%}",
        f"- 价格请求成功率：{price_success_rate:.1%}",
        f"- 资金流最新截面覆盖率：{format_optional_rate(latest_moneyflow_coverage)}",
        f"- 最小月度有效股票数：{min_monthly_stocks}",
        f"- IC 有效期数：{ic_periods}",
        f"- 缓存兜底次数：{cache_fallbacks}",
        f"- 端点失败记录数：{fetch_failures}",
    ]
    if data_source:
        lines.append(f"- data_source={data_source}")
    if price_adjustment:
        lines.append(f"- price_adjustment={price_adjustment}")
    if return_source:
        lines.append(f"- return_source={return_source}")
    if market_cap_unit_multiplier is not None:
        lines.append(f"- market_cap_unit_multiplier={market_cap_unit_multiplier}")
    if cf_yield_unit_guard_status:
        lines.append(f"- cf_yield_unit_guard_status={cf_yield_unit_guard_status}")
    if methodology_note:
        lines += ["", f"- {methodology_note}"]
    if factor_processing:
        lines.append(f"- factor_processing={factor_processing}")
    if factor_processing_mad_multiplier is not None:
        lines.append(f"- factor_processing_mad_multiplier={factor_processing_mad_multiplier}")
    if factor_processing_ols_x:
        lines.append(f"- factor_processing_ols_x={factor_processing_ols_x}")
    if factor_processing_min_regression_samples is not None:
        lines.append(f"- factor_processing_min_regression_samples={factor_processing_min_regression_samples}")
    if industry_neutralization_status:
        lines.append(f"- industry_neutralization_status={industry_neutralization_status}")
    if industry_neutralization:
        lines.append(f"- industry_neutralization={industry_neutralization}")
    if industry_coverage is not None:
        lines.append(f"- industry_coverage={float(industry_coverage):.1%}")
    if industry_neutralization_fallback_rate is not None:
        lines.append(
            f"- industry_neutralization_fallback_rate={float(industry_neutralization_fallback_rate):.1%}"
        )
    if price_adjustment_warning and price_adjustment != "market_cap_proxy":
        lines += [
            "",
            f'<span style="color:red; font-weight:700">{price_adjustment_warning}</span>',
            "",
            "**mathematically invalid:** unadjusted prices can create extreme ex-dividend return distortion.",
        ]
    if price_missing_rate is not None:
        lines.append(f"- price_missing_rate={float(price_missing_rate):.1%}")
    if moneyflow_status:
        lines.append(f"- moneyflow_status={moneyflow_status}")
    if ic_weight_source:
        lines.append(f"- ic_weight_source={ic_weight_source}")
    if universe_survivorship_status:
        lines.append(f"- universe_survivorship_status={universe_survivorship_status}")
        lines.append(
            "- survivorship_bias_caveat=current universe membership may omit delisted historical stocks; "
            "per-date rows require historical price observations but do not fully prove point-in-time listing membership."
        )
    if financial_available_date_policy:
        lines.append(f"- financial_available_date_policy={financial_available_date_policy}")
    if cashflow_statement_basis:
        lines.append(f"- cashflow_statement_basis={cashflow_statement_basis}")
    if sell_side_execution_constraints:
        lines.append(f"- sell_side_execution_constraints={sell_side_execution_constraints}")
    if data_quality:
        lines += metadata_lines("ic_weight", data_quality.get("ic_weight"))
        lines += metadata_lines("price_adjustment_fields_found", data_quality.get("price_adjustment_fields_found"))
        lines += metadata_lines("endpoint_coverage", data_quality.get("endpoint_coverage"))
        lines += metadata_lines("sync_counts", data_quality.get("sync_counts"))
        lines += metadata_lines("unit_summary", data_quality.get("unit_summary"))
        lines += metadata_lines("neutral_factor_coverage", data_quality.get("neutral_factor_coverage"))
        lines += metadata_lines(
            "industry_neutralization_fallback_reasons",
            data_quality.get("industry_neutralization_fallback_reasons"),
        )
        lines += metadata_lines(
            "qa_raw_cf_yield_ln_cap_mean_abs_corr",
            data_quality.get("qa_raw_cf_yield_ln_cap_mean_abs_corr"),
        )
        lines += metadata_lines(
            "qa_neutral_cf_yield_ln_cap_mean_abs_corr",
            data_quality.get("qa_neutral_cf_yield_ln_cap_mean_abs_corr"),
        )
        lines += metadata_lines(
            "qa_neutral_industry_dummy_max_abs_mean",
            data_quality.get("qa_neutral_industry_dummy_max_abs_mean"),
        )
        lines += metadata_lines("price_date_ranges", data_quality.get("price_date_ranges"))
    if price_adjustment == "unknown":
        lines += [
            "",
            "**exploratory / not for decision: price_adjustment=unknown.**",
        ]
    if min_monthly_stocks < 10 or ic_periods == 0:
        lines += [
            "",
            "**样本不足，IC/分组结果不可解释。** 请优先查看 `data/processed/fetch_summary.csv` 和 `fetch_failures.csv`。",
        ]
    lines.append("")
    return lines


def factor_correlation_section(matrix: pd.DataFrame) -> list[str]:
    if matrix.empty:
        return []
    factors = ["cf_yield_neutral", "reversal_20d_neutral", "volatility_20d_neutral"]
    if not set(factors).issubset(matrix.index) or not set(factors).issubset(matrix.columns):
        return []

    pairs = [
        ("cf_yield_neutral", "reversal_20d_neutral"),
        ("cf_yield_neutral", "volatility_20d_neutral"),
        ("reversal_20d_neutral", "volatility_20d_neutral"),
    ]
    pair_values = []
    for left, right in pairs:
        value = pd.to_numeric(pd.Series([matrix.loc[left, right]]), errors="coerce").iloc[0]
        pair_values.append((left, right, value))
    valid_values = [abs(float(value)) for _left, _right, value in pair_values if pd.notna(value)]
    negative_values = [float(value) for _left, _right, value in pair_values if pd.notna(value) and float(value) <= -0.5]
    high_collinearity = bool(valid_values and max(valid_values) >= 0.7)
    direction_conflict_risk = bool(negative_values)

    lines = [
        "## Factor Correlation Diagnostics",
        "",
        "- method=spearman",
        "- scope=per_date_cross_section_then_mean",
    ]
    for left, right, value in pair_values:
        lines.append(f"- {left} vs {right}={_format_correlation(value)}")
    lines += [
        f"- high_collinearity={'yes' if high_collinearity else 'no'}",
        f"- direction_conflict_risk={'yes' if direction_conflict_risk else 'no'}",
        "",
    ]
    matrix_for_report = matrix.copy()
    matrix_for_report.index.name = "factor"
    lines += dataframe_to_markdown(matrix_for_report.reset_index())
    lines.append("")
    return lines


def _format_correlation(value: object) -> str:
    if value is None or pd.isna(value):
        return "NaN"
    return f"{float(value):.4f}"


def latest_metric(df: pd.DataFrame, column: str) -> float | None:
    if df.empty or column not in df:
        return None
    value = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(value.iloc[-1]) if not value.empty else None


def min_stocks_per_month(panel: pd.DataFrame, coverage: pd.DataFrame) -> int:
    if not coverage.empty and "stocks" in coverage:
        stocks = pd.to_numeric(coverage["stocks"], errors="coerce").dropna()
        if not stocks.empty:
            return int(stocks.min())
    if panel.empty:
        return 0
    return int(panel.groupby("date")["code"].nunique().min())


def max_ic_periods(summary: pd.DataFrame) -> int:
    if summary.empty or "periods" not in summary:
        return 0
    periods = pd.to_numeric(summary["periods"], errors="coerce").dropna()
    return int(periods.max()) if not periods.empty else 0


def format_optional_rate(value: float | None) -> str:
    return "未知" if value is None else f"{value:.1%}"


def _dominant_value(df: pd.DataFrame, column: str) -> str:
    if df.empty or column not in df:
        return "unknown"
    values = df[column].dropna().astype(str)
    if values.empty:
        return "unknown"
    return values.mode().iloc[0]


def _warning_counts(warnings: pd.DataFrame) -> dict[str, int]:
    if warnings.empty or "warning_type" not in warnings:
        return {}
    result: dict[str, int] = {}
    for warning_type, group in warnings.groupby("warning_type"):
        if "count" in group:
            counts = pd.to_numeric(group["count"], errors="coerce").dropna()
            result[str(warning_type)] = int(counts.sum()) if not counts.empty else int(group.shape[0])
        else:
            result[str(warning_type)] = int(group.shape[0])
    return result


def _format_metric(value: object) -> str:
    if value is None or pd.isna(value):
        return "NaN"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _format_threshold(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.10g}"


def _format_threshold_with_commas(value: float) -> str:
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.10g}"


def metadata_lines(name: str, value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, dict):
        return [f"- {name}.{key}={item}" for key, item in sorted(value.items())]
    return [f"- {name}={value}"]


def dataframe_to_markdown(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["空表。"]
    formatted = df.copy()
    for col in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[col]):
            formatted[col] = formatted[col].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
    return formatted.to_markdown(index=False).splitlines()
