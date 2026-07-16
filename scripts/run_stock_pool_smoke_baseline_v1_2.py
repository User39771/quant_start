from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPANDED_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_expanded_only_v1_2.csv"
RESEARCH_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"
PRICE_PANEL = ROOT / "data" / "processed" / "backtest_price_panel_v1_2.csv"
READINESS = ROOT / "reports" / "backtest_data_readiness_report.md"

OUT_SUMMARY = ROOT / "reports" / "stock_pool_smoke_baseline_v1_2.csv"
OUT_NAV = ROOT / "reports" / "stock_pool_smoke_baseline_v1_2_nav.csv"
OUT_TURNOVER = ROOT / "reports" / "stock_pool_smoke_baseline_v1_2_turnover.csv"
OUT_QA = ROOT / "reports" / "stock_pool_smoke_baseline_v1_2_data_qa.csv"
OUT_REPORT = ROOT / "reports" / "stock_pool_smoke_baseline_v1_2.md"

SMOKE_ONLY = "true"
PERFORMANCE_CONCLUSION_ALLOWED = "false"
MIN_COVERAGE_RATIO = 0.8


@dataclass(frozen=True)
class Scenario:
    universe_name: str
    universe_path: Path
    transaction_cost: float


MAIN_FIELDS = [
    "universe_name",
    "transaction_cost",
    "rebalance_date",
    "next_rebalance_date",
    "universe_count",
    "available_count",
    "coverage_ratio",
    "coverage_pass",
    "gross_return",
    "turnover",
    "cost_drag",
    "net_return",
    "nav",
    "smoke_only",
    "performance_conclusion_allowed",
]

QA_FIELDS = [
    "universe_name",
    "transaction_cost",
    "rebalance_date",
    "next_rebalance_date",
    "universe_count",
    "available_count",
    "missing_close_count",
    "dropped_codes",
    "coverage_ratio",
    "coverage_pass",
    "qa_note",
    "smoke_only",
    "performance_conclusion_allowed",
]

TURNOVER_FIELDS = [
    "universe_name",
    "transaction_cost",
    "rebalance_date",
    "next_rebalance_date",
    "turnover",
    "cost_drag",
    "previous_count",
    "target_count",
    "smoke_only",
    "performance_conclusion_allowed",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def code6(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6)[-6:]


def parse_float(value: object) -> float | None:
    try:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        value_float = float(text)
        return value_float if value_float > 0 else None
    except ValueError:
        return None


def load_universe(path: Path) -> list[str]:
    return sorted({code6(row["code"]) for row in read_csv(path)})


def scenarios() -> list[Scenario]:
    return [
        Scenario("expanded_only_v1_2", EXPANDED_UNIVERSE, 0.0),
        Scenario("expanded_only_v1_2", EXPANDED_UNIVERSE, 0.001),
        Scenario("research_universe_v1_2", RESEARCH_UNIVERSE, 0.0),
        Scenario("research_universe_v1_2", RESEARCH_UNIVERSE, 0.001),
    ]


def index_prices(rows: list[dict[str, str]]) -> dict[tuple[str, str], float | None]:
    indexed: dict[tuple[str, str], float | None] = {}
    for row in rows:
        code = code6(row.get("stock_code", ""))
        date = str(row.get("trade_date", "")).strip()
        key = (code, date)
        if key in indexed:
            raise ValueError(f"duplicate code/date in price panel: {code} {date}")
        indexed[key] = parse_float(row.get("close"))
    return indexed


def trading_dates(rows: list[dict[str, str]]) -> list[str]:
    return sorted({str(row.get("trade_date", "")).strip() for row in rows if row.get("trade_date")})


def rebalance_dates(dates: list[str], step: int = 20) -> list[str]:
    unique = sorted(dict.fromkeys(dates))
    if not unique:
        return []
    selected = unique[::step]
    if selected[-1] != unique[-1]:
        selected.append(unique[-1])
    return selected


def equal_weights(codes: list[str]) -> dict[str, float]:
    if not codes:
        return {}
    weight = 1.0 / len(codes)
    return {code: weight for code in sorted(codes)}


def drifted_weights(previous_weights: dict[str, float], returns: dict[str, float]) -> dict[str, float]:
    gross = {
        code: weight * (1.0 + returns.get(code, 0.0))
        for code, weight in previous_weights.items()
    }
    total = sum(gross.values())
    if total <= 0:
        return {}
    return {code: value / total for code, value in gross.items()}


def turnover_from_drift(target: dict[str, float], drifted: dict[str, float]) -> float:
    codes = set(target) | set(drifted)
    return 0.5 * sum(abs(target.get(code, 0.0) - drifted.get(code, 0.0)) for code in codes)


def period_row(
    universe: list[str],
    prices: dict[tuple[str, str], float | None],
    universe_name: str,
    transaction_cost: float,
    rebalance_date: str,
    next_rebalance_date: str,
    previous_weights: dict[str, float],
    *,
    min_coverage_ratio: float = MIN_COVERAGE_RATIO,
) -> tuple[dict[str, object], dict[str, float], dict[str, object]]:
    returns: dict[str, float] = {}
    dropped: list[str] = []
    for code in universe:
        start = prices.get((code, rebalance_date))
        end = prices.get((code, next_rebalance_date))
        if start is None or end is None:
            dropped.append(code)
            continue
        returns[code] = end / start - 1.0

    target = equal_weights(list(returns))
    universe_count = len(universe)
    available_count = len(target)
    coverage_ratio = available_count / universe_count if universe_count else 0.0
    coverage_pass = coverage_ratio >= min_coverage_ratio
    gross_return = sum(target[code] * returns[code] for code in target) if target else 0.0

    if previous_weights:
        drifted = drifted_weights(previous_weights, returns)
        turnover = turnover_from_drift(target, drifted)
    else:
        turnover = 1.0 if target else 0.0
    cost_drag = turnover * transaction_cost
    net_return = gross_return - cost_drag

    row = {
        "universe_name": universe_name,
        "transaction_cost": transaction_cost,
        "rebalance_date": rebalance_date,
        "next_rebalance_date": next_rebalance_date,
        "universe_count": universe_count,
        "available_count": available_count,
        "coverage_ratio": coverage_ratio,
        "coverage_pass": str(coverage_pass).lower(),
        "gross_return": gross_return,
        "turnover": turnover,
        "cost_drag": cost_drag,
        "net_return": net_return,
        "nav": "",
        "smoke_only": SMOKE_ONLY,
        "performance_conclusion_allowed": PERFORMANCE_CONCLUSION_ALLOWED,
    }
    qa = {
        "universe_name": universe_name,
        "transaction_cost": transaction_cost,
        "rebalance_date": rebalance_date,
        "next_rebalance_date": next_rebalance_date,
        "universe_count": universe_count,
        "available_count": available_count,
        "missing_close_count": len(dropped),
        "dropped_codes": ";".join(dropped),
        "coverage_ratio": coverage_ratio,
        "coverage_pass": str(coverage_pass).lower(),
        "qa_note": "coverage below threshold; diagnostic row only" if not coverage_pass else "ok",
        "smoke_only": SMOKE_ONLY,
        "performance_conclusion_allowed": PERFORMANCE_CONCLUSION_ALLOWED,
    }
    return row, target, qa


def run_scenario(
    universe: list[str],
    price_index: dict[tuple[str, str], float | None],
    dates: list[str],
    universe_name: str,
    transaction_cost: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []
    turnover_rows: list[dict[str, object]] = []
    previous_weights: dict[str, float] = {}
    nav = 1.0
    for rebalance_date, next_date in zip(dates, dates[1:], strict=False):
        row, target, qa = period_row(
            universe,
            price_index,
            universe_name,
            transaction_cost,
            rebalance_date,
            next_date,
            previous_weights,
        )
        nav *= 1.0 + float(row["net_return"])
        row["nav"] = nav
        rows.append(row)
        qa_rows.append(qa)
        turnover_rows.append(
            {
                "universe_name": universe_name,
                "transaction_cost": transaction_cost,
                "rebalance_date": rebalance_date,
                "next_rebalance_date": next_date,
                "turnover": row["turnover"],
                "cost_drag": row["cost_drag"],
                "previous_count": len(previous_weights),
                "target_count": len(target),
                "smoke_only": SMOKE_ONLY,
                "performance_conclusion_allowed": PERFORMANCE_CONCLUSION_ALLOWED,
            }
        )
        previous_weights = target
    return rows, turnover_rows, qa_rows


def summary_rows(nav_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_scenario: dict[tuple[str, float], list[dict[str, object]]] = {}
    for row in nav_rows:
        by_scenario.setdefault((str(row["universe_name"]), float(row["transaction_cost"])), []).append(row)
    rows: list[dict[str, object]] = []
    for (universe_name, transaction_cost), group in sorted(by_scenario.items()):
        rows.append(
            {
                "universe_name": universe_name,
                "transaction_cost": transaction_cost,
                "rebalance_date": group[0]["rebalance_date"],
                "next_rebalance_date": group[-1]["next_rebalance_date"],
                "universe_count": group[-1]["universe_count"],
                "available_count": group[-1]["available_count"],
                "coverage_ratio": min(float(row["coverage_ratio"]) for row in group),
                "coverage_pass": str(all(row["coverage_pass"] == "true" for row in group)).lower(),
                "gross_return": "",
                "turnover": sum(float(row["turnover"]) for row in group),
                "cost_drag": sum(float(row["cost_drag"]) for row in group),
                "net_return": float(group[-1]["nav"]) - 1.0,
                "nav": group[-1]["nav"],
                "smoke_only": SMOKE_ONLY,
                "performance_conclusion_allowed": PERFORMANCE_CONCLUSION_ALLOWED,
            }
        )
    return rows


def render_report(nav_rows: list[dict[str, object]], qa_rows: list[dict[str, object]], caveats: str) -> str:
    low_coverage = [row for row in qa_rows if row["coverage_pass"] == "false"]
    final = summary_rows(nav_rows)
    lines = [
        "# Stock Pool Smoke Baseline v1.2",
        "",
        "- smoke_only=true",
        "- performance_conclusion_allowed=false",
        "- baseline_type=current_universe_historical_performance",
        "- not point-in-time strategy backtest",
        "- no investment conclusion",
        "- return_source=close_to_close_unadjusted_or_unverified",
        "- rebalance_frequency=20_trading_days",
        "",
        "## Scenario Summary",
    ]
    for row in final:
        lines.append(
            f"- {row['universe_name']} cost={row['transaction_cost']}: "
            f"nav={row['nav']}; min_coverage={row['coverage_ratio']}; "
            "formal_performance_conclusion=forbidden"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "- Current universe is a 2026 v1.2 stock pool, so historical results have future-looking universe bias.",
            "- Price data is not verified qfq adjusted close.",
            "- Missing open/volume/pre_close, historical ST, suspension, and limit-up/down fields.",
            "- No verified benchmark, so no excess return conclusion.",
            "- Low-coverage periods are diagnostics only.",
            "- 300378 high/low/date coverage issue remains from readiness report; close-to-close smoke can continue with caveat.",
            "",
            "## Readiness Metadata",
            caveats.strip()[:2000],
            "",
            "## Coverage Diagnostics",
            f"- low_coverage_periods={len(low_coverage)}",
            "",
            "## Next Minimal Data Fetch Plan",
            "- Fetch only the 56 active/research universe stocks, not all A-shares.",
            "- Fetch qfq OHLC, volume, pre_close.",
            "- Repair 300378 high/low/date coverage.",
            "- Fetch benchmarks: 沪深300 + 中证1000; optionally 创业板指.",
            "- Record failed symbols to CSV; no silent skips.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    price_rows = read_csv(PRICE_PANEL)
    price_index = index_prices(price_rows)
    dates = rebalance_dates(trading_dates(price_rows), step=20)
    caveats = READINESS.read_text(encoding="utf-8") if READINESS.exists() else ""
    all_nav: list[dict[str, object]] = []
    all_turnover: list[dict[str, object]] = []
    all_qa: list[dict[str, object]] = []
    for scenario in scenarios():
        universe = load_universe(scenario.universe_path)
        nav_rows, turnover_rows, qa_rows = run_scenario(
            universe,
            price_index,
            dates,
            scenario.universe_name,
            scenario.transaction_cost,
        )
        all_nav.extend(nav_rows)
        all_turnover.extend(turnover_rows)
        all_qa.extend(qa_rows)

    write_csv(OUT_NAV, all_nav, MAIN_FIELDS)
    write_csv(OUT_TURNOVER, all_turnover, TURNOVER_FIELDS)
    write_csv(OUT_QA, all_qa, QA_FIELDS)
    write_csv(OUT_SUMMARY, summary_rows(all_nav), MAIN_FIELDS)
    OUT_REPORT.write_text(render_report(all_nav, all_qa, caveats), encoding="utf-8")

    print(f"scenarios={len(scenarios())}")
    print(f"nav_rows={len(all_nav)}")
    print(f"qa_rows={len(all_qa)}")
    print(f"low_coverage={sum(1 for row in all_qa if row['coverage_pass'] == 'false')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
