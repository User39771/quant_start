from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metric(path: Path, column: str, **filters: object) -> object:
    frame = pd.read_csv(path, dtype=str)
    for key, value in filters.items():
        wanted = str(value)
        if key == "benchmark_code":
            frame = frame[frame[key].str.zfill(6).eq(wanted.zfill(6))]
        elif key == "transaction_cost":
            frame = frame[pd.to_numeric(frame[key]).eq(float(value))]
        else:
            frame = frame[frame[key].eq(wanted)]
    return frame.iloc[0][column] if not frame.empty and column in frame else None


def run(root: Path) -> None:
    root, reports = Path(root), Path(root) / "reports"
    old_prices = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_2.csv", dtype={"stock_code": str})
    new_prices = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_5.csv", dtype={"stock_code": str})
    for frame in (old_prices, new_prices):
        frame["stock_code"] = frame["stock_code"].str.zfill(6)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")
    overlap = old_prices[["stock_code", "trade_date", "adjusted_close"]].merge(
        new_prices[["stock_code", "trade_date", "adjusted_close"]],
        on=["stock_code", "trade_date"], suffixes=("_old", "_new"), how="outer", indicator=True,
    )
    both = overlap[overlap["_merge"].eq("both")].copy()
    both["absolute_difference"] = (pd.to_numeric(both["adjusted_close_new"]) - pd.to_numeric(both["adjusted_close_old"])).abs()
    diff = pd.DataFrame([
        {"metric": "old_rows", "value": len(old_prices)},
        {"metric": "new_rows", "value": len(new_prices)},
        {"metric": "newly_added_rows", "value": int((overlap["_merge"] == "right_only").sum())},
        {"metric": "old_only_rows", "value": int((overlap["_merge"] == "left_only").sum())},
        {"metric": "overlap_rows", "value": len(both)},
        {"metric": "changed_overlap_rows_gt_1e_8", "value": int((both["absolute_difference"] > 1e-8).sum())},
        {"metric": "maximum_overlap_absolute_difference", "value": both["absolute_difference"].max()},
    ])
    diff.to_csv(reports / "qfq_refresh_diff_v1_5.csv", index=False)

    rows = []
    for version in ("v1_4", "v1_5"):
        lowvol = reports / f"factor_hypothesis_summary_lowvol20_{version}.csv"
        baseline_version = "v1_2" if version == "v1_4" else "v1_5"
        baseline = reports / f"adjusted_stock_pool_baseline_summary_{baseline_version}.csv"
        row = {"version": version}
        if baseline.exists():
            row.update({
                "baseline_cumulative_return": _metric(baseline, "cumulative_return", universe_name="research_universe_v1_2", transaction_cost=0.0, benchmark_code="000300"),
                "baseline_annualized_return": _metric(baseline, "annualized_return", universe_name="research_universe_v1_2", transaction_cost=0.0, benchmark_code="000300"),
                "baseline_volatility": _metric(baseline, "annualized_volatility", universe_name="research_universe_v1_2", transaction_cost=0.0, benchmark_code="000300"),
                "baseline_endpoint_drawdown": _metric(baseline, "period_endpoint_maximum_drawdown", universe_name="research_universe_v1_2", transaction_cost=0.0, benchmark_code="000300"),
            })
        if lowvol.exists():
            table = pd.read_csv(lowvol)
            verdict = table[table.get("metric", pd.Series(dtype=str)).eq("verdict")]
            row["lowvol_status"] = "ok" if not verdict.empty else "research_not_ready"
            row["lowvol_verdict"] = verdict.iloc[0]["value"] if not verdict.empty else "not_available"
        rows.append(row)
    pd.DataFrame(rows).to_csv(reports / "v1_4_vs_v1_5_revised_history_comparison.csv", index=False)
    (reports / "v1_4_vs_v1_5_revised_history_comparison.md").write_text(
        "# v1.4 vs v1.5 Revised History\n\nThe v1.5 full-history refresh changes historical availability and causes the frozen baseline to terminate early on an end-price gap. LOWVOL20 v1.5 is therefore research_not_ready. Rules and thresholds were not changed.\n\nformal_performance_conclusion_allowed=false\n",
        encoding="utf-8",
    )

    universe = pd.read_csv(root / "data/processed/research_universe_lowvol_freeze_20260711.csv", dtype=str)
    event_codes = universe[universe["theme"].fillna("").str.contains("商业航天")]["code"].str.zfill(6)
    benchmark = pd.read_csv(root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str})
    readiness = pd.DataFrame({"stock_code": event_codes, "event_date": "2026-07-10", "status": "blocked_waiting_for_event_window"})
    readiness.to_csv(reports / "commercial_space_event_readiness_v1_5.csv", index=False)
    latest = benchmark[benchmark["benchmark_code"].isin(["000852", "399006"])]["trade_date"].max()
    (reports / "commercial_space_event_readiness_v1_5.md").write_text(
        f"# Commercial Space Event Readiness v1.5\n\n- status: blocked_waiting_for_event_window\n- event_date: 2026-07-10\n- frozen_stock_count: {len(event_codes)}\n- benchmark_latest_date: {latest}\n- reason: the +5 market-day window has not occurred yet\n- event return and CAR were not calculated\n",
        encoding="utf-8",
    )

    before = pd.read_csv(reports / "v1_5_frozen_file_manifest_before.csv")
    differences = []
    for row in before.itertuples(index=False):
        path = root / row.path
        current = _hash(path) if path.exists() else "missing"
        expected = str(getattr(row, "sha256")).lower()
        if current.lower() != expected:
            differences.append({"path": row.path, "expected": expected, "actual": current})
    pd.DataFrame(differences, columns=["path", "expected", "actual"]).to_csv(reports / "v1_5_frozen_hash_differences.csv", index=False)


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
