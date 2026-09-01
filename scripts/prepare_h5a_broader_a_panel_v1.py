# ruff: noqa: E501
"""Prepare a local-only broader-A signal-time panel for H5A readiness.

This runner deliberately does not calculate any future return or research outcome.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path("data/cache/price")
DEFAULT_QFQ_DIR = Path("data/cache/h5a_broader_a_qfq_v1")
PUBLIC_DAILY_DIR = Path("data/cache/public/clean/akshare/daily_price")
OUTPUT_DATA = Path("data/processed")
OUTPUT_REPORT = Path("reports/hypothesis_5a_broader_a")
IDENTITY = {
    "sample_role": "historical_seen",
    "universe_point_in_time": "false",
    "current_universe_historical_backfill": "true",
    "descriptive_research_only": "true",
    "alpha_claim_allowed": "false",
    "oos_claim_allowed": "false",
}


def code6(value: object) -> str:
    text = str(value).strip().replace(".0", "")
    return text.zfill(6) if text.isascii() and text.isdigit() and len(text) <= 6 else ""


def ordinary_a_share(code: str, exchange: str) -> bool:
    """Conservative current-code screen; uncertain codes are excluded, not guessed."""
    prefixes = {
        "SH": ("600", "601", "603", "605", "688"),
        "SZ": ("000", "001", "002", "003", "300", "301"),
        "BJ": ("4", "8", "92"),
    }
    return len(code) == 6 and exchange in prefixes and code.startswith(prefixes[exchange])


def _finite_positive(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.Series(np.isfinite(numeric) & numeric.gt(0), index=values.index)


def _finite_nonnegative(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.Series(np.isfinite(numeric) & numeric.ge(0), index=values.index)


def stable_groups(frame: pd.DataFrame, column: str, groups: int) -> pd.Series:
    """Deterministic equal-count groups with stock code as the fixed tie breaker."""
    ordered = frame.sort_values([column, "stock_code"], kind="stable")
    labels = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    for number, indices in enumerate(np.array_split(ordered.index.to_numpy(), groups), 1):
        labels.loc[indices] = number
    return labels


def endpoint_date(
    calendar: pd.DatetimeIndex, rebalance: pd.Timestamp, horizon: int
) -> pd.Timestamp:
    location = calendar.get_indexer([rebalance])[0]
    if location < 0 or location + horizon >= len(calendar):
        return pd.NaT
    return calendar[location + horizon]


def _profile_csv(path: Path, source: str, adjustment: str) -> tuple[dict, pd.DataFrame | None]:
    row = {
        "stock_code": "",
        "file_path": path.as_posix(),
        "source": source,
        "adjustment_type": adjustment,
        "has_close": False,
        "has_qfq_close": False,
        "has_amount": False,
        "row_count": 0,
        "date_min": "",
        "date_max": "",
        "readable": False,
        "notes": "",
    }
    try:
        frame = pd.read_csv(path, low_memory=False)
        code_column = next((x for x in ("stock_code", "code", "symbol") if x in frame), None)
        fallback_code = path.stem if path.stem.isdigit() else path.stem.split("_")[2]
        row["stock_code"] = code6(
            frame[code_column].iloc[0] if code_column and len(frame) else fallback_code
        )
        date_column = next((x for x in ("trade_date", "date") if x in frame), None)
        dates = (
            pd.to_datetime(frame[date_column], errors="coerce")
            if date_column
            else pd.Series(dtype="datetime64[ns]")
        )
        row.update(
            {
                "has_close": "close" in frame,
                "has_qfq_close": "qfq_close" in frame,
                "has_amount": "amount" in frame,
                "row_count": len(frame),
                "date_min": dates.min(),
                "date_max": dates.max(),
                "readable": True,
                "notes": "raw close is not return-usable" if adjustment == "raw_unadjusted" else "",
            }
        )
        return row, frame
    except Exception as exc:  # every local file must remain in the inventory
        row["notes"] = f"read_error:{type(exc).__name__}:{exc}"
        return row, None


def load_calendar_and_signals(root: Path) -> tuple[pd.DatetimeIndex, pd.DataFrame]:
    calendar_frame = pd.read_csv(
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str}
    )
    calendar_frame["benchmark_code"] = calendar_frame["benchmark_code"].map(code6)
    calendar = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[calendar_frame["benchmark_code"].eq("000300"), "trade_date"],
            errors="raise",
        )
        .drop_duplicates()
        .sort_values()
    )
    columns = ["period_index", "signal_as_of_date", "rebalance_date", "next_rebalance_date"]
    mom = pd.read_csv(root / "data/processed/mom60_factor_panel_v1_3.csv", usecols=columns)
    signals = mom.drop_duplicates().sort_values("period_index").reset_index(drop=True)
    if len(signals) != 57 or signals["period_index"].nunique() != 57:
        raise ValueError(f"locked_signal_count={len(signals)} expected=57")
    for column in columns[1:]:
        signals[column] = pd.to_datetime(signals[column], errors="raise")
    if signals.duplicated("period_index").any():
        raise ValueError("duplicate_period_index")
    if not (
        (signals["signal_as_of_date"] < signals["rebalance_date"])
        & (signals["rebalance_date"] < signals["next_rebalance_date"])
    ).all():
        raise ValueError("invalid_locked_date_order")
    lowvol_path = root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv"
    if lowvol_path.exists():
        lowvol = pd.read_csv(lowvol_path, usecols=columns).drop_duplicates()
        for column in columns[1:]:
            lowvol[column] = pd.to_datetime(lowvol[column], errors="raise")
        check = signals.merge(
            lowvol, on="period_index", suffixes=("_mom", "_lowvol"), validate="one_to_one"
        )
        for column in columns[1:]:
            if not check[f"{column}_mom"].equals(check[f"{column}_lowvol"]):
                raise ValueError(f"locked_signal_conflict={column}")
    if (calendar.get_indexer(signals["signal_as_of_date"]) < 0).any() or (
        calendar.get_indexer(signals["rebalance_date"]) < 0
    ).any():
        raise ValueError("locked_date_absent_from_csi300_calendar")
    return calendar, signals


def run(root: Path, qfq_cache: Path = DEFAULT_QFQ_DIR) -> None:
    root = root.resolve()
    report_dir = root / OUTPUT_REPORT
    processed_dir = root / OUTPUT_DATA
    daily_dir = processed_dir / "h5a_broader_a_daily_v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)

    inventory_rows: list[dict] = []
    raw_profiles: dict[str, dict] = {}
    for path in sorted((root / RAW_DIR).glob("*.csv")):
        row, frame = _profile_csv(path, "local_all_a_price_cache", "raw_unadjusted")
        inventory_rows.append(row)
        code = row["stock_code"]
        if frame is None or not code:
            raw_profiles[code or path.stem] = {
                "path": path,
                "readable": False,
                "exchange": "",
                "amount_usable": False,
            }
            continue
        exchange = (
            str(frame["exchange"].iloc[0]).strip().upper()
            if "exchange" in frame and len(frame)
            else ""
        )
        amount_usable = "amount" in frame and bool(_finite_nonnegative(frame["amount"]).any())
        raw_profiles[code] = {
            "path": path,
            "readable": True,
            "exchange": exchange,
            "amount_usable": amount_usable,
            "amount_valid_rows": int(_finite_nonnegative(frame["amount"]).sum())
            if "amount" in frame
            else 0,
            "date_min": row["date_min"],
            "date_max": row["date_max"],
        }
    qfq_sources: dict[str, list[dict]] = {}
    for directory, source, priority in (
        (qfq_cache, "sina_broader_a_qfq_v1", 1),
    ):
        for path in sorted((root / directory).glob("*.csv")):
            row, frame = _profile_csv(path, source, "qfq")
            inventory_rows.append(row)
            if frame is None or not row["stock_code"] or "qfq_close" not in frame:
                continue
            valid = _finite_positive(frame["qfq_close"])
            if valid.any():
                qfq_sources.setdefault(row["stock_code"], []).append(
                    {
                        "path": path,
                        "source": source,
                        "priority": priority,
                        "valid_rows": int(valid.sum()),
                        "date_min": row["date_min"],
                        "date_max": row["date_max"],
                    }
                )
    for path in sorted((root / PUBLIC_DAILY_DIR).glob("*.csv")):
        row, _ = _profile_csv(path, "public_clean_akshare_daily_cache", "raw_unadjusted")
        inventory_rows.append(row)
    inventory = pd.DataFrame(inventory_rows)
    inventory["file_path"] = inventory["file_path"].map(
        lambda x: Path(x).resolve().relative_to(root).as_posix()
    )
    inventory.to_csv(report_dir / "local_data_inventory.csv", index=False, encoding="utf-8-sig")

    universe_rows = []
    for code, profile in sorted(raw_profiles.items()):
        legal = bool(profile.get("readable")) and ordinary_a_share(
            code, profile.get("exchange", "")
        )
        universe_rows.append(
            {
                "stock_code": code6(code),
                "name_if_available": "",
                "exchange_if_available": profile.get("exchange", ""),
                "universe_source": "data/cache/price current local cache",
                "universe_status": "INCLUDED" if legal else "UNKNOWN_EXCLUDED",
                "notes": "current-universe historical backfill; not point-in-time"
                if legal
                else "ordinary A-share identity not reliably established",
            }
        )
    universe = pd.DataFrame(universe_rows).sort_values(["universe_status", "stock_code"])
    universe.to_csv(
        processed_dir / "h5a_broader_a_universe_v1.csv", index=False, encoding="utf-8-sig"
    )
    included = sorted(universe.loc[universe["universe_status"].eq("INCLUDED"), "stock_code"])

    selected: dict[str, dict] = {}
    resolution_rows = []
    for code in included:
        candidates = sorted(
            qfq_sources.get(code, []), key=lambda x: (x["priority"], -x["valid_rows"])
        )
        chosen = candidates[0] if candidates else None
        if chosen:
            selected[code] = chosen
        raw = raw_profiles[code]
        resolution_rows.append(
            {
                "stock_code": code,
                "qfq_candidate_count": len(candidates),
                "canonical_price_source": chosen["source"] if chosen else "",
                "canonical_price_path": chosen["path"].resolve().relative_to(root).as_posix()
                if chosen
                else "",
                "canonical_amount_source": "local_all_a_price_cache"
                if raw.get("amount_usable")
                else "",
                "canonical_amount_path": raw["path"].resolve().relative_to(root).as_posix()
                if raw.get("amount_usable")
                else "",
                "resolution_status": "JOINT_USABLE"
                if chosen and raw.get("amount_usable")
                else "QFQ_MISSING"
                if not chosen
                else "AMOUNT_MISSING",
                "conflict_note": "",
            }
        )
    resolution = pd.DataFrame(resolution_rows)
    resolution.to_csv(
        report_dir / "source_resolution_report.csv", index=False, encoding="utf-8-sig"
    )
    resolution_status = resolution.set_index("stock_code")["resolution_status"].to_dict()

    manifest_rows = []
    canonical: dict[str, pd.DataFrame] = {}
    for code in included:
        chosen = selected.get(code)
        raw = raw_profiles[code]
        if not chosen:
            manifest_rows.append(
                {
                    "stock_code": code,
                    "storage_path": "",
                    "rows": 0,
                    "date_min": "",
                    "date_max": "",
                    "qfq_valid_rows": 0,
                    "amount_valid_rows": raw.get("amount_valid_rows", 0),
                    "joint_valid_rows": 0,
                }
            )
            continue
        if chosen:
            qfq = pd.read_csv(chosen["path"], dtype={"stock_code": str})[
                ["trade_date", "qfq_close"]
            ]
            qfq["trade_date"] = pd.to_datetime(qfq["trade_date"], errors="raise")
            qfq["qfq_close"] = pd.to_numeric(qfq["qfq_close"], errors="coerce")
            qfq = qfq.loc[_finite_positive(qfq["qfq_close"])].drop_duplicates(
                "trade_date", keep=False
            )
        else:
            qfq = pd.DataFrame(columns=["trade_date", "qfq_close"])
        raw_frame = pd.read_csv(raw["path"], usecols=["date", "amount"], low_memory=False)
        raw_frame["trade_date"] = pd.to_datetime(raw_frame.pop("date"), errors="raise")
        raw_frame["amount"] = pd.to_numeric(raw_frame["amount"], errors="coerce")
        raw_frame.loc[~_finite_nonnegative(raw_frame["amount"]), "amount"] = np.nan
        raw_frame = raw_frame.drop_duplicates("trade_date", keep=False)
        merged = qfq.merge(
            raw_frame, on="trade_date", how="outer", validate="one_to_one"
        ).sort_values("trade_date")
        merged.insert(0, "stock_code", code)
        merged["price_source"] = chosen["source"] if chosen else ""
        merged["amount_source"] = "local_all_a_price_cache" if raw.get("amount_usable") else ""
        merged["qfq_status"] = np.where(_finite_positive(merged["qfq_close"]), "VALID", "MISSING")
        qfq_valid = _finite_positive(merged["qfq_close"])
        amount_valid = _finite_nonnegative(merged["amount"])
        if chosen:
            storage_path = daily_dir / f"{code}.csv"
            merged.to_csv(storage_path, index=False, encoding="utf-8-sig")
            canonical[code] = merged.set_index("trade_date")[["qfq_close", "amount"]]
            relative_storage = storage_path.relative_to(root).as_posix()
        else:
            relative_storage = ""
        manifest_rows.append(
            {
                "stock_code": code,
                "storage_path": relative_storage,
                "rows": len(merged) if chosen else 0,
                "date_min": merged["trade_date"].min() if chosen else "",
                "date_max": merged["trade_date"].max() if chosen else "",
                "qfq_valid_rows": int(qfq_valid.sum()),
                "amount_valid_rows": int(amount_valid.sum()),
                "joint_valid_rows": int((qfq_valid & amount_valid).sum()),
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(
        processed_dir / "h5a_broader_a_daily_v1_manifest.csv", index=False, encoding="utf-8-sig"
    )

    calendar, signals = load_calendar_and_signals(root)
    signal_calendar = signals.rename(
        columns={
            "rebalance_date": "rebalance_date_if_existing",
            "next_rebalance_date": "next_rebalance_date_if_existing",
        }
    )
    signal_calendar["calendar_source"] = (
        "CSI300 dates from hybrid_benchmark_panel_v1_5.csv; locked dates from mom60_factor_panel_v1_3.csv"
    )
    signal_calendar.to_csv(
        processed_dir / "h5a_broader_a_signal_calendar_v1.csv", index=False, encoding="utf-8-sig"
    )

    feature_rows = []
    availability_rows = []
    for signal in signals.itertuples(index=False):
        signal_date = signal.signal_as_of_date
        signal_pos = calendar.get_indexer([signal_date])[0]
        lookback_date = calendar[signal_pos - 60] if signal_pos >= 60 else pd.NaT
        amount_dates = (
            calendar[signal_pos - 19 : signal_pos + 1] if signal_pos >= 19 else pd.DatetimeIndex([])
        )
        endpoints = {h: endpoint_date(calendar, signal.rebalance_date, h) for h in (20, 60, 120)}
        period_start = len(feature_rows)
        for code in included:
            panel = canonical.get(code)
            return_value = math.nan
            amount_value = math.nan
            history_days = 0
            if panel is not None:
                history_days = int(panel.loc[panel.index <= signal_date, "qfq_close"].notna().sum())
                if signal_date in panel.index and lookback_date in panel.index:
                    endpoints_values = panel.loc[[lookback_date, signal_date], "qfq_close"]
                    if _finite_positive(endpoints_values).all():
                        return_value = float(
                            endpoints_values.iloc[1] / endpoints_values.iloc[0] - 1
                        )
                amounts = panel["amount"].reindex(amount_dates)
                if len(amount_dates) == 20 and _finite_positive(amounts).all():
                    amount_value = float(amounts.mean())
            return_valid = math.isfinite(return_value)
            amount_valid = math.isfinite(amount_value)
            reasons = []
            if not return_valid:
                reasons.append("RETURN60_ENDPOINT_MISSING_OR_INVALID")
            if not amount_valid:
                reasons.append("AMOUNT20_INCOMPLETE_OR_NONPOSITIVE")
            feature_rows.append(
                {
                    "period_index": signal.period_index,
                    "signal_as_of_date": signal_date,
                    "stock_code": code,
                    "return_60": return_value,
                    "return60_valid": return_valid,
                    "amount_mean_20": amount_value,
                    "amount20_valid": amount_valid,
                    "activity_pct": math.nan,
                    "signal_ready": return_valid and amount_valid,
                    "signal_not_ready_reason": ";".join(reasons),
                    "history_days_available": history_days,
                    "source_status": resolution_status[code],
                }
            )
            available = {}
            for horizon, date in endpoints.items():
                value = (
                    panel.loc[date, "qfq_close"]
                    if panel is not None and pd.notna(date) and date in panel.index
                    else math.nan
                )
                available[horizon] = (
                    bool(math.isfinite(float(value)) and float(value) > 0)
                    if not pd.isna(value)
                    else False
                )
            availability_rows.append(
                {
                    "period_index": signal.period_index,
                    "stock_code": code,
                    **{f"endpoint_{h}d_date": endpoints[h] for h in (20, 60, 120)},
                    **{f"endpoint_{h}d_available": available[h] for h in (20, 60, 120)},
                }
            )
        period_slice = pd.DataFrame(feature_rows[period_start:])
        ready = period_slice["signal_ready"]
        if ready.any():
            percentiles = period_slice.loc[ready, "amount_mean_20"].rank(method="average", pct=True)
            for local_index, percentile in percentiles.items():
                feature_rows[period_start + local_index]["activity_pct"] = float(percentile)
    features = pd.DataFrame(feature_rows)
    features.to_csv(
        processed_dir / "h5a_broader_a_signal_features_v1.csv", index=False, encoding="utf-8-sig"
    )
    availability = pd.DataFrame(availability_rows)
    availability.to_csv(
        processed_dir / "h5a_broader_a_future_endpoint_availability_v1.csv",
        index=False,
        encoding="utf-8-sig",
    )

    coverage = features.groupby(["period_index", "signal_as_of_date"], as_index=False).agg(
        universe_count=("stock_code", "size"),
        return60_valid_count=("return60_valid", "sum"),
        amount20_valid_count=("amount20_valid", "sum"),
        signal_ready_count=("signal_ready", "sum"),
    )
    coverage["signal_ready_ratio"] = coverage["signal_ready_count"] / coverage["universe_count"]
    coverage["at_least_500"] = coverage["signal_ready_count"].ge(500)
    coverage["at_least_1000"] = coverage["signal_ready_count"].ge(1000)
    coverage.to_csv(report_dir / "signal_period_coverage.csv", index=False, encoding="utf-8-sig")

    cell_detail = []
    labels = {2: ("low", "high"), 3: ("low", "middle", "high")}
    for period, group in features.loc[features["signal_ready"]].groupby("period_index", sort=True):
        for groups in (2, 3):
            working = group.copy()
            working["return_group"] = stable_groups(working, "return_60", groups)
            working["activity_group"] = stable_groups(working, "amount_mean_20", groups)
            for r in range(1, groups + 1):
                for a in range(1, groups + 1):
                    cell_detail.append(
                        {
                            "row_type": "period_cell",
                            "state_structure": f"{groups}x{groups}",
                            "period_index": period,
                            "state_cell": f"return_{labels[groups][r - 1]}__activity_{labels[groups][a - 1]}",
                            "stock_count": int(
                                (
                                    working["return_group"].eq(r) & working["activity_group"].eq(a)
                                ).sum()
                            ),
                            "median": math.nan,
                            "p10": math.nan,
                            "minimum": math.nan,
                            "periods_lt_10": math.nan,
                            "periods_lt_25": math.nan,
                            "periods_lt_50": math.nan,
                        }
                    )
    detail = pd.DataFrame(cell_detail)
    summaries = []
    if len(detail):
        for (structure, cell), group in detail.groupby(["state_structure", "state_cell"]):
            values = group["stock_count"]
            summaries.append(
                {
                    "row_type": "cell_summary",
                    "state_structure": structure,
                    "period_index": "",
                    "state_cell": cell,
                    "stock_count": math.nan,
                    "median": values.median(),
                    "p10": values.quantile(0.1),
                    "minimum": values.min(),
                    "periods_lt_10": int(values.lt(10).sum()),
                    "periods_lt_25": int(values.lt(25).sum()),
                    "periods_lt_50": int(values.lt(50).sum()),
                }
            )
    cell_output = pd.concat([detail, pd.DataFrame(summaries)], ignore_index=True)
    cell_output.to_csv(
        report_dir / "state_cell_size_readiness.csv", index=False, encoding="utf-8-sig"
    )

    theme = pd.read_csv(
        root / "data/processed/research_universe_lowvol_freeze_20260711.csv", dtype={"code": str}
    )
    theme["code"] = theme["code"].map(code6)
    transfer_rows = []
    for period in signals["period_index"]:
        period_features = features.loc[features["period_index"].eq(period)].set_index("stock_code")
        for scope, token in (("AI", "AI"), ("商业航天", "商业航天")):
            codes = sorted(theme.loc[theme["theme"].str.contains(token, na=False), "code"].unique())
            mapped = [code for code in codes if code in included]
            qfq_mapped = [code for code in mapped if code in selected]
            ready_count = int(period_features.reindex(mapped)["signal_ready"].fillna(False).sum())
            transfer_rows.append(
                {
                    "period_index": period,
                    "theme": scope,
                    "frozen_theme_stock_count": len(codes),
                    "mapped_to_broader_universe_count": len(mapped),
                    "qfq_available_count": len(qfq_mapped),
                    "signal_ready_count": ready_count,
                    "signal_ready_ratio": ready_count / len(codes) if codes else 0,
                }
            )
    transfer = pd.DataFrame(transfer_rows)
    transfer.to_csv(report_dir / "theme_transfer_readiness.csv", index=False, encoding="utf-8-sig")

    usable = manifest.loc[manifest["qfq_valid_rows"].gt(0)].copy()
    usable["date_max"] = pd.to_datetime(usable["date_max"], errors="coerce")
    typical_ready = float(coverage["signal_ready_count"].median())
    joint_codes = int(resolution["resolution_status"].eq("JOINT_USABLE").sum())
    qfq_codes = int(resolution["canonical_price_source"].ne("").sum())
    amount_codes = int(resolution["canonical_amount_source"].ne("").sum())
    latest = usable["date_max"]
    stale_july = int(latest.lt(pd.Timestamp("2026-07-01")).sum())
    stale_aug = int(latest.lt(pd.Timestamp("2026-08-01")).sum())
    structure_medians = (
        detail.groupby("state_structure")["stock_count"].median()
        if len(detail)
        else pd.Series(dtype=float)
    )
    structure_minima = (
        detail.groupby("state_structure")["stock_count"].min()
        if len(detail)
        else pd.Series(dtype=float)
    )
    three_by_three = detail.loc[detail["state_structure"].eq("3x3"), "stock_count"]
    board_coverage = resolution.assign(
        board=resolution["stock_code"].map(
            lambda code: "STAR"
            if code.startswith("688")
            else "CHINEXT"
            if code.startswith(("300", "301"))
            else "SH_MAIN"
            if code.startswith("6")
            else "SZ_MAIN"
        ),
        qfq_ok=resolution["canonical_price_source"].ne(""),
    ).groupby("board")["qfq_ok"].mean()
    ready = (
        joint_codes >= 4676
        and int(coverage["at_least_1000"].sum()) >= 52
        and float(board_coverage.min()) >= 0.85
        and float(three_by_three.median()) >= 75
        and float(three_by_three.quantile(0.1)) >= 25
        and float(three_by_three.ge(25).mean()) >= 0.90
    )
    ready_with_limitations = (
        joint_codes / len(included) >= 0.85
        and int(coverage["at_least_1000"].sum()) >= 46
        and float(board_coverage.min()) >= 0.80
        and float(three_by_three.median()) >= 50
        and float(three_by_three.quantile(0.1)) >= 20
    )
    classification = (
        "BROADER_A_H5A_PANEL_READY"
        if ready
        else "BROADER_A_H5A_PANEL_READY_WITH_LIMITATIONS"
        if ready_with_limitations
        else "BROADER_A_H5A_PANEL_NOT_READY"
    )

    missing_qfq = resolution.loc[resolution["canonical_price_source"].eq(""), "stock_code"].tolist()
    missing_amount = resolution.loc[
        resolution["canonical_amount_source"].eq(""), "stock_code"
    ].tolist()
    refresh = f"""# Future refresh requirements\n\n+This is a planning list only. No network refresh was run.\n\n+- QFQ missing: **{len(missing_qfq):,}** stocks. Full code-level list: `source_resolution_report.csv` where `canonical_price_source` is blank.\n+- Amount missing: **{len(missing_amount):,}** stocks. Full code-level list: `source_resolution_report.csv` where `canonical_amount_source` is blank.\n+- Canonical QFQ stale before 2026-07-01: **{stale_july:,}**; before 2026-08-01: **{stale_aug:,}**.\n+- Source anomaly: the all-A cache is RAW/unadjusted and cannot be used for RETURN_60. It remains valid only as the amount source.\n+- A future historical H5A run requires verified QFQ backfill for the missing broader-A codes. A future prospective run additionally requires a point-in-time universe/eligibility contract and a separately approved freshness refresh.\n+"""
    refresh = refresh.replace("\n+", "\n")
    (report_dir / "future_refresh_requirements.md").write_text(refresh, encoding="utf-8")

    report = f"""# Broader A-Share H5A Data Panel Preparation v1\n\n+## Technical summary\n\n+**{classification}.** The current-universe historical panel contains {joint_codes:,}/{len(included):,} stocks with both canonical Sina QFQ and amount. The RAW all-A close was not substituted for QFQ. This is a data-readiness result, not an H5A performance result.\n\n+## Key findings\n\n+1. QFQ usable: {qfq_codes:,}; amount usable: {amount_codes:,}; joint usable: {joint_codes:,}.\n+2. Signal-ready periods: {int(coverage["at_least_1000"].sum())}/57 with at least 1,000 stocks; median {typical_ready:.0f}; minimum {coverage["signal_ready_count"].min():.0f}.\n+3. 2x2 period-cell size: median {structure_medians.get("2x2", math.nan):.1f}; minimum {structure_minima.get("2x2", math.nan):.1f}.\n+4. 3x3 period-cell size: median {structure_medians.get("3x3", math.nan):.1f}; minimum {structure_minima.get("3x3", math.nan):.1f}; p10 {three_by_three.quantile(0.1):.1f}; share at least 25 {three_by_three.ge(25).mean():.2%}.\n+5. Minimum board QFQ coverage: {board_coverage.min():.2%}; board detail: {board_coverage.to_dict()}.\n+6. AI transfer median/min signal-ready: {transfer.loc[transfer["theme"].eq("AI"), "signal_ready_count"].median():.0f}/{transfer.loc[transfer["theme"].eq("AI"), "signal_ready_count"].min():.0f}.\n+7. Commercial-space transfer median/min signal-ready: {transfer.loc[transfer["theme"].eq("商业航天"), "signal_ready_count"].median():.0f}/{transfer.loc[transfer["theme"].eq("商业航天"), "signal_ready_count"].min():.0f}.\n+8. Missing canonical QFQ: {len(missing_qfq):,}; missing amount: {len(missing_amount):,}.\n+9. Universe is current, not historical point-in-time, so survivorship bias remains.\n\n+## Contract and QA\n\n+{"; ".join(f"{key}={value}" for key, value in IDENTITY.items())}. `RETURN_60` uses canonical QFQ at the signal date and the exact CSI300 market date 60 sessions earlier. `AMOUNT_MEAN_20` uses the exact 20 CSI300 market dates ending at the signal date and requires positive finite observations. Source resolution uses only the explicit Sina broader-A QFQ cache. No forward fill, backfill, future-return selection, RankIC, performance, MCTS, Phase B, or network refresh was run. Future endpoint output records availability only.\n\n+## Limitation\n\n+The strict amount window estimates continuously observable stocks. Suspensions or missing dates remain missing. Historical listing, ST and delisting-risk eligibility were not reconstructed.\n"""
    report = report.replace("\n+", "\n")
    (report_dir / "broader_a_h5a_panel_preparation_report.md").write_text(report, encoding="utf-8")

    # Contract assertions are kept adjacent to the outputs they protect.
    assert features.duplicated(["period_index", "stock_code"]).sum() == 0
    assert len(signal_calendar) == 57
    assert not any(
        "future" in column.lower() or "rankic" in column.lower() for column in features.columns
    )
    assert not any("return" in column.lower() for column in availability.columns)
    assert features.loc[features["signal_ready"], "activity_pct"].between(0, 1).all()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--qfq-cache", type=Path, default=DEFAULT_QFQ_DIR)
    args = parser.parse_args()
    run(args.project_root, args.qfq_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
