from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import qlib
from qlib.config import REG_CN
from qlib.contrib.data.handler import Alpha158DL
from qlib.data import D

from aq_factor_lab.alpha_jungle_c0.contract import C0, assert_period_allowed


SAMPLE_WINDOWS = (
    ("2011-01-04", "2011-01-10"),
    ("2016-06-01", "2016-06-07"),
    ("2020-06-01", "2020-06-05"),
    ("2024-11-25", "2024-11-29"),
)
RAW_FIELDS = (
    "$open",
    "$high",
    "$low",
    "$close",
    "$volume",
    "$vwap",
    "$factor",
    "$amount",
    "$adjclose",
)


def _finite_number(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _alpha158_split(
    expressions: list[str], names: list[str], start: date, end: date, chunk_size: int
) -> dict[str, object]:
    # This is the hard guard that keeps the audit away from the frozen Final Test.
    assert_period_allowed(start, end)
    universe = D.instruments(C0.universe)
    feature_stats: dict[str, dict[str, object]] = {}
    row_counts: list[int] = []
    date_count = instrument_count = 0
    first_date = last_date = None

    for offset in range(0, len(expressions), chunk_size):
        chunk_expr = expressions[offset : offset + chunk_size]
        chunk_names = names[offset : offset + chunk_size]
        frame = D.features(
            universe,
            chunk_expr,
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            freq="day",
        )
        row_counts.append(len(frame))
        dates = frame.index.get_level_values("datetime")
        instruments = frame.index.get_level_values("instrument")
        date_count = max(date_count, dates.nunique())
        instrument_count = max(instrument_count, instruments.nunique())
        first_date = dates.min() if first_date is None else min(first_date, dates.min())
        last_date = dates.max() if last_date is None else max(last_date, dates.max())

        for expr, name in zip(chunk_expr, chunk_names):
            values = frame[expr].astype(float)
            finite = values[np.isfinite(values)]
            minimum = finite.min() if len(finite) else float("nan")
            maximum = finite.max() if len(finite) else float("nan")
            feature_stats[name] = {
                "expression": expr,
                "non_null": int(values.notna().sum()),
                "finite": int(np.isfinite(values).sum()),
                "minimum": _finite_number(minimum),
                "maximum": _finite_number(maximum),
                "all_nan": bool(values.notna().sum() == 0),
                "constant": bool(len(finite) > 0 and minimum == maximum),
            }

    all_nan = sorted(name for name, stat in feature_stats.items() if stat["all_nan"])
    constant = sorted(name for name, stat in feature_stats.items() if stat["constant"])
    return {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "observed_first_session": first_date.date().isoformat(),
        "observed_last_session": last_date.date().isoformat(),
        "sessions": int(date_count),
        "instruments_seen": int(instrument_count),
        "row_count_min_across_chunks": min(row_counts),
        "row_count_max_across_chunks": max(row_counts),
        "feature_count": len(feature_stats),
        "all_nan_features": all_nan,
        "constant_features": constant,
        "features": feature_stats,
    }


def _raw_field_audit() -> dict[str, object]:
    universe = D.instruments(C0.universe)
    windows: list[dict[str, object]] = []
    total_rows = 0
    total_ohlc_violations = 0
    identity_errors: list[float] = []
    factor_nonpositive = 0
    adjclose_scale_spreads: list[float] = []
    sample_frames: list[pd.DataFrame] = []

    for start, end in SAMPLE_WINDOWS:
        frame = D.features(universe, list(RAW_FIELDS), start_time=start, end_time=end, freq="day")
        sample_frames.append(frame)
        finite = np.isfinite(frame.astype(float))
        ohlc_ok = (
            (frame["$low"] <= frame[["$open", "$close"]].min(axis=1))
            & (frame["$high"] >= frame[["$open", "$close"]].max(axis=1))
        )
        ratio = frame["$amount"] / (frame["$volume"] * frame["$vwap"])
        ratio_error = (ratio - 0.1).abs().replace([np.inf, -np.inf], np.nan).dropna()
        scale = frame["$adjclose"] / frame["$close"]
        scale_spread = scale.groupby(level="instrument").agg(lambda x: x.max() - x.min())

        rows = len(frame)
        violations = int((~ohlc_ok & frame[["$open", "$high", "$low", "$close"]].notna().all(axis=1)).sum())
        total_rows += rows
        total_ohlc_violations += violations
        identity_errors.extend(ratio_error.tolist())
        factor_nonpositive += int((frame["$factor"].dropna() <= 0).sum())
        adjclose_scale_spreads.extend(scale_spread.dropna().tolist())
        windows.append(
            {
                "start": start,
                "end": end,
                "rows": rows,
                "sessions": int(frame.index.get_level_values("datetime").nunique()),
                "instruments": int(frame.index.get_level_values("instrument").nunique()),
                "all_fields_have_finite_observations": bool(finite.any(axis=0).all()),
                "ohlc_violations": violations,
            }
        )

    combined = pd.concat(sample_frames)
    field_stats = {}
    for field in RAW_FIELDS:
        values = combined[field].astype(float)
        finite = values[np.isfinite(values)]
        field_stats[field] = {
            "non_null": int(values.notna().sum()),
            "finite": int(np.isfinite(values).sum()),
            "minimum": _finite_number(finite.min()),
            "maximum": _finite_number(finite.max()),
            "constant": bool(finite.min() == finite.max()),
        }
    reconstructed_raw_close = combined["$close"] / combined["$factor"]
    reconstructed_raw_close = reconstructed_raw_close.replace([np.inf, -np.inf], np.nan).dropna()

    return {
        "fields": list(RAW_FIELDS),
        "field_stats": field_stats,
        "windows": windows,
        "rows": total_rows,
        "ohlc_violations": total_ohlc_violations,
        "nonpositive_factor_rows": factor_nonpositive,
        "max_abs_amount_over_volume_vwap_minus_0_1": max(identity_errors),
        "max_within_instrument_adjclose_over_close_spread": max(adjclose_scale_spreads),
        "reconstructed_raw_close": {
            "formula": "$close / $factor",
            "finite_positive_rows": int(
                (np.isfinite(reconstructed_raw_close) & (reconstructed_raw_close > 0)).sum()
            ),
            "minimum": float(reconstructed_raw_close.min()),
            "maximum": float(reconstructed_raw_close.max()),
            "constant": bool(reconstructed_raw_close.min() == reconstructed_raw_close.max()),
        },
        "vwap_semantics": "amount / (adjusted_volume * adjusted_vwap) = 0.1",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the frozen C0 Qlib data gate without Test outcomes.")
    parser.add_argument("--provider-uri", type=Path, default=Path(r"D:\qlib_data\cn_data"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/alpha_jungle_c0/QLIB_DATA_GATE_EVIDENCE.json"),
    )
    parser.add_argument("--chunk-size", type=int, default=32)
    args = parser.parse_args()

    qlib.init(provider_uri=str(args.provider_uri.resolve()), region=REG_CN)
    calendar = pd.DatetimeIndex(D.calendar(start_time="2011-01-01", end_time="2024-11-30", freq="day"))
    membership_counts = {}
    for day in ("2011-01-04", "2016-06-01", "2020-06-01", "2024-11-29"):
        members = D.list_instruments(
            D.instruments(C0.universe), start_time=day, end_time=day, freq="day", as_list=True
        )
        membership_counts[day] = len(members)

    expressions, names = Alpha158DL.get_feature_config()
    train = _alpha158_split(expressions, names, C0.train_start, C0.train_end, args.chunk_size)
    validation = _alpha158_split(
        expressions, names, C0.validation_start, C0.validation_end, args.chunk_size
    )
    evidence = {
        "python": sys.version,
        "qlib_version": qlib.__version__,
        "qlib_path": str(Path(qlib.__file__).resolve()),
        "provider_uri": str(args.provider_uri.resolve()),
        "calendar": {
            "first_required_session": calendar.min().date().isoformat(),
            "last_required_session": calendar.max().date().isoformat(),
            "sessions": len(calendar),
        },
        "historical_csi300_membership_counts": membership_counts,
        "raw_field_audit": _raw_field_audit(),
        "alpha158": {"configured_feature_count": len(expressions), "train": train, "validation": validation},
        "label_expression_not_loaded": C0.label_expression,
        "final_test_performance_accessed": False,
        "search_executed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "alpha158": evidence["alpha158"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
