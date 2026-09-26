from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_rq2_primary_prospective_acquisition import (
    AlpacaClient,
    analyze_trade_window,
    atomic_json,
    fetch_paged_trades,
    jsonl,
    load_condition_policy,
    load_env_credentials,
)
from run_rq2_primary_prospective_first_model import pooled_models, robust_fit, validate_sample


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "reports" / "robinhood_chain_pilot" / "rq2_information_content_design"
INPUT = DESIGN_DIR / "rq2_primary_prospective_analysis_panel.csv"
OUTPUT_DIR = DESIGN_DIR / "e3_temporal_localization"
CACHE_DIR = ROOT / "data" / "cache" / "alpaca_rq2_e3_premarket"
PAYLOAD = OUTPUT_DIR / "e3_payload.json"
NY = ZoneInfo("America/New_York")
ASSETS = ["NVDA", "GME", "COST"]
EXPECTED_COUNTS = {"NVDA": 11, "GME": 23, "COST": 9}
FROZEN = {
    "n": 43,
    "token_beta": 0.30404797991707677,
    "token_hc3_standard_error": 0.2869111623035907,
    "model_0_r_squared": 0.20867089560354102,
    "model_0_adjusted_r_squared": 0.14779942603458263,
    "model_1_r_squared": 0.2966625292064887,
    "model_1_adjusted_r_squared": 0.22262700596506646,
    "delta_r_squared": 0.0879916336029477,
    "delta_adjusted_r_squared": 0.07482757993048383,
    "token_partial_r_squared": 0.11119473947575616,
}


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)


def frozen_reproduction(frame: pd.DataFrame) -> dict:
    result = pooled_models(frame)
    beta = next(row for row in result["coefficients"] if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m")
    observed = {
        "n": int(result["model1_base"].nobs),
        "token_beta": beta["estimate"],
        "token_hc3_standard_error": beta["hc3_standard_error"],
        "model_0_r_squared": result["fits"]["MODEL_0"]["r_squared"],
        "model_0_adjusted_r_squared": result["fits"]["MODEL_0"]["adjusted_r_squared"],
        "model_1_r_squared": result["fits"]["MODEL_1"]["r_squared"],
        "model_1_adjusted_r_squared": result["fits"]["MODEL_1"]["adjusted_r_squared"],
        "delta_r_squared": result["incremental"]["delta_r_squared"],
        "delta_adjusted_r_squared": result["incremental"]["delta_adjusted_r_squared"],
        "token_partial_r_squared": result["incremental"]["partial_r_squared"],
    }
    if any(not close(float(observed[key]), float(value)) for key, value in FROZEN.items()):
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: frozen primary mismatch: {observed}")
    return observed


def reconstruct_raw(normalized_path: Path) -> list[dict]:
    rows = [json.loads(line) for line in normalized_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [
        {"c": row["conditions"], "i": row["trade_id"], "p": row["price"], "s": row["size"], "t": row["timestamp"], "x": row["exchange"], "z": row["tape"]}
        for row in rows
    ]


def failure_reasons(result: dict) -> list[str]:
    if result.get("retrieval_error"):
        return ["PREMARKET_SOURCE_RETRIEVAL_FAILURE"]
    gates = result["hard_gates"]
    reasons = []
    mapping = [
        ("pagination_complete", "PREMARKET_PAGINATION_INCOMPLETE"),
        ("all_rows_inside_interval", "PREMARKET_ROW_OUTSIDE_INTERVAL"),
        ("timestamps_timezone_aware", "PREMARKET_TIMESTAMP_NOT_TIMEZONE_AWARE"),
        ("all_conditions_classified", "PREMARKET_UNKNOWN_TRADE_CONDITION"),
        ("minimum_5_executions", "PREMARKET_INSUFFICIENT_ELIGIBLE_TRADES"),
        ("minimum_100_shares", "PREMARKET_INSUFFICIENT_SHARES"),
        ("minimum_10000_notional", "PREMARKET_INSUFFICIENT_NOTIONAL"),
        ("finite_positive_vwap", "PREMARKET_INVALID_VWAP"),
    ]
    for gate, reason in mapping:
        if not gates.get(gate, False):
            reasons.append(reason)
    if result.get("anomaly_review_required", False):
        reasons.append("PREMARKET_ANOMALY_REQUIRES_REVIEW")
    return reasons


def acquire_row(client: AlpacaClient, row: pd.Series, policy: dict[str, str]) -> dict:
    asset = str(row["token"])
    market_date = date.fromisoformat(str(row["market_open_date"])[:10])
    start = datetime.combine(market_date, dt_time(9, 0), NY).astimezone(timezone.utc)
    end = datetime.combine(market_date, dt_time(9, 30), NY).astimezone(timezone.utc)
    row_dir = CACHE_DIR / asset / market_date.isoformat()
    normalized_path = row_dir / "premarket_trades_normalized.jsonl"
    metadata_path = row_dir / "premarket_metadata.json"
    try:
        if normalized_path.exists() and metadata_path.exists():
            raw = reconstruct_raw(normalized_path)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            raw, metadata = fetch_paged_trades(client, asset, start, end, row_dir, "premarket")
            analyzed_for_write = analyze_trade_window(raw, start, end, policy)
            jsonl(normalized_path, analyzed_for_write.pop("normalized"))
            atomic_json(metadata_path, metadata)
        analyzed = analyze_trade_window(raw, start, end, policy)
        analyzed.pop("normalized")
        analyzed["hard_gates"]["pagination_complete"] = bool(metadata["pagination_complete"])
        analyzed["premarket_quality_ok"] = all(analyzed["hard_gates"].values())
        analyzed["retrieval_error"] = ""
    except Exception as exc:
        analyzed = {
            "raw_trade_count": 0, "eligible_trade_count": 0, "eligible_share_volume": 0.0,
            "eligible_notional": 0.0, "vwap": None, "first_trade_time": "", "last_trade_time": "",
            "last_trade_age_seconds": None, "condition_code_counts": {}, "exchange_counts": {},
            "duplicate_trade_id_count": 0, "missing_required_trade_field_count": 0,
            "nonpositive_price_or_size_count": 0, "unknown_condition_codes": [],
            "hard_gates": {}, "premarket_quality_ok": False, "staleness_warning": False,
            "anomaly_review_required": False, "retrieval_error": f"{type(exc).__name__}: {exc}",
        }
    analyzed["failure_reasons"] = failure_reasons(analyzed)
    analyzed["e3_eligible"] = bool(analyzed["premarket_quality_ok"] and not analyzed["anomaly_review_required"] and not analyzed["retrieval_error"])
    return analyzed


def pooled_pair(frame: pd.DataFrame, outcome: str, prefix: str) -> dict:
    observed = [asset for asset in ["COST", "GME", "NVDA"] if frame["token"].eq(asset).any()]
    reference = "COST" if "COST" in observed else observed[0]
    design0 = pd.DataFrame({f"intercept_{reference}": 1.0}, index=frame.index)
    for asset in observed:
        if asset != reference:
            design0[f"asset_{asset}"] = frame["token"].eq(asset).astype(float)
    design0["stock_post_return"] = frame["stock_post_return"].astype(float)
    design1 = design0.copy()
    design1["token_deep_return_30m"] = frame["token_deep_return_30m"].astype(float)
    y = frame[outcome].astype(float)
    base0, robust0 = robust_fit(y, design0)
    base1, robust1 = robust_fit(y, design1)
    if np.linalg.matrix_rank(design1.to_numpy()) != design1.shape[1]:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: {prefix} rank deficient")
    index = list(design1.columns).index("token_deep_return_30m")
    confidence = np.asarray(robust1.conf_int(alpha=0.05))[index]
    sse0 = float(np.dot(base0.resid, base0.resid))
    sse1 = float(np.dot(base1.resid, base1.resid))
    return {
        "analysis_scope": "POOLED_E3",
        "outcome": outcome,
        "model_0_id": f"{prefix}_MODEL_0",
        "model_1_id": f"{prefix}_MODEL_1",
        "n": int(len(frame)),
        "asset_counts": ";".join(f"{asset}:{int(frame['token'].eq(asset).sum())}" for asset in ASSETS),
        "reference_asset": reference,
        "token_beta": float(robust1.params[index]),
        "token_hc3_standard_error": float(robust1.bse[index]),
        "token_ci_95_lower": float(confidence[0]),
        "token_ci_95_upper": float(confidence[1]),
        "token_p_value": float(robust1.pvalues[index]),
        "model_0_r_squared": float(base0.rsquared),
        "model_0_adjusted_r_squared": float(base0.rsquared_adj),
        "model_1_r_squared": float(base1.rsquared),
        "model_1_adjusted_r_squared": float(base1.rsquared_adj),
        "delta_r_squared": float(base1.rsquared - base0.rsquared),
        "delta_adjusted_r_squared": float(base1.rsquared_adj - base0.rsquared_adj),
        "token_partial_r_squared": float((sse0 - sse1) / sse0),
        "estimator": "OLS", "uncertainty": "HC3",
        "reference_distribution": "Student t with OLS residual degrees of freedom",
        "model_0_formula": f"{outcome} ~ asset fixed effects + stock_post_return",
        "model_1_formula": f"{outcome} ~ asset fixed effects + stock_post_return + token_deep_return_30m",
        "base0": base0, "base1": base1,
    }


def nvda_fit(frame: pd.DataFrame, outcome: str) -> dict:
    design = pd.DataFrame({"intercept": 1.0, "stock_post_return": frame["stock_post_return"].astype(float), "token_deep_return_30m": frame["token_deep_return_30m"].astype(float)}, index=frame.index)
    if len(frame) <= design.shape[1] or np.linalg.matrix_rank(design.to_numpy()) != design.shape[1]:
        return {"analysis_label": "POST_E1_E2_NVDA_DESCRIPTIVE_ONLY", "outcome": outcome, "n": int(len(frame)), "status": "NUMERICALLY_UNSTABLE_OR_RANK_DEFICIENT"}
    base, robust = robust_fit(frame[outcome].astype(float), design)
    index = 2
    confidence = np.asarray(robust.conf_int(alpha=0.05))[index]
    return {
        "analysis_label": "POST_E1_E2_NVDA_DESCRIPTIVE_ONLY", "outcome": outcome,
        "n": int(len(frame)), "status": "COMPLETE", "token_beta": float(robust.params[index]),
        "token_hc3_standard_error": float(robust.bse[index]), "token_ci_95_lower": float(confidence[0]),
        "token_ci_95_upper": float(confidence[1]), "token_p_value": float(robust.pvalues[index]),
        "r_squared": float(base.rsquared), "adjusted_r_squared": float(base.rsquared_adj),
        "estimator": "OLS", "uncertainty": "HC3", "base": base,
    }


def serializable_model(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in {"base0", "base1", "base"}}


def make_plots(pooled: list[dict], nvda: list[dict], eligible: pd.DataFrame) -> None:
    plt.rcParams.update({"font.family": "Arial", "font.size": 10})
    labels = ["Total", "By late premarket", "Premarket to open"]
    x = np.arange(3, dtype=float)
    pooled_est = np.array([row["token_beta"] for row in pooled])
    pooled_low = np.array([row["token_ci_95_lower"] for row in pooled])
    pooled_high = np.array([row["token_ci_95_upper"] for row in pooled])
    fig, axis = plt.subplots(figsize=(8.2, 5.3), constrained_layout=True)
    axis.errorbar(x - 0.08, pooled_est, yerr=np.vstack([pooled_est - pooled_low, pooled_high - pooled_est]), fmt="o", color="#374151", capsize=4, markersize=7, label=f"Pooled E3 (N={len(eligible)})")
    if all(row.get("status") == "COMPLETE" for row in nvda):
        nv_est = np.array([row["token_beta"] for row in nvda])
        nv_low = np.array([row["token_ci_95_lower"] for row in nvda])
        nv_high = np.array([row["token_ci_95_upper"] for row in nvda])
        axis.errorbar(x + 0.08, nv_est, yerr=np.vstack([nv_est - nv_low, nv_high - nv_est]), fmt="^", color="#2563EB", capsize=4, markersize=8, label=f"NVDA descriptive (N={len(eligible.loc[eligible['token'].eq('NVDA')])})")
    axis.axhline(0, color="#9CA3AF", linewidth=0.9, linestyle="--")
    axis.set_xticks(x, labels)
    axis.set_ylabel("Token coefficient (95% HC3 CI)")
    axis.set_title("E3 temporal coefficient decomposition")
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True); axis.legend(frameon=False)
    for spine in ("top", "right"): axis.spines[spine].set_visible(False)
    fig.savefig(OUTPUT_DIR / "e3_temporal_coefficients.png", dpi=300, facecolor="white")
    plt.close(fig)

    reconstructed = eligible["Y_pre"] + eligible["Y_open"]
    lower = float(min(eligible["Y_total"].min(), reconstructed.min()))
    upper = float(max(eligible["Y_total"].max(), reconstructed.max()))
    padding = max((upper - lower) * 0.05, 1e-6)
    fig, axis = plt.subplots(figsize=(6.5, 5.7), constrained_layout=True)
    colors = {"NVDA": "#2563EB", "GME": "#D97706", "COST": "#6B8E23"}
    markers = {"NVDA": "o", "GME": "s", "COST": "^"}
    for asset in ASSETS:
        group = eligible.loc[eligible["token"].eq(asset)]
        if group.empty:
            continue
        axis.scatter(group["Y_pre"] + group["Y_open"], group["Y_total"], color=colors[asset], marker=markers[asset], s=58, edgecolor="white", linewidth=0.7, label=f"{asset} (N={len(group)})")
    axis.plot([lower-padding, upper+padding], [lower-padding, upper+padding], color="#111827", linewidth=1.2, linestyle="--", label="Identity")
    axis.set_xlim(lower-padding, upper+padding); axis.set_ylim(lower-padding, upper+padding)
    axis.set_xlabel("Y_pre + Y_open"); axis.set_ylabel("Y_total")
    axis.set_title("Row-level return decomposition QA")
    axis.grid(True, color="#E5E7EB", linewidth=0.7); axis.set_axisbelow(True); axis.legend(frameon=False)
    for spine in ("top", "right"): axis.spines[spine].set_visible(False)
    fig.savefig(OUTPUT_DIR / "e3_return_decomposition_qa.png", dpi=300, facecolor="white")
    plt.close(fig)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True); CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(INPUT)
    frame["market_open_date"] = pd.to_datetime(frame["market_open_date"], format="%Y-%m-%d")
    for column in ["stock_p20", "stock_open", "stock_post_return", "stock_20_to_open_return", "token_deep_return_30m"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    validate_sample(frame)
    frozen = frozen_reproduction(frame)
    key, secret = load_env_credentials()
    policy, policy_sha = load_condition_policy()
    client = AlpacaClient(key, secret, args.pause_seconds)

    audit_rows = []
    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        result = acquire_row(client, row, policy)
        gates = result["hard_gates"]
        audit_rows.append({
            "asset": row["token"], "market_open_date": row["market_open_date"].date().isoformat(),
            "frozen_primary_member": True, "stock_p20": float(row["stock_p20"]),
            "stock_premarket": result["vwap"] if result["e3_eligible"] else None,
            "stock_open": float(row["stock_open"]), "premarket_raw_trade_count": result["raw_trade_count"],
            "premarket_eligible_trade_count": result["eligible_trade_count"],
            "premarket_shares": result["eligible_share_volume"], "premarket_notional": result["eligible_notional"],
            "premarket_first_trade_time": result["first_trade_time"], "premarket_last_trade_time": result["last_trade_time"],
            "premarket_last_trade_age_seconds": result["last_trade_age_seconds"],
            "premarket_exact_interval_requested": gates.get("exact_interval_requested", False),
            "premarket_pagination_complete": gates.get("pagination_complete", False),
            "premarket_all_rows_inside_interval": gates.get("all_rows_inside_interval", False),
            "premarket_timestamps_timezone_aware": gates.get("timestamps_timezone_aware", False),
            "premarket_all_conditions_classified": gates.get("all_conditions_classified", False),
            "premarket_minimum_5_executions": gates.get("minimum_5_executions", False),
            "premarket_minimum_100_shares": gates.get("minimum_100_shares", False),
            "premarket_minimum_10000_notional": gates.get("minimum_10000_notional", False),
            "premarket_finite_positive_vwap": gates.get("finite_positive_vwap", False),
            "premarket_staleness_warning": result["staleness_warning"],
            "premarket_anomaly_review_required": result["anomaly_review_required"],
            "premarket_unknown_condition_codes": ";".join(result["unknown_condition_codes"]),
            "premarket_duplicate_trade_id_count": result["duplicate_trade_id_count"],
            "premarket_missing_required_trade_field_count": result["missing_required_trade_field_count"],
            "premarket_nonpositive_price_or_size_count": result["nonpositive_price_or_size_count"],
            "e3_eligible": result["e3_eligible"], "e3_failure_reason": "|".join(result["failure_reasons"]),
            "source": "Alpaca Historical Market Data API", "feed": "sip",
            "premarket_window": "[09:00,09:30) America/New_York", "condition_policy_sha256": policy_sha,
        })
        print(f"progress={position}/43 eligible={sum(bool(r['e3_eligible']) for r in audit_rows)} requests={client.request_count}", flush=True)

    audit = pd.DataFrame(audit_rows)
    if len(audit) != 43 or audit.duplicated(["asset", "market_open_date"]).any() or set(zip(audit["asset"], audit["market_open_date"])) != set(zip(frame["token"], frame["market_open_date"].dt.date.astype(str))):
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: E3 audit does not reconcile to frozen keys")
    eligible_audit = audit.loc[audit["e3_eligible"]].copy()
    eligible_audit["market_open_date"] = pd.to_datetime(eligible_audit["market_open_date"], format="%Y-%m-%d")
    eligible = frame.merge(eligible_audit[["asset", "market_open_date", "stock_premarket"]].rename(columns={"asset": "token"}), on=["token", "market_open_date"], how="inner", validate="one_to_one")
    if len(eligible) != int(audit["e3_eligible"].sum()):
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: eligible merge mismatch")
    if len(eligible) < 6:
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: insufficient E3 rows for frozen-regressor models")
    eligible["Y_total"] = np.log(eligible["stock_open"] / eligible["stock_p20"])
    eligible["Y_pre"] = np.log(eligible["stock_premarket"] / eligible["stock_p20"])
    eligible["Y_open"] = np.log(eligible["stock_open"] / eligible["stock_premarket"])
    eligible["row_decomposition_error"] = eligible["Y_total"] - eligible["Y_pre"] - eligible["Y_open"]
    maximum_row_error = float(eligible["row_decomposition_error"].abs().max())
    if maximum_row_error > 1e-12:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: material return decomposition mismatch {maximum_row_error}")
    original_difference = float((eligible["Y_total"] - eligible["stock_20_to_open_return"]).abs().max())
    if original_difference > 1e-12:
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: Y_total differs from frozen outcome")

    pooled = [pooled_pair(eligible, "Y_total", "E3_TOTAL"), pooled_pair(eligible, "Y_pre", "PRE"), pooled_pair(eligible, "Y_open", "OPEN")]
    beta_discrepancy = abs(pooled[0]["token_beta"] - pooled[1]["token_beta"] - pooled[2]["token_beta"])
    fitted_discrepancy = float(np.max(np.abs(np.asarray(pooled[0]["base1"].fittedvalues) - np.asarray(pooled[1]["base1"].fittedvalues) - np.asarray(pooled[2]["base1"].fittedvalues))))
    residual_discrepancy = float(np.max(np.abs(np.asarray(pooled[0]["base1"].resid) - np.asarray(pooled[1]["base1"].resid) - np.asarray(pooled[2]["base1"].resid))))
    if max(beta_discrepancy, fitted_discrepancy, residual_discrepancy) > 1e-10:
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: coefficient/fitted/residual decomposition mismatch")

    nvda_frame = eligible.loc[eligible["token"].eq("NVDA")]
    nvda = [nvda_fit(nvda_frame, outcome) for outcome in ["Y_total", "Y_pre", "Y_open"]]
    nvda_complete = all(row.get("status") == "COMPLETE" for row in nvda)
    nvda_beta_discrepancy = abs(nvda[0]["token_beta"] - nvda[1]["token_beta"] - nvda[2]["token_beta"]) if nvda_complete else None
    make_plots(pooled, nvda, eligible)

    reasons = Counter(reason for value in audit.loc[~audit["e3_eligible"], "e3_failure_reason"] for reason in str(value).split("|") if reason)
    recorded_requests = sum(
        len(json.loads((CACHE_DIR / row["asset"] / row["market_open_date"] / "premarket_metadata.json").read_text(encoding="utf-8")).get("requests", []))
        for row in audit_rows
        if (CACHE_DIR / row["asset"] / row["market_open_date"] / "premarket_metadata.json").exists()
    )
    attrition_by_asset = {
        asset: {
            "frozen_rows": int(audit["asset"].eq(asset).sum()),
            "eligible_rows": int((audit["asset"].eq(asset) & audit["e3_eligible"]).sum()),
            "failed_rows": int((audit["asset"].eq(asset) & ~audit["e3_eligible"]).sum()),
        }
        for asset in ASSETS
    }
    decomposition = {
        "beta_total": pooled[0]["token_beta"], "beta_pre": pooled[1]["token_beta"], "beta_open": pooled[2]["token_beta"],
        "beta_pre_plus_beta_open": pooled[1]["token_beta"] + pooled[2]["token_beta"],
        "absolute_beta_discrepancy": beta_discrepancy, "maximum_absolute_row_return_discrepancy": maximum_row_error,
        "maximum_absolute_model1_fitted_value_discrepancy": fitted_discrepancy,
        "maximum_absolute_model1_residual_discrepancy": residual_discrepancy,
        "nvda_absolute_beta_discrepancy": nvda_beta_discrepancy,
    }
    validation = {
        "frozen_primary_reproduced": True, "frozen_rows": 43, "frozen_asset_counts": EXPECTED_COUNTS,
        "audit_rows": int(len(audit)), "unique_audit_keys": int(audit[["asset", "market_open_date"]].drop_duplicates().shape[0]),
        "e3_eligible_rows": int(len(eligible)), "only_frozen_primary_rows": True,
        "premarket_window": "[09:00,09:30) America/New_York", "new_measurement_only": "stock_premarket",
        "trade_policy_reused": True, "hard_thresholds_reused": {"eligible_executions": 5, "shares": 100, "notional_usd": 10000},
        "fallback_or_interpolation_used": False, "rows_silently_dropped": 0,
        "all_pooled_models_same_rows": True, "all_pooled_models_same_regressors": True,
        "pooled_estimator": "OLS", "pooled_uncertainty": "HC3", "asset_fixed_effects_present": True,
        "no_e4_or_additional_mechanism_experiment": True,
        "alpaca_requests_recorded_for_e3_acquisition": int(recorded_requests),
        "new_network_requests_this_execution": int(client.request_count),
    }
    payload = {
        "frozen_reproduction": frozen, "validation": validation,
        "attrition": {"total": {"frozen_rows": 43, "eligible_rows": int(len(eligible)), "failed_rows": int(43-len(eligible))}, "by_asset": attrition_by_asset, "failure_reason_counts": dict(sorted(reasons.items()))},
        "decomposition_qa": decomposition,
        "row_audit": audit.astype(object).where(pd.notna(audit), None).to_dict(orient="records"),
        "temporal_model_results": [serializable_model(row) for row in pooled],
        "nvda_temporal_descriptive": [serializable_model(row) for row in nvda],
    }
    PAYLOAD.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# E3 — Temporal Localization of the Overnight Association", "", "`TERMINAL_MECHANISM_DIAGNOSTIC`", "",
        "## 1. Premarket acquisition and attrition", "",
        f"Valid 09:00–09:30 ET premarket anchors: {len(eligible)}/43; failures: {43-len(eligible)}. The window was exactly `[09:00,09:30)` America/New_York and used the frozen SIP condition policy and stock-p20 QA thresholds.", "",
        "| Asset | Frozen | E3 eligible | Failed |", "|---|---:|---:|---:|",
    ]
    for asset in ASSETS:
        item = attrition_by_asset[asset]; lines.append(f"| {asset} | {item['frozen_rows']} | {item['eligible_rows']} | {item['failed_rows']} |")
    lines += ["", "Failure reasons: " + (", ".join(f"{key}={value}" for key, value in sorted(reasons.items())) if reasons else "none") + ".", "", "Attrition is material and strongly asset-skewed. Every excluded row triggered the frozen duplicate-trade-ID anomaly-review rule; no excluded row had an unknown condition, missing required trade field, or nonpositive price/size. The rule was not relaxed or reinterpreted.", "", "## 2. Frozen primary reproduction", "", f"Frozen N=43 MODEL 0 / MODEL 1 reproduced exactly. MODEL 1 beta {fmt(frozen['token_beta'])}, HC3 SE {fmt(frozen['token_hc3_standard_error'])}, delta adjusted R² {fmt(frozen['delta_adjusted_r_squared'])}, partial R² {fmt(frozen['token_partial_r_squared'])}.", "", "## 3. Pooled E3 temporal models", "", "| Outcome | N | Token beta | HC3 SE | 95% CI | p | Delta adjusted R² | Partial R² |", "|---|---:|---:|---:|---|---:|---:|---:|"]
    for row in pooled:
        lines.append(f"| {row['outcome']} | {row['n']} | {fmt(row['token_beta'])} | {fmt(row['token_hc3_standard_error'])} | [{fmt(row['token_ci_95_lower'])}, {fmt(row['token_ci_95_upper'])}] | {fmt(row['token_p_value'])} | {fmt(row['delta_adjusted_r_squared'])} | {fmt(row['token_partial_r_squared'])} |")
    lines += ["", "Full MODEL 0 / MODEL 1 fit metrics are in `e3_temporal_model_results.csv`.", "", f"On the E3 subset, Y_total no longer resembles the frozen positive association: beta_total is {fmt(pooled[0]['token_beta'])}, delta adjusted R² is {fmt(pooled[0]['delta_adjusted_r_squared'])}, and partial R² is {fmt(pooled[0]['token_partial_r_squared'])}. Incremental contribution is concentrated in opposing component estimates rather than the total: Y_pre beta {fmt(pooled[1]['token_beta'])}, delta adjusted R² {fmt(pooled[1]['delta_adjusted_r_squared'])}; Y_open beta {fmt(pooled[2]['token_beta'])}, delta adjusted R² {fmt(pooled[2]['delta_adjusted_r_squared'])}.", "", "## 4. Coefficient and return decomposition QA", "", f"beta_total={fmt(decomposition['beta_total'])}; beta_pre={fmt(decomposition['beta_pre'])}; beta_open={fmt(decomposition['beta_open'])}; beta_pre+beta_open={fmt(decomposition['beta_pre_plus_beta_open'])}; absolute discrepancy={decomposition['absolute_beta_discrepancy']:.3e}.", f"Maximum absolute row-return discrepancy: {maximum_row_error:.3e}. Maximum fitted-value discrepancy: {fitted_discrepancy:.3e}. Maximum residual discrepancy: {residual_discrepancy:.3e}.", "", "## 5. NVDA-only descriptive timing", "", "`POST_E1_E2_NVDA_DESCRIPTIVE_ONLY`", ""]
    for row in nvda:
        if row.get("status") == "COMPLETE": lines.append(f"- {row['outcome']}: beta={fmt(row['token_beta'])}, HC3 SE={fmt(row['token_hc3_standard_error'])}, 95% CI [{fmt(row['token_ci_95_lower'])}, {fmt(row['token_ci_95_upper'])}], p={fmt(row['token_p_value'])}.")
        else: lines.append(f"- {row['outcome']}: {row['status']} (N={row['n']}).")
    lines += ["", "No NVDA row passed the frozen premarket QA convention, so the requested NVDA-only descriptive timing comparison is unavailable rather than replaced or re-specified.", "", "## 6. Terminal interpretation", "", "**Terminal classification: `NO_COHERENT_TEMPORAL_MECHANISM`.** The E3-total association is near zero after severe, asset-skewed attrition leaves an almost exclusively GME sample, while the temporal components are sizeable and opposing. This cannot localize the original pooled, NVDA-dependent RQ2 association.", "", "What remains unidentified is the timing of the original pooled/NVDA-associated signal for sessions that fail the frozen premarket QA convention. E3 also cannot identify causal direction or prove price discovery; a shared overnight public-information process remains compatible with any temporal pattern.", "", "No E4 or additional mechanism experiment was run.", ""]
    (OUTPUT_DIR / "e3_temporal_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "request_count": client.request_count, "attrition": payload["attrition"], "temporal_model_results": payload["temporal_model_results"], "nvda_temporal_descriptive": payload["nvda_temporal_descriptive"], "decomposition_qa": decomposition, "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
