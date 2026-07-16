"""Append-only prospective observations for the frozen LOWVOL20 v1.5.1 protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts import run_lowvol_locked_grid_prototype_v1_5 as legacy
    from scripts.run_adjusted_stock_pool_baseline_v1_2 import code6
    from scripts.run_lowvol_locked_grid_prototype_v1_5_1 import period_targets, sha256
    from scripts.test_lowvol20_hypothesis_v1_4 import assign_quantiles, market_calendar, window_statistics
except ImportError:
    import run_lowvol_locked_grid_prototype_v1_5 as legacy
    from run_adjusted_stock_pool_baseline_v1_2 import code6
    from run_lowvol_locked_grid_prototype_v1_5_1 import period_targets, sha256
    from test_lowvol20_hypothesis_v1_4 import assign_quantiles, market_calendar, window_statistics


VERSION = "v1.5.1"
FREEZE_DATE = "2026-07-11"
STEP = 20
STATUSES = {"WAITING_FOR_COMPLETE_PERIOD", "PENDING", "CALCULATED", "APPENDED"}
LEDGER_COLUMNS = [
    "period_id", "status", "status_timestamp", "freeze_date", "strategy_version",
    "signal_date", "rebalance_date", "evaluation_end_date", "data_cutoff",
    "snapshot_hash", "result_hash", "approval_status", "input_price_hash",
    "input_benchmark_hash", "frozen_universe_hash", "qa_status",
    "formal_performance_conclusion_allowed", "execution_sim_ready",
    "no_investment_conclusion",
]
PROTECTED = (
    "scripts/run_lowvol_locked_grid_prototype_v1_5.py",
    "scripts/run_lowvol_locked_grid_prototype_v1_5_1.py",
    "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
    "reports/lowvol_locked_grid_prototype_nav_v1_5_1.csv",
    "reports/lowvol_locked_grid_prototype_summary_v1_5_1.csv",
    "reports/lowvol_locked_grid_prototype_qa_v1_5_1.csv",
    "reports/lowvol_locked_grid_prototype_v1_5_1.md",
    "reports/lowvol20_prospective_protocol_v1_5.md",
    "reports/lowvol20_prospective_periods_v1_5.csv",
    "data/processed/research_universe_lowvol_freeze_20260711.csv",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def protected_hashes(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in PROTECTED}


def output_root(root: Path) -> Path:
    return (root / "reports/prospective/lowvol_v1_5_1").resolve()


def resolve_approved_refresh(root: Path, refresh_run_id: str) -> tuple[Path, Path, str]:
    """Resolve only the latest approved immutable refresh inputs."""
    if not refresh_run_id:
        raise ValueError("--refresh-run-id is required")
    ledger_path = output_root(root) / "approved_refreshes.csv"
    if not ledger_path.exists():
        raise ValueError("No approved prospective refresh exists")
    ledger = pd.read_csv(ledger_path, dtype=str, keep_default_na=False)
    required = {
        "refresh_run_id", "cutoff", "price_panel_path", "benchmark_panel_path",
        "price_panel_sha256", "benchmark_panel_sha256", "qa_sha256", "publication_status",
    }
    if not required.issubset(ledger.columns) or ledger["refresh_run_id"].duplicated().any():
        raise ValueError("Invalid approved refresh ledger")
    if ledger.empty or ledger.iloc[-1]["refresh_run_id"] != refresh_run_id:
        raise ValueError("Refresh run is missing, unapproved, or stale")
    row = ledger.iloc[-1]
    if row["publication_status"] != "approved":
        raise ValueError("Refresh run is not approved")
    run_path = output_root(root) / "refresh_runs" / refresh_run_id
    price = (root / row["price_panel_path"]).resolve()
    benchmark = (root / row["benchmark_panel_path"]).resolve()
    if run_path.resolve() not in price.parents or run_path.resolve() not in benchmark.parents:
        raise ValueError("Approved panels are outside their immutable run directory")
    qa_path = run_path / "refresh_qa.csv"
    if sha256(price) != row["price_panel_sha256"] or sha256(benchmark) != row["benchmark_panel_sha256"]:
        raise ValueError("Approved refresh panel hash mismatch")
    if sha256(qa_path) != row["qa_sha256"]:
        raise ValueError("Approved refresh QA hash mismatch")
    qa = pd.read_csv(qa_path, dtype=str, keep_default_na=False)
    passed = len(qa) == 1 and qa.iloc[0].get("critical_qa_pass", "").lower() == "true"
    allowed = len(qa) == 1 and qa.iloc[0].get("observe_allowed", "").lower() == "true"
    if not passed or not allowed:
        raise ValueError("Approved refresh QA does not allow prospective use")
    if qa.iloc[0].get("price_panel_sha256") != row["price_panel_sha256"] or qa.iloc[0].get("benchmark_panel_sha256") != row["benchmark_panel_sha256"]:
        raise ValueError("Approved ledger and QA provenance disagree")
    return price, benchmark, row["cutoff"]


def ensure_output_path(root: Path, path: Path) -> Path:
    base, candidate = output_root(root), path.resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError(f"Prospective output escapes its directory: {candidate}")
    return candidate


def read_ledger(root: Path) -> pd.DataFrame:
    path = output_root(root) / "prospective_periods.csv"
    if not path.exists():
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.columns.tolist() != LEDGER_COLUMNS:
        raise ValueError("Prospective ledger schema mismatch")
    if frame.duplicated(["period_id", "status"]).any():
        raise ValueError("Duplicate prospective period/status")
    if not set(frame["status"]).issubset(STATUSES):
        raise ValueError("Unknown prospective status")
    return frame


def append_ledger(root: Path, row: dict[str, object]) -> None:
    if row["status"] not in STATUSES:
        raise ValueError(f"Unknown status: {row['status']}")
    ledger = read_ledger(root)
    duplicate = ledger["period_id"].eq(str(row["period_id"])) & ledger["status"].eq(str(row["status"]))
    if duplicate.any():
        raise ValueError(f"Duplicate prospective transition: {row['period_id']} {row['status']}")
    path = ensure_output_path(root, output_root(root) / "prospective_periods.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {column: row.get(column, "") for column in LEDGER_COLUMNS}
    pd.DataFrame([values], columns=LEDGER_COLUMNS).to_csv(
        path, mode="a", header=not path.exists(), index=False
    )
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())
    read_ledger(root)


def base_row(root: Path, price_path: Path, benchmark_path: Path, **values: object) -> dict[str, object]:
    row = {
        "status_timestamp": now(), "freeze_date": FREEZE_DATE, "strategy_version": VERSION,
        "approval_status": "not_requested", "input_price_hash": sha256(price_path),
        "input_benchmark_hash": sha256(benchmark_path),
        "frozen_universe_hash": sha256(root / "data/processed/research_universe_lowvol_freeze_20260711.csv"),
        "qa_status": "pass", "formal_performance_conclusion_allowed": False,
        "execution_sim_ready": False, "no_investment_conclusion": True,
    }
    row.update(values)
    return row


def load_schedule(root: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    path = root / "reports/adjusted_stock_pool_baseline_periods_v1_5.csv"
    frame = pd.read_csv(path, dtype=str)
    cost = pd.to_numeric(frame["transaction_cost"], errors="raise")
    selected = frame.loc[
        frame["universe_name"].eq("research_universe_v1_2") & np.isclose(cost, 0.0),
        ["rebalance_date", "next_rebalance_date", "period_trading_days", "period_type"],
    ].drop_duplicates().sort_values("rebalance_date").reset_index(drop=True)
    selected[["rebalance_date", "next_rebalance_date"]] = selected[["rebalance_date", "next_rebalance_date"]].apply(
        pd.to_datetime, errors="raise"
    )
    if selected.empty or selected.duplicated(["rebalance_date", "next_rebalance_date"]).any():
        raise ValueError("Invalid frozen schedule")
    if not selected["next_rebalance_date"].iloc[:-1].reset_index(drop=True).equals(
        selected["rebalance_date"].iloc[1:].reset_index(drop=True)
    ):
        raise ValueError("Frozen schedule is not contiguous")
    partial = selected.loc[selected["period_type"].eq("partial")]
    if len(partial) != 1 or partial.index[0] != selected.index[-1]:
        raise ValueError("Expected one terminal partial frozen-schedule row")
    return selected, pd.Timestamp(partial.iloc[0]["rebalance_date"])


def next_period(root: Path, benchmark: pd.DataFrame) -> dict[str, object]:
    schedule, anchor = load_schedule(root)
    calendar = market_calendar(benchmark)
    positions = {date: index for index, date in enumerate(calendar)}
    if anchor not in positions:
        raise ValueError("Frozen schedule anchor is absent from 000300 calendar")
    expected_old = schedule.iloc[:-1]
    for row in expected_old.itertuples(index=False):
        if row.rebalance_date not in positions or row.next_rebalance_date not in positions:
            raise ValueError("Stored schedule endpoint is absent from 000300 calendar")
        if positions[row.next_rebalance_date] - positions[row.rebalance_date] != int(row.period_trading_days):
            raise ValueError("Stored schedule changed under authoritative calendar")
    ledger = read_ledger(root)
    appended = ledger.loc[ledger["status"].eq("APPENDED")].copy()
    appended_count = appended["period_id"].nunique()
    rebalance_position = positions[anchor] + STEP * (appended_count + 1)
    if rebalance_position >= len(calendar):
        return {"complete": False, "anchor": anchor, "calendar": calendar}
    rebalance = calendar[rebalance_position]
    expected_prior = [calendar[positions[anchor] + STEP * index] for index in range(1, appended_count + 1)]
    actual_prior = sorted(pd.to_datetime(appended["rebalance_date"], errors="raise").drop_duplicates().tolist())
    if actual_prior != expected_prior:
        raise ValueError("Appended prospective periods do not follow the frozen schedule")
    if rebalance <= pd.Timestamp(FREEZE_DATE):
        raise ValueError("Next scheduled rebalance is not prospective")
    end_position = rebalance_position + STEP
    end = calendar[end_position] if end_position < len(calendar) else pd.NaT
    return {
        "complete": pd.notna(end), "anchor": anchor, "calendar": calendar,
        "signal_date": calendar[rebalance_position - 1], "rebalance_date": rebalance,
        "evaluation_end_date": end,
    }


def load_inputs(
    root: Path, price_path: Path, benchmark_path: Path, data_cutoff: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    prices = pd.read_csv(price_path, dtype={"stock_code": str})
    benchmark = pd.read_csv(benchmark_path, dtype={"benchmark_code": str})
    universe = pd.read_csv(root / "data/processed/research_universe_lowvol_freeze_20260711.csv", dtype={"code": str})
    universe_codes = sorted(universe["code"].map(code6).unique())
    if len(universe_codes) != 56:
        raise ValueError("Frozen prospective universe must contain 56 unique codes")
    prices["stock_code"] = prices["stock_code"].map(code6)
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="raise")
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    cutoff = pd.Timestamp(data_cutoff)
    prices = prices.loc[prices["trade_date"].le(cutoff)].copy()
    benchmark = benchmark.loc[benchmark["trade_date"].le(cutoff)].copy()
    if prices.empty or benchmark.empty:
        raise ValueError("Data cutoff leaves no usable input rows")
    if prices.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("Duplicate stock/date")
    flag = prices["adjusted_flag"].astype(str).str.strip().str.lower().map({"true": True, "1": True, "false": False, "0": False})
    if flag.isna().any():
        raise ValueError("Invalid adjusted_flag")
    qfq = pd.to_numeric(prices["qfq_close"], errors="coerce")
    adjusted = pd.to_numeric(prices["adjusted_close"], errors="coerce")
    conflict = flag & ((qfq <= 0) | (adjusted <= 0) | ~np.isclose(qfq, adjusted, atol=1e-10, rtol=1e-8, equal_nan=False))
    if conflict.any():
        raise ValueError("Adjusted/QFQ price conflict")
    prices = prices.loc[flag & (qfq > 0), ["stock_code", "trade_date"]].assign(adjusted_close=adjusted[flag & (qfq > 0)])
    return prices, benchmark, universe_codes


def period_id(rebalance_date: pd.Timestamp, end_date: object = None) -> str:
    # The future 20th market date is unknown when the signal snapshot is frozen.
    return f"LOWVOL20_V1_5_1_{pd.Timestamp(rebalance_date).strftime('%Y%m%d')}"


def snapshot_hash(path: Path, include_result: bool = False) -> str:
    names = ["universe.csv", "factor.csv", "targets.csv", "manifest.csv", "qa.csv"]
    if include_result:
        names.append("result.csv")
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((path / name).read_bytes())
    return digest.hexdigest()


def build_snapshot(
    root: Path, prices: pd.DataFrame, universe_codes: list[str], period: dict[str, object],
    price_path: Path, benchmark_path: Path, data_cutoff: str,
) -> tuple[str, Path]:
    rebalance, signal = pd.Timestamp(period["rebalance_date"]), pd.Timestamp(period["signal_date"])
    pid = period_id(rebalance, period.get("evaluation_end_date"))
    path = ensure_output_path(root, output_root(root) / "snapshots" / pid)
    if path.exists():
        raise ValueError(f"Snapshot already exists: {pid}")
    lookup = prices.set_index(["stock_code", "trade_date"])["adjusted_close"]
    rows = []
    for stock_code in universe_codes:
        series = lookup.loc[stock_code] if stock_code in lookup.index.get_level_values(0) else pd.Series(dtype=float)
        stats = window_statistics(series, period["calendar"], signal, STEP)
        rows.append({
            "stock_code": stock_code, "signal_date": signal.strftime("%Y-%m-%d"),
            "rebalance_date": rebalance.strftime("%Y-%m-%d"),
            "evaluation_end_date": "" if pd.isna(period.get("evaluation_end_date")) else pd.Timestamp(period["evaluation_end_date"]).strftime("%Y-%m-%d"),
            "baseline_eligible": (stock_code, rebalance) in lookup.index,
            "forward_return": math.nan, "forward_risk_available": False,
            "primary_reliable_signal": stats["primary_reliable_signal"],
            "lowvol20": stats["lowvol"], **stats,
        })
    factor, diagnostics = assign_quantiles(pd.DataFrame(rows), "lowvol20", reliable=True)
    targets = period_targets(factor)
    universe = pd.DataFrame({"stock_code": universe_codes})
    universe["frozen_protocol_member"] = True
    universe["baseline_eligible"] = universe["stock_code"].map(factor.set_index("stock_code")["baseline_eligible"])
    target_rows = [
        {"portfolio": portfolio, "stock_code": code, "target_weight": item["target"][code]}
        for portfolio, item in targets.items() for code in item["codes"]
    ]
    qa = pd.DataFrame([
        {"check_id": "signal_precedes_rebalance", "pass": signal < rebalance, "critical": True},
        {"check_id": "frozen_universe_count", "pass": len(universe_codes) == 56, "critical": True},
        {"check_id": "quantile_label_blind", "pass": not factor["label_available"].any(), "critical": True},
        {"check_id": "target_weights", "pass": all(np.isclose(sum(item["target"].values()), 1.0) for item in targets.values() if item["codes"]), "critical": True},
        {"check_id": "signal_unique_values", "pass": diagnostics["signal_unique_value_count"] >= 5, "critical": True},
    ])
    if not qa.loc[qa["critical"], "pass"].all():
        raise ValueError("Signal snapshot QA failed")
    path.mkdir(parents=True)
    universe.to_csv(path / "universe.csv", index=False)
    factor.to_csv(path / "factor.csv", index=False)
    pd.DataFrame(target_rows).to_csv(path / "targets.csv", index=False)
    pd.DataFrame([{
        "period_id": pid, "strategy_version": VERSION, "freeze_date": FREEZE_DATE,
        "generated_at": now(), "data_cutoff": data_cutoff,
        "price_path": str(price_path), "price_sha256": sha256(price_path),
        "benchmark_path": str(benchmark_path), "benchmark_sha256": sha256(benchmark_path),
        "universe_sha256": sha256(root / "data/processed/research_universe_lowvol_freeze_20260711.csv"),
    }]).to_csv(path / "manifest.csv", index=False)
    qa.to_csv(path / "qa.csv", index=False)
    return pid, path


def read_targets(path: Path) -> dict[str, dict[str, float]]:
    frame = pd.read_csv(path / "targets.csv", dtype={"stock_code": str})
    result = {}
    for portfolio, group in frame.groupby("portfolio"):
        result[portfolio] = dict(zip(group["stock_code"].map(code6), pd.to_numeric(group["target_weight"], errors="raise")))
    return result


def prior_observations(root: Path, portfolio: str) -> list[dict[str, object]]:
    ledger = read_ledger(root)
    appended = ledger.loc[ledger["status"].eq("APPENDED")].sort_values("rebalance_date")
    observations = []
    for row in appended.itertuples(index=False):
        result = pd.read_csv(output_root(root) / "snapshots" / row.period_id / "result.csv")
        selected = result.loc[
            result["portfolio"].eq(portfolio) & np.isclose(result["transaction_cost"], 0.0)
        ]
        if len(selected) != 1:
            raise ValueError(f"Invalid prior prospective result: {row.period_id} {portfolio}")
        item = selected.iloc[0]
        observations.append({
            "period_index": len(observations), "rebalance_date": item["rebalance_date"],
            "next_rebalance_date": item["next_rebalance_date"], "portfolio": portfolio,
            "target": json.loads(item["target_weights"]),
            "returns": json.loads(item["stock_returns"]),
            "valid": item["period_status"] != "end_price_missing",
            "selected_codes": item["selected_codes"],
            "target_weights": item["target_weights"], "stock_returns": item["stock_returns"],
            "end_price_missing_codes": item.get("end_price_missing_codes", ""),
        })
    return observations


def evaluate_snapshot(
    root: Path, path: Path, prices: pd.DataFrame, benchmark: pd.DataFrame,
    evaluation_end_date: object | None = None,
) -> pd.DataFrame:
    manifest = pd.read_csv(path / "manifest.csv", dtype=str).iloc[0]
    factor = pd.read_csv(path / "factor.csv", dtype={"stock_code": str})
    start = pd.Timestamp(factor.iloc[0]["rebalance_date"])
    end_text = str(factor.iloc[0]["evaluation_end_date"])
    if evaluation_end_date is not None:
        end_text = str(pd.Timestamp(evaluation_end_date).date())
    if not end_text or end_text.lower() == "nan":
        raise ValueError("Snapshot has no complete evaluation endpoint")
    end = pd.Timestamp(end_text)
    lookup = prices.set_index(["stock_code", "trade_date"])["adjusted_close"]
    observations = {}
    for portfolio, target in read_targets(path).items():
        missing = [code for code in target if (code, end) not in lookup.index]
        returns = {
            code: float(lookup[(code, end)] / lookup[(code, start)] - 1)
            for code in target if (code, start) in lookup.index and (code, end) in lookup.index
        }
        current = {
            "period_index": 0, "rebalance_date": start.strftime("%Y-%m-%d"),
            "next_rebalance_date": end.strftime("%Y-%m-%d"), "portfolio": portfolio,
            "target": target, "returns": returns, "valid": bool(target) and not missing,
            "selected_codes": ";".join(sorted(target)), "end_price_missing_codes": ";".join(sorted(missing)),
            "target_weights": json.dumps(target, sort_keys=True),
            "stock_returns": json.dumps(returns, sort_keys=True),
        }
        previous = prior_observations(root, portfolio)
        current["period_index"] = len(previous)
        observations[portfolio] = previous + [current]
    rows = []
    for portfolio, items in observations.items():
        for cost in legacy.COSTS:
            rows.append(legacy.simulate(items, cost).tail(1))
    result = pd.concat(rows, ignore_index=True)
    result["period_id"] = manifest["period_id"]
    benchmark["benchmark_code"] = benchmark["benchmark_code"].map(code6)
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    if benchmark.duplicated(["benchmark_code", "trade_date"]).any():
        raise ValueError("Duplicate benchmark/date")
    blookup = benchmark.set_index(["benchmark_code", "trade_date"])["close"].astype(float)
    for code in ("000300", "000852", "399006"):
        if (code, start) not in blookup.index or (code, end) not in blookup.index:
            raise ValueError(f"Missing benchmark endpoint: {code}")
        result[f"benchmark_return_{code}"] = blookup[(code, end)] / blookup[(code, start)] - 1
    return result


def record_waiting(root: Path, price_path: Path, benchmark_path: Path, data_cutoff: str) -> None:
    ledger = read_ledger(root)
    pid = "LOWVOL20_V1_5_1_NEXT_SCHEDULED_PERIOD"
    if ((ledger["period_id"] == pid) & (ledger["status"] == "WAITING_FOR_COMPLETE_PERIOD")).any():
        return
    append_ledger(root, base_row(
        root, price_path, benchmark_path, period_id=pid, status="WAITING_FOR_COMPLETE_PERIOD",
        data_cutoff=data_cutoff, approval_status="not_applicable", qa_status="pass",
    ))


def observe(root: Path, price_path: Path, benchmark_path: Path, data_cutoff: str) -> int:
    before = protected_hashes(root)
    prices, benchmark, universe = load_inputs(root, price_path, benchmark_path, data_cutoff)
    period = next_period(root, benchmark)
    if "rebalance_date" not in period:
        record_waiting(root, price_path, benchmark_path, data_cutoff)
        print("complete_periods=0 status=WAITING_FOR_COMPLETE_PERIOD performance_results=none")
    else:
        pid = period_id(period["rebalance_date"], period.get("evaluation_end_date"))
        ledger = read_ledger(root)
        if not ((ledger["period_id"] == pid) & (ledger["status"] == "PENDING")).any():
            pid, path = build_snapshot(root, prices, universe, period, price_path, benchmark_path, data_cutoff)
            append_ledger(root, base_row(
                root, price_path, benchmark_path, period_id=pid, status="PENDING",
                signal_date=pd.Timestamp(period["signal_date"]).strftime("%Y-%m-%d"),
                rebalance_date=pd.Timestamp(period["rebalance_date"]).strftime("%Y-%m-%d"),
                evaluation_end_date="" if pd.isna(period["evaluation_end_date"]) else pd.Timestamp(period["evaluation_end_date"]).strftime("%Y-%m-%d"),
                data_cutoff=data_cutoff, snapshot_hash=snapshot_hash(path),
            ))
        print(f"period_id={pid} status=PENDING complete_periods={int(period['complete'])}")
    if before != protected_hashes(root):
        raise ValueError("Protected historical artifact changed")
    return 0


def evaluate(root: Path, price_path: Path, benchmark_path: Path, data_cutoff: str) -> int:
    before = protected_hashes(root)
    prices, benchmark, _ = load_inputs(root, price_path, benchmark_path, data_cutoff)
    ledger = read_ledger(root)
    pending = ledger.loc[ledger["status"].eq("PENDING")]
    if pending.empty:
        period = next_period(root, benchmark)
        if "rebalance_date" not in period or not period["complete"]:
            record_waiting(root, price_path, benchmark_path, data_cutoff)
            if before != protected_hashes(root):
                raise ValueError("Protected historical artifact changed")
            print("complete_periods=0 status=WAITING_FOR_COMPLETE_PERIOD performance_results=none")
            return 0
        raise ValueError("Complete prospective period has no frozen signal snapshot")
    row = pending.iloc[-1]
    pid = row["period_id"]
    period = next_period(root, benchmark)
    if (
        not period.get("complete")
        or pd.Timestamp(period["rebalance_date"]).strftime("%Y-%m-%d") != row["rebalance_date"]
        or pd.Timestamp(data_cutoff) < pd.Timestamp(period["evaluation_end_date"])
    ):
        record_waiting(root, price_path, benchmark_path, data_cutoff)
        if before != protected_hashes(root):
            raise ValueError("Protected historical artifact changed")
        print("complete_periods=0 status=WAITING_FOR_COMPLETE_PERIOD performance_results=none")
        return 0
    if ((ledger["period_id"] == pid) & (ledger["status"] == "CALCULATED")).any():
        raise ValueError(f"Period already calculated: {pid}")
    path = output_root(root) / "snapshots" / pid
    if snapshot_hash(path) != row["snapshot_hash"]:
        raise ValueError("Signal snapshot hash changed")
    evaluation_end = pd.Timestamp(period["evaluation_end_date"]).strftime("%Y-%m-%d")
    result = evaluate_snapshot(root, path, prices, benchmark, evaluation_end)
    result.to_csv(path / "result.csv", index=False)
    result_hash = sha256(path / "result.csv")
    append_ledger(root, base_row(
        root, price_path, benchmark_path, period_id=pid, status="CALCULATED",
        signal_date=row["signal_date"], rebalance_date=row["rebalance_date"],
        evaluation_end_date=evaluation_end, data_cutoff=data_cutoff,
        snapshot_hash=row["snapshot_hash"], result_hash=result_hash,
    ))
    if before != protected_hashes(root):
        raise ValueError("Protected historical artifact changed")
    print(f"period_id={pid} status=CALCULATED")
    return 0


def approve_append(root: Path, period_id_value: str, approve: bool) -> int:
    if not approve:
        raise ValueError("Explicit --approve is required")
    before = protected_hashes(root)
    ledger = read_ledger(root)
    calculated = ledger[(ledger["period_id"] == period_id_value) & (ledger["status"] == "CALCULATED")]
    if len(calculated) != 1:
        raise ValueError("Expected exactly one CALCULATED record")
    if ((ledger["period_id"] == period_id_value) & (ledger["status"] == "APPENDED")).any():
        raise ValueError("Prospective period is already appended")
    source = calculated.iloc[0].to_dict()
    path = output_root(root) / "snapshots" / period_id_value / "result.csv"
    if sha256(path) != source["result_hash"]:
        raise ValueError("Calculated result hash changed")
    source.update(status="APPENDED", status_timestamp=now(), approval_status="human_approved")
    append_ledger(root, source)
    if before != protected_hashes(root):
        raise ValueError("Protected historical artifact changed")
    print(f"period_id={period_id_value} status=APPENDED")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("observe", "evaluate", "append"))
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--refresh-run-id")
    parser.add_argument("--period-id")
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        if args.command == "append":
            if not args.period_id:
                raise ValueError("--period-id is required")
            return approve_append(root, args.period_id, args.approve)
        price_path, benchmark_path, cutoff = resolve_approved_refresh(root, args.refresh_run_id)
        if args.command == "observe":
            return observe(root, price_path, benchmark_path, cutoff)
        return evaluate(root, price_path, benchmark_path, cutoff)
    except Exception as exc:
        print(f"critical_error={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
