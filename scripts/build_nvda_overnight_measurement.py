"""Build the 20-row NVDA overnight measurement-design pilot."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from forensic_nvda_session_retrieval import (
    NVDA_POOL,
    OFFICIAL_RPC,
    decode,
    first_block_at_or_after,
    query,
)


PHASE0_DIR = Path("reports/robinhood_chain_phase0/nvda_20_session")
OUTPUT_DIR = Path("reports/robinhood_chain_pilot/nvda_20_session")
OUTPUT_CSV = OUTPUT_DIR / "nvda_overnight_session_measurements.csv"
SUMMARY_MD = OUTPUT_DIR / "measurement_summary.md"
DIAGNOSTICS_JSON = OUTPUT_DIR / "diagnostics.json"
UNDERLYING_JSON = OUTPUT_DIR / "underlying_source.json"
BOUNDARY_JSON = OUTPUT_DIR / "last_trade_1600_source.json"
SCATTER_PNG = OUTPUT_DIR / "return_gap_scatter.png"
NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
NASDAQ_URL = (
    "https://api.nasdaq.com/api/quote/NVDA/historical"
    "?assetclass=stocks&fromdate=2026-08-01&todate=2026-09-04&limit=30"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/market-activity/stocks/nvda/historical",
}
SEGMENTS = ("post", "deep", "premarket", "full")
THIN_BOUNDARY_MIN_SWAPS = 5
THIN_BOUNDARY_MIN_NOTIONAL_USDG = 500


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def money(value: str) -> float:
    return float(value.replace("$", "").replace(",", ""))


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
    for retry in range(6):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if retry == 5:
                raise
            time.sleep(min(2 ** (retry + 1), 15))


def fetch_underlying() -> dict:
    if UNDERLYING_JSON.exists():
        return json.loads(UNDERLYING_JSON.read_text(encoding="utf-8"))

    nasdaq_payload = get_json(NASDAQ_URL, headers=HEADERS)
    rows = nasdaq_payload["data"]["tradesTable"]["rows"]
    nasdaq = {
        datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat(): {
            "open": money(row["open"]),
            "close": money(row["close"]),
        }
        for row in rows
    }
    required_dates = {day.date().isoformat() for day in pd.bdate_range("2026-08-07", "2026-09-04")}
    assert len(required_dates) == 21 and required_dates.issubset(nasdaq)

    result = {
        "nasdaq_url": NASDAQ_URL,
        "nasdaq_page": "https://www.nasdaq.com/market-activity/stocks/nvda/historical",
        "nasdaq_rows": nasdaq,
        "required_dates": sorted(required_dates),
        "required_date_coverage": "21 / 21",
        "adjustment_convention": "raw Nasdaq Open and Close/Last; no adjusted-close field used",
    }
    write_json(UNDERLYING_JSON, result)
    return result


def rpc_logs(session: requests.Session, first_block: int, last_block: int) -> list[dict]:
    pending = [(first_block, last_block)]
    logs: list[dict] = []
    while pending:
        first, last = pending.pop(0)
        for retry in range(8):
            try:
                response = session.post(
                    OFFICIAL_RPC,
                    json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [query(first, last)]},
                    headers={"User-Agent": "nvda-measurement-boundary/0.1"},
                    timeout=40,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.RequestException(str(response.status_code))
                response.raise_for_status()
                payload = response.json()
                if "result" in payload:
                    logs.extend(payload["result"])
                    break
                message = str(payload.get("error", "")).lower()
                if ("limit" in message or "exceed" in message) and last > first:
                    middle = (first + last) // 2
                    pending[:0] = [(first, middle), (middle + 1, last)]
                    break
                raise RuntimeError(payload.get("error"))
            except (requests.RequestException, RuntimeError, ValueError):
                if retry == 7:
                    raise
                time.sleep(min(2 ** (retry + 1), 30))
    unique = {(event["transactionHash"].lower(), int(event["logIndex"], 16)): event for event in logs}
    return sorted(unique.values(), key=lambda event: (int(event["blockNumber"], 16), int(event["logIndex"], 16)))


def fetch_last_trade_1600(quality: pd.DataFrame) -> dict:
    result = json.loads(BOUNDARY_JSON.read_text(encoding="utf-8")) if BOUNDARY_JSON.exists() else {}
    session = requests.Session()
    for row in quality.itertuples(index=False):
        if row.market_open_date in result:
            continue
        boundary = datetime.fromisoformat(row.session_start_et)
        window_start = boundary - timedelta(minutes=5)
        for retry in range(6):
            try:
                first = first_block_at_or_after(session, OFFICIAL_RPC, int(window_start.astimezone(UTC).timestamp()))
                break
            except (requests.RequestException, RuntimeError, ValueError):
                if retry == 5:
                    raise
                time.sleep(min(2 ** (retry + 1), 15))
        last = int(row.exact_block_start) - 1
        events = rpc_logs(session, first, last)
        decoded = [decode(event, 1.0) for event in events]
        valid = [item for item in decoded if item["reconstructable"]]
        last_trade = valid[-1] if valid else None
        result[row.market_open_date] = {
            "window_start_et": window_start.isoformat(),
            "window_end_et_exclusive": boundary.isoformat(),
            "exact_block_start": first,
            "exact_block_end": last,
            "swap_count": len(events),
            "last_transaction_hash": last_trade["transaction_hash"] if last_trade else None,
            "last_log_index": last_trade["log_index"] if last_trade else None,
            "last_price_usdg": last_trade["underlying_equivalent_price_usdg"] if last_trade else None,
            "provider": OFFICIAL_RPC,
        }
        write_json(BOUNDARY_JSON, result)
        print(f"16:00 sensitivity boundary {row.market_open_date}: {len(events)} swaps", flush=True)
    assert set(result) == set(quality["market_open_date"])
    return result


def boundary_metrics(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    sample = frame.loc[
        frame["reconstructable"]
        & frame["timestamp"].ge(start)
        & frame["timestamp"].lt(end)
    ]
    weight = sample["quote_amount_usdg"].sum()
    return {
        "vwap": float((sample["underlying_equivalent_price_usdg"] * sample["quote_amount_usdg"]).sum() / weight) if weight > 0 else math.nan,
        "swap_count": int(len(sample)),
        "notional_usdg": float(weight),
    }


def last_price_before(frame: pd.DataFrame, boundary: pd.Timestamp) -> float:
    sample = frame.loc[frame["reconstructable"] & frame["timestamp"].lt(boundary)]
    return float(sample.iloc[-1]["underlying_equivalent_price_usdg"]) if not sample.empty else math.nan


def log_return(end: float, start: float) -> float:
    return math.log(end / start) if np.isfinite(start) and np.isfinite(end) and start > 0 and end > 0 else math.nan


def segment_metrics(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    sample = frame.loc[frame["timestamp"].ge(start) & frame["timestamp"].lt(end)]
    minutes = (end - start).total_seconds() / 60
    active = sample["timestamp"].dt.floor("min").nunique()
    sizes = sample.loc[sample["reconstructable"], "quote_amount_usdg"]
    return {
        "swap_count": int(len(sample)),
        "notional": float(sizes.sum()),
        "active_minutes": int(active),
        "active_min_share": float(active / minutes),
        "median_trade_size": float(sizes.median()) if not sizes.empty else math.nan,
    }


def build_table() -> pd.DataFrame:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    quality = pd.read_csv(PHASE0_DIR / "nvda_session_quality.csv")
    assert len(quality) == quality["market_open_date"].nunique() == 20
    assert quality["completion_status"].eq("complete").all()
    underlying = fetch_underlying()
    boundary_1600 = fetch_last_trade_1600(quality)
    nasdaq = underlying["nasdaq_rows"]
    rows = []

    for index, quality_row in quality.iterrows():
        open_date = quality_row["market_open_date"]
        frame = pd.read_csv(PHASE0_DIR / "sessions" / open_date / "decoded_swaps.csv")
        frame["timestamp"] = pd.to_datetime(frame["block_timestamp_et"], utc=True).dt.tz_convert(NEW_YORK)
        frame = frame.sort_values(["timestamp", "block_number", "log_index"]).reset_index(drop=True)
        start = pd.Timestamp(quality_row["session_start_et"])
        end = pd.Timestamp(quality_row["session_end_et_exclusive"])
        boundary_2000 = start.normalize() + pd.Timedelta(hours=20)
        boundary_0400 = end.normalize() + pd.Timedelta(hours=4)
        boundaries = {"1600": start, "2000": boundary_2000, "0400": boundary_0400, "0930": end}
        windows = {
            "1600": (start, start + pd.Timedelta(minutes=5)),
            "2000": (boundary_2000 - pd.Timedelta(minutes=5), boundary_2000),
            "0400": (boundary_0400 - pd.Timedelta(minutes=5), boundary_0400),
            "0930": (end - pd.Timedelta(minutes=5), end),
        }
        boundary_activity = {name: boundary_metrics(frame, *window) for name, window in windows.items()}
        vwaps = {name: values["vwap"] for name, values in boundary_activity.items()}
        lasts = {
            "1600": boundary_1600[open_date]["last_price_usdg"],
            "2000": last_price_before(frame, boundary_2000),
            "0400": last_price_before(frame, boundary_0400),
            "0930": last_price_before(frame, end),
        }
        segments = {
            "post": (start, boundary_2000),
            "deep": (boundary_2000, boundary_0400),
            "premarket": (boundary_0400, end),
            "full": (start, end),
        }
        activity = {name: segment_metrics(frame, *bounds) for name, bounds in segments.items()}
        missing = [name for name, value in vwaps.items() if not np.isfinite(value)]
        thin = [
            name
            for name, values in boundary_activity.items()
            if values["swap_count"] < THIN_BOUNDARY_MIN_SWAPS
            or values["notional_usdg"] < THIN_BOUNDARY_MIN_NOTIONAL_USDG
        ]
        decomposition_error = log_return(vwaps["0930"], vwaps["1600"]) - sum(
            [log_return(vwaps["2000"], vwaps["1600"]), log_return(vwaps["0400"], vwaps["2000"]), log_return(vwaps["0930"], vwaps["0400"])]
        ) if not missing else math.nan
        last_decomposition_error = log_return(lasts["0930"], lasts["1600"]) - sum(
            [log_return(lasts["2000"], lasts["1600"]), log_return(lasts["0400"], lasts["2000"]), log_return(lasts["0930"], lasts["0400"])]
        )

        previous_date = quality.iloc[index - 1]["market_open_date"] if index else "2026-08-07"
        previous_close = nasdaq[previous_date]["close"]
        underlying_issue = ""
        warnings = []
        if missing:
            warnings.append("missing primary VWAP: " + ",".join(missing))
        if thin:
            warnings.append("thin primary boundary (<5 swaps or <500 USDG): " + ",".join(thin))
        if abs(decomposition_error) > 1e-12:
            warnings.append("primary return decomposition failed")
        if underlying_issue:
            warnings.append(underlying_issue)

        row = {
            "session_id": f"NVDA_{open_date}",
            "market_open_date": open_date,
            "session_start_et": start.isoformat(),
            "session_end_et_exclusive": end.isoformat(),
            **{f"token_vwap_{name}": value for name, value in vwaps.items()},
            **{f"boundary_swap_count_{name}": values["swap_count"] for name, values in boundary_activity.items()},
            **{f"boundary_notional_usdg_{name}": values["notional_usdg"] for name, values in boundary_activity.items()},
            **{f"token_last_{name}": value for name, value in lasts.items()},
            "token_ret_full": log_return(vwaps["0930"], vwaps["1600"]),
            "token_ret_post": log_return(vwaps["2000"], vwaps["1600"]),
            "token_ret_deep": log_return(vwaps["0400"], vwaps["2000"]),
            "token_ret_premarket": log_return(vwaps["0930"], vwaps["0400"]),
            "token_ret_full_last_trade": log_return(lasts["0930"], lasts["1600"]),
            "token_ret_post_last_trade": log_return(lasts["2000"], lasts["1600"]),
            "token_ret_deep_last_trade": log_return(lasts["0400"], lasts["2000"]),
            "token_ret_premarket_last_trade": log_return(lasts["0930"], lasts["0400"]),
            "return_decomposition_error": decomposition_error,
            "return_decomposition_valid": bool(np.isfinite(decomposition_error) and abs(decomposition_error) <= 1e-12),
            "return_decomposition_error_last_trade": last_decomposition_error,
            "return_decomposition_valid_last_trade": bool(np.isfinite(last_decomposition_error) and abs(last_decomposition_error) <= 1e-12),
            "nvda_previous_close_date": previous_date,
            "nvda_previous_close": previous_close,
            "nvda_next_open": nasdaq[open_date]["open"],
            "nvda_gap_return": log_return(nasdaq[open_date]["open"], previous_close),
        }
        for segment in SEGMENTS:
            for metric, value in activity[segment].items():
                row[f"{metric}_{segment}"] = value
        row.update(
            {
                "price_reconstruction_rate": quality_row["reconstructable_price_percentage"] / 100,
                "first_execution_timestamp": quality_row["first_execution_timestamp_et"],
                "last_execution_timestamp": quality_row["last_execution_timestamp_et"],
                "largest_execution_gap_minutes": quality_row["largest_execution_gap_minutes"],
                "missing_boundary_flag": bool(missing),
                "missing_boundary_detail": ",".join(missing),
                "thin_boundary_flag": bool(thin),
                "thin_boundary_detail": ",".join(thin),
                "underlying_data_issue": underlying_issue,
                "session_warning": "; ".join(warnings),
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows)
    assert len(result) == result["session_id"].nunique() == 20
    assert (result[[f"swap_count_{name}" for name in ("post", "deep", "premarket")]].sum(axis=1) == result["swap_count_full"]).all()
    assert result["return_decomposition_valid"].all()
    assert result["return_decomposition_valid_last_trade"].all()
    assert result["nvda_next_open"].notna().all() and result["nvda_previous_close"].notna().all()
    result.to_csv(OUTPUT_CSV, index=False)
    return result


def correlation_diagnostics(table: pd.DataFrame) -> dict:
    correlations = {}
    for segment in ("full", "deep", "post", "premarket"):
        x_name = f"token_ret_{segment}"
        sample = table[["market_open_date", x_name, "nvda_gap_return"]].dropna()
        pearson = float(sample[x_name].corr(sample["nvda_gap_return"], method="pearson"))
        spearman = float(sample[x_name].corr(sample["nvda_gap_return"], method="spearman"))
        leave_one_out = []
        for omitted in sample["market_open_date"]:
            reduced = sample.loc[sample["market_open_date"] != omitted]
            leave_one_out.append({"omitted": omitted, "pearson": float(reduced[x_name].corr(reduced["nvda_gap_return"]))})
        correlations[segment] = {
            "n": len(sample),
            "pearson": pearson,
            "spearman": spearman,
            "leave_one_out_pearson_min": min(item["pearson"] for item in leave_one_out),
            "leave_one_out_pearson_max": max(item["pearson"] for item in leave_one_out),
            "largest_leave_one_out_change": max(
                ({"omitted": item["omitted"], "change": abs(item["pearson"] - pearson)} for item in leave_one_out),
                key=lambda item: item["change"],
            ),
        }
    return correlations


def write_outputs(table: pd.DataFrame) -> None:
    correlations = correlation_diagnostics(table)
    return_comparison = {}
    for segment in ("full", "post", "deep", "premarket"):
        primary = table[f"token_ret_{segment}"]
        sensitivity = table[f"token_ret_{segment}_last_trade"]
        difference_bps = (primary - sensitivity).abs() * 10_000
        return_comparison[segment] = {
            "paired_n": int((primary.notna() & sensitivity.notna()).sum()),
            "pearson": float(primary.corr(sensitivity)),
            "median_absolute_difference_bps": float(difference_bps.median()),
            "maximum_absolute_difference_bps": float(difference_bps.max()),
        }
    segment_movement = {
        segment: {
            "median_absolute_log_return": float(table[f"token_ret_{segment}"].abs().median()),
            "sum_absolute_log_return": float(table[f"token_ret_{segment}"].abs().sum()),
        }
        for segment in ("post", "deep", "premarket")
    }
    extremes = table.nlargest(5, "token_ret_full", keep="all")[["market_open_date", "token_ret_full", "nvda_gap_return"]]
    extremes = pd.concat(
        [extremes, table.nsmallest(5, "token_ret_full", keep="all")[["market_open_date", "token_ret_full", "nvda_gap_return"]]]
    ).drop_duplicates("market_open_date")
    activity_top = {
        metric: table.nlargest(3, metric)[["market_open_date", metric, "token_ret_full", "nvda_gap_return"]].to_dict("records")
        for metric in ("swap_count_full", "notional_full", "active_min_share_full")
    }
    activity_associations = {
        metric: {
            "spearman_vs_absolute_token_full_return": float(table[metric].corr(table["token_ret_full"].abs(), method="spearman")),
            "spearman_vs_absolute_nvda_gap": float(table[metric].corr(table["nvda_gap_return"].abs(), method="spearman")),
        }
        for metric in (
            "swap_count_full", "notional_full", "active_min_share_full",
            "swap_count_deep", "notional_deep", "active_min_share_deep",
        )
    }
    diagnostics = {
        "effective_sample_size": 20,
        "missing_primary_boundaries": {name: int(table[f"token_vwap_{name}"].isna().sum()) for name in ("1600", "2000", "0400", "0930")},
        "thin_boundary_rule": "fewer than 5 reconstructable swaps or under 500 USDG notional; warning only, no exclusion",
        "thin_boundary_sessions": table.loc[table["thin_boundary_flag"], ["market_open_date", "thin_boundary_detail"]].to_dict("records"),
        "primary_boundary_depth": {
            name: {
                "minimum_swap_count": int(table[f"boundary_swap_count_{name}"].min()),
                "median_swap_count": float(table[f"boundary_swap_count_{name}"].median()),
                "minimum_notional_usdg": float(table[f"boundary_notional_usdg_{name}"].min()),
                "median_notional_usdg": float(table[f"boundary_notional_usdg_{name}"].median()),
            }
            for name in ("1600", "2000", "0400", "0930")
        },
        "return_decomposition_max_abs_error": float(table["return_decomposition_error"].abs().max()),
        "last_trade_return_decomposition_max_abs_error": float(table["return_decomposition_error_last_trade"].abs().max()),
        "primary_vs_last_trade": return_comparison,
        "segment_movement": segment_movement,
        "return_vs_gap_correlations_exploratory_only": correlations,
        "extreme_full_returns": extremes.to_dict("records"),
        "top_activity_sessions": activity_top,
        "activity_associations_exploratory_only": activity_associations,
    }
    write_json(DIAGNOSTICS_JSON, diagnostics)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    for axis, segment in zip(axes.flat, ("full", "deep", "post", "premarket")):
        x = table[f"token_ret_{segment}"] * 100
        y = table["nvda_gap_return"] * 100
        axis.scatter(x, y, color="#2563eb", alpha=0.8)
        outlier = table.loc[table["market_open_date"].eq("2026-08-27")].iloc[0]
        axis.annotate(
            "Aug 27",
            (outlier[f"token_ret_{segment}"] * 100, outlier["nvda_gap_return"] * 100),
            xytext=(-6, -12),
            textcoords="offset points",
            ha="right",
            fontsize=8,
        )
        axis.axhline(0, color="#999999", linewidth=0.7)
        axis.axvline(0, color="#999999", linewidth=0.7)
        axis.set(title=f"{segment.replace('_', ' ').title()} token return vs NVDA gap", xlabel="Token log return (%)", ylabel="NVDA close-to-open log gap (%)")
    fig.suptitle("NVDA Robinhood Chain measurement pilot — 20 sessions (exploratory only)")
    fig.savefig(SCATTER_PNG, dpi=150)
    plt.close(fig)

    strongest = max(correlations, key=lambda name: abs(correlations[name]["pearson"]))
    largest_segment = max(segment_movement, key=lambda name: segment_movement[name]["median_absolute_log_return"])
    full_compare = return_comparison["full"]
    deep_activity = {
        "swaps": table["swap_count_deep"].median(),
        "notional": table["notional_deep"].median(),
        "share": table["active_min_share_deep"].median(),
    }
    dominance = correlations[strongest]["largest_leave_one_out_change"]
    markdown = f"""# NVDA overnight measurement-design summary

## Scope and interpretation

- **DATA QUALITY:** already validated by Phase 0 (20/20 complete sessions; executed Uniswap V3 swaps only).
- **MEASUREMENT VALIDITY:** assessed here for one economic observation per overnight session.
- **PREDICTIVE INFORMATION CONTENT:** not established; correlations below are descriptive and unstable at N=20.
- **PRICE DISCOVERY:** not established.
- **TRADING ATTENTION MECHANISM:** not established; activity fields are proxies only.
- **CAUSAL EFFECT OF ROBINHOOD CHAIN ON NVDA:** not tested.

Primary token boundaries are quote-notional-weighted executed-trade VWAPs in [16:00,16:05), [19:55,20:00), [03:55,04:00), and [09:25,09:30), America/New_York. Last-trade sensitivity uses the final execution strictly before each boundary. On weekend sessions, DEEP spans Friday 20:00 through Monday 04:00 so the three segments partition the full session.

Underlying target uses raw Nasdaq `Open` and `Close/Last`, not adjusted close. Nasdaq supplied all 20 target opens and all 20 previous regular-session closes, including the first 2026-08-07 close (${table.iloc[0]['nvda_previous_close']:.2f}).

## Answers

**A. Were all four token boundary prices measurable reliably?**  
All 80 primary boundary VWAPs are present: {diagnostics['missing_primary_boundaries']}. Six sessions have a warning-only thin boundary (fewer than 5 swaps or under 500 USDG): {diagnostics['thin_boundary_sessions']}. The maximum return-decomposition error was {diagnostics['return_decomposition_max_abs_error']:.3g}.

**B. Is 5-minute VWAP materially different from last-trade measurement?**  
For the full return, the median absolute difference was {full_compare['median_absolute_difference_bps']:.2f} bp, the maximum was {full_compare['maximum_absolute_difference_bps']:.2f} bp, and paired-return correlation was {full_compare['pearson']:.3f}. This is a sensitivity comparison, not estimator selection.

**C. Which segment contributes most to full overnight token movement?**  
By median absolute log return, **{largest_segment}** is largest. Segment diagnostics: {json.dumps(segment_movement)}.

**D. Does deep-overnight activity appear economically meaningful?**  
The median deep segment contains {deep_activity['swaps']:.0f} swaps, {deep_activity['notional']:,.0f} USDG notional, and {deep_activity['share']:.1%} active-minute coverage. This is meaningful observable pool activity, not evidence of investor attention or price discovery. High activity does not uniformly coincide with large moves: August 27 has the highest full notional and largest move, while August 31 has the highest swap count and deep notional but modest returns. Across the six full/deep activity proxies, all exploratory Spearman associations with absolute token return or absolute NVDA gap have magnitude at most {max(abs(value) for item in activity_associations.values() for value in item.values()):.3f}.

**E. Is the NVDA close-to-open target aligned correctly?**  
Yes for all 20 rows: each target is log(next regular open / previous regular close) on the preserved valid-market-open schedule, using raw Nasdaq prices throughout.

**F. Are there obvious correlations worth testing later?**  
The largest absolute exploratory Pearson correlation is **{strongest} = {correlations[strongest]['pearson']:.3f}** (Spearman {correlations[strongest]['spearman']:.3f}, N={correlations[strongest]['n']}). This is only a candidate for later testing after sample expansion, not evidence of prediction.

**G. Are apparent relationships dominated by one or two sessions?**  
For the strongest correlation, leave-one-out Pearson ranges from {correlations[strongest]['leave_one_out_pearson_min']:.3f} to {correlations[strongest]['leave_one_out_pearson_max']:.3f}; the largest change ({dominance['change']:.3f}) occurs when omitting {dominance['omitted']}. Treat the relationship as small-sample unstable.

**H. Is the design suitable for later multi-token-panel expansion?**  
Yes, as a measurement contract: it produces exactly one row per token session, preserves calendar-aware segments, separates primary and sensitivity prices, and exposes missingness/warnings. It does not establish predictive content and should be frozen before expansion rather than optimized on these 20 rows.

## Artifacts and sources

- Session table: `{OUTPUT_CSV.as_posix()}`
- Diagnostics: `{DIAGNOSTICS_JSON.as_posix()}`
- Scatter figure: `{SCATTER_PNG.as_posix()}`
- Token inputs: `{PHASE0_DIR.as_posix()}/sessions/*/decoded_swaps.csv`
- Nasdaq historical page: https://www.nasdaq.com/market-activity/stocks/nvda/historical
- Nasdaq 2026 market calendar: https://www.nasdaqtrader.com/trader.aspx?id=calendar
"""
    SUMMARY_MD.write_text(markdown, encoding="utf-8")


def main() -> None:
    table = build_table()
    write_outputs(table)
    print(f"Wrote {len(table)} session observations to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
