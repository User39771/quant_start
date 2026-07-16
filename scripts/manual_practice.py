"""对 stock pool v1.2 baseline 输出进行手动学习练习。

本脚本不重新回测，也不产生投资结论。它只把现有的 baseline 输出转换为
三个常见的金融时间序列练习：

1. 组合 NAV 与基准 NAV；
2. 调仓期端点回撤；
3. 基于调仓期收益的滚动 Sharpe。

这些练习对应 Python for Finance 中处理时间索引、简单收益率、复利、累计
运算和滚动窗口的基础。当前股票池使用 2026 年信息构建，因此输出只能解释为
``current-universe historical performance``，不能视为 point-in-time 回测或投资建议。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd


# 在终端或 CI 环境中生成 PNG，不依赖桌面图形界面。
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAV_PATH = PROJECT_ROOT / "reports" / "adjusted_stock_pool_baseline_nav_v1_2.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "manual_practice_v1_2"


def code6(value: object) -> str:
    """将股票或指数代码统一成六位文本，防止 CSV 读取时丢失前导零。"""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or len(text) > 6:
        raise ValueError(f"Invalid six-digit code: {value!r}")
    return text.zfill(6)


def as_bool(series: pd.Series) -> pd.Series:
    """兼容 CSV 中 true/false、TRUE/FALSE 或 Python bool 的写法。"""
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def load_practice_frame(
    nav_path: Path,
    universe_name: str,
    transaction_cost: float,
    benchmark_code: str,
) -> pd.DataFrame:
    """读取一个情景的完整 headline periods，并与指定基准严格对齐。

    使用 ``portfolio_net_return``，而不是从 NAV 反推收益率。这样可以直接看到
    baseline runner 已经扣除的交易成本。只保留 ``headline_included=true`` 的完整
    调仓期，避免诊断期、终止后的期间或最后不足 20 个交易日的 partial period
    混入年化和滚动统计。
    """
    frame = pd.read_csv(nav_path, dtype=str)
    required = {
        "next_rebalance_date",
        "portfolio_net_return",
        "portfolio_nav",
        "benchmark_code",
        "benchmark_return",
        "benchmark_nav",
        "headline_included",
        "benchmark_period_valid",
        "universe_name",
        "transaction_cost",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"NAV file is missing required columns: {missing}")

    benchmark_code = code6(benchmark_code)
    frame["benchmark_code"] = frame["benchmark_code"].map(code6)
    frame["transaction_cost"] = pd.to_numeric(frame["transaction_cost"], errors="coerce")
    frame["next_rebalance_date"] = pd.to_datetime(
        frame["next_rebalance_date"], errors="coerce"
    )

    selected = frame.loc[
        (frame["universe_name"] == universe_name)
        & np.isclose(frame["transaction_cost"], transaction_cost, equal_nan=False)
        & (frame["benchmark_code"] == benchmark_code)
        & as_bool(frame["headline_included"])
        & as_bool(frame["benchmark_period_valid"])
    ].copy()

    if selected.empty:
        raise ValueError(
            "No headline NAV rows match the requested scenario. "
            f"universe={universe_name!r}, transaction_cost={transaction_cost}, "
            f"benchmark={benchmark_code}"
        )
    if selected["next_rebalance_date"].isna().any():
        raise ValueError("Selected NAV rows contain unparseable next_rebalance_date values.")
    if selected["next_rebalance_date"].duplicated().any():
        raise ValueError("Selected scenario has duplicate period-end dates.")

    numeric_columns = [
        "portfolio_net_return",
        "portfolio_nav",
        "benchmark_return",
        "benchmark_nav",
    ]
    selected[numeric_columns] = selected[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    if selected[numeric_columns].isna().any().any():
        raise ValueError("Selected headline rows contain non-numeric NAV or return values.")
    if (selected[["portfolio_nav", "benchmark_nav"]] <= 0).any().any():
        raise ValueError("NAV must stay positive for drawdown calculations.")

    selected = selected.sort_values("next_rebalance_date").reset_index(drop=True)
    selected = selected.rename(
        columns={
            "next_rebalance_date": "period_end",
            "portfolio_net_return": "portfolio_period_return",
            "benchmark_return": "benchmark_period_return",
        }
    )
    return selected[
        [
            "period_end",
            "portfolio_period_return",
            "portfolio_nav",
            "benchmark_period_return",
            "benchmark_nav",
        ]
    ]


def add_learning_metrics(frame: pd.DataFrame, rolling_window: int) -> pd.DataFrame:
    """添加回撤和滚动 Sharpe 等学习指标。

    这里的回撤基于每 20 个交易日的 NAV 端点，因此名称使用
    ``period_endpoint_drawdown``。它可能低估一个调仓期内部发生过的日度回撤。

    滚动 Sharpe 使用零无风险利率和 20 个交易日一期的年化因子 ``sqrt(252 / 20)``。
    它用于观察风险调整收益在不同时间段的变化，不用于预测未来表现。
    """
    if rolling_window < 2:
        raise ValueError("rolling_window must be at least 2 periods.")

    result = frame.copy()
    result["portfolio_running_peak"] = result["portfolio_nav"].cummax()
    result["benchmark_running_peak"] = result["benchmark_nav"].cummax()
    result["portfolio_period_endpoint_drawdown"] = (
        result["portfolio_nav"] / result["portfolio_running_peak"] - 1.0
    )
    result["benchmark_period_endpoint_drawdown"] = (
        result["benchmark_nav"] / result["benchmark_running_peak"] - 1.0
    )

    annualization = np.sqrt(252 / 20)
    rolling_mean = result["portfolio_period_return"].rolling(rolling_window).mean()
    rolling_std = result["portfolio_period_return"].rolling(rolling_window).std(ddof=1)
    result["portfolio_rolling_sharpe"] = np.where(
        rolling_std > 0,
        rolling_mean / rolling_std * annualization,
        np.nan,
    )
    return result


def write_plots(metrics: pd.DataFrame, output_dir: Path, benchmark_code: str) -> None:
    """将三项练习可视化为 PNG，便于把公式与真实 baseline 输出对应起来。"""
    plt.style.use("seaborn-v0_8-whitegrid")

    figure, axis = plt.subplots(figsize=(11, 5.5))
    axis.plot(metrics["period_end"], metrics["portfolio_nav"], label="Portfolio NAV")
    axis.plot(
        metrics["period_end"],
        metrics["benchmark_nav"],
        label=f"Benchmark NAV ({benchmark_code})",
    )
    axis.set_title("Research Baseline NAV (period endpoints)")
    axis.set_xlabel("Period end")
    axis.set_ylabel("NAV (starts at 1.0)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "nav_vs_benchmark.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(11, 5.5))
    axis.plot(
        metrics["period_end"],
        metrics["portfolio_period_endpoint_drawdown"],
        label="Portfolio drawdown",
    )
    axis.plot(
        metrics["period_end"],
        metrics["benchmark_period_endpoint_drawdown"],
        label=f"Benchmark drawdown ({benchmark_code})",
        alpha=0.8,
    )
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_title("Period-end Drawdown (not intraperiod daily drawdown)")
    axis.set_xlabel("Period end")
    axis.set_ylabel("Drawdown")
    axis.yaxis.set_major_formatter("{x:.0%}")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "period_endpoint_drawdown.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(11, 5.5))
    axis.plot(metrics["period_end"], metrics["portfolio_rolling_sharpe"])
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_title("Rolling Sharpe (20-trading-day periods)")
    axis.set_xlabel("Period end")
    axis.set_ylabel("Rolling Sharpe, risk-free rate = 0")
    figure.tight_layout()
    figure.savefig(output_dir / "rolling_sharpe.png", dpi=150)
    plt.close(figure)


def write_notes(
    metrics: pd.DataFrame,
    output_dir: Path,
    universe_name: str,
    transaction_cost: float,
    benchmark_code: str,
    rolling_window: int,
) -> None:
    """输出可审计的学习笔记，只描述数据和公式，不评价策略优劣。"""
    endpoint_drawdown = metrics["portfolio_period_endpoint_drawdown"].min()
    note = f"""# Manual Practice v1.2

This directory is a learning exercise built from the existing adjusted-return baseline.

## Selected Scenario

- universe: `{universe_name}`
- transaction_cost: `{transaction_cost}`
- benchmark: `{benchmark_code}`
- headline period count: `{len(metrics)}`
- period range: `{metrics['period_end'].min().date()}` to `{metrics['period_end'].max().date()}`
- rolling Sharpe window: `{rolling_window}` rebalance periods

## Exercises

1. `nav_vs_benchmark.png`: compound period returns into NAV with
   `NAV_t = NAV_(t-1) * (1 + r_t)`.
2. `period_endpoint_drawdown.png`: calculate drawdown from the running NAV peak.
   The lowest period-end drawdown is `{endpoint_drawdown:.2%}`. This is not daily
   maximum drawdown and can miss intraperiod losses.
3. `rolling_sharpe.png`: compute a rolling zero-risk-free-rate Sharpe from period
   returns, annualized with `sqrt(252 / 20)`.

## Research Limits

- research_baseline_only=true
- current_universe_historical_performance=true
- point_in_time_strategy_backtest=false
- survivorship_or_future_universe_bias=true
- close_to_close_execution_assumption=true
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no investment conclusion

The outputs help practice financial time-series analysis. They are not a trading
recommendation and should not be interpreted as evidence of future performance.
"""
    (output_dir / "README.md").write_text(note, encoding="utf-8")


def run_self_check() -> None:
    """用极小样本验证复利和回撤公式，避免把学习脚本本身写错。"""
    nav = np.cumprod([1.10, 0.90])
    if not np.isclose(nav[-1], 0.99):
        raise AssertionError("Compounded NAV check failed.")

    example = pd.DataFrame(
        {
            "portfolio_nav": [1.0, 1.2, 0.96],
            "benchmark_nav": [1.0, 1.0, 1.0],
            "portfolio_period_return": [0.0, 0.2, -0.2],
            "benchmark_period_return": [0.0, 0.0, 0.0],
        }
    )
    checked = add_learning_metrics(example, rolling_window=2)
    if not np.isclose(checked.loc[2, "portfolio_period_endpoint_drawdown"], -0.2):
        raise AssertionError("Drawdown check failed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nav-path", type=Path, default=DEFAULT_NAV_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--universe", default="research_universe_v1_2")
    parser.add_argument("--transaction-cost", type=float, default=0.0)
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument(
        "--rolling-window",
        type=int,
        default=12,
        help="Number of 20-trading-day rebalance periods for rolling Sharpe.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run small formula checks before reading project data.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.self_check:
        run_self_check()
        print("Self-check passed.")

    metrics = add_learning_metrics(
        load_practice_frame(
            args.nav_path,
            args.universe,
            args.transaction_cost,
            args.benchmark,
        ),
        args.rolling_window,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.output_dir / "practice_metrics.csv", index=False)
    write_plots(metrics, args.output_dir, code6(args.benchmark))
    write_notes(
        metrics,
        args.output_dir,
        args.universe,
        args.transaction_cost,
        code6(args.benchmark),
        args.rolling_window,
    )
    print(f"Wrote learning outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
