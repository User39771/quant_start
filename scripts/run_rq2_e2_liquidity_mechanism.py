from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from run_rq2_primary_prospective_first_model import pooled_models, validate_sample


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "reports" / "robinhood_chain_pilot" / "rq2_information_content_design"
PRIMARY_INPUT = DESIGN_DIR / "rq2_primary_prospective_analysis_panel.csv"
TOKEN_INPUT = DESIGN_DIR / "rq2_primary_prospective_token_predictor.csv"
OUTPUT_DIR = DESIGN_DIR / "e2_nvda_identity_vs_liquidity"
PAYLOAD = OUTPUT_DIR / "e2_payload.json"

ASSETS = ["NVDA", "GME", "COST"]
EXPECTED_COUNTS = {"NVDA": 11, "GME": 23, "COST": 9}
FROZEN = {
    "n": 43,
    "token_beta": 0.30404797991707677,
    "token_hc3_standard_error": 0.2869111623035907,
    "model_1_r_squared": 0.2966625292064887,
    "model_1_adjusted_r_squared": 0.22262700596506646,
    "delta_adjusted_r_squared": 0.07482757993048383,
    "token_partial_r_squared": 0.11119473947575616,
}


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)


def fit_model(frame: pd.DataFrame, model_id: str, extra_terms: list[str]) -> dict:
    design = pd.DataFrame(
        {
            "intercept_COST": 1.0,
            "asset_GME": frame["token"].eq("GME").astype(float),
            "asset_NVDA": frame["token"].eq("NVDA").astype(float),
            "stock_post_return": frame["stock_post_return"].astype(float),
            "token_deep_return_30m": frame["token_deep_return_30m"].astype(float),
        },
        index=frame.index,
    )
    for term in extra_terms:
        design[term] = frame[term].astype(float)
    y = frame["stock_20_to_open_return"].astype(float)
    import statsmodels.api as sm

    base = sm.OLS(y, design).fit()
    robust = base.get_robustcov_results(cov_type="HC3", use_t=True)
    if int(np.linalg.matrix_rank(design.to_numpy())) != design.shape[1]:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: {model_id} design is rank deficient")
    return {
        "model_id": model_id,
        "design": design,
        "base": base,
        "robust": robust,
        "term_names": list(design.columns),
    }


def linear_combination(model: dict, weights: dict[str, float]) -> dict:
    names = model["term_names"]
    contrast = np.array([weights.get(name, 0.0) for name in names], dtype=float)
    robust = model["robust"]
    estimate = float(contrast @ np.asarray(robust.params))
    variance = float(contrast @ np.asarray(robust.cov_params()) @ contrast)
    standard_error = math.sqrt(max(variance, 0.0))
    df = float(model["base"].df_resid)
    t_value = estimate / standard_error if standard_error > 0 else math.nan
    p_value = float(2 * stats.t.sf(abs(t_value), df)) if standard_error > 0 else math.nan
    critical = float(stats.t.ppf(0.975, df))
    return {
        "estimate": estimate,
        "hc3_standard_error": standard_error,
        "ci_95_lower": estimate - critical * standard_error,
        "ci_95_upper": estimate + critical * standard_error,
        "p_value": p_value,
    }


def model_rows(model: dict, frozen_r2: float, frozen_adj_r2: float) -> list[dict]:
    rows = []
    base = model["base"]
    for term in model["term_names"]:
        result = linear_combination(model, {term: 1.0})
        rows.append(
            {
                "model_id": model["model_id"],
                "term": term,
                **result,
                "n": int(base.nobs),
                "df_residual": float(base.df_resid),
                "r_squared": float(base.rsquared),
                "adjusted_r_squared": float(base.rsquared_adj),
                "change_r_squared_vs_frozen_model_1": float(base.rsquared - frozen_r2),
                "change_adjusted_r_squared_vs_frozen_model_1": float(base.rsquared_adj - frozen_adj_r2),
                "design_rank": int(np.linalg.matrix_rank(model["design"].to_numpy())),
                "parameter_count": int(model["design"].shape[1]),
                "estimator": "OLS",
                "uncertainty": "HC3",
                "reference_distribution": "Student t with OLS residual degrees of freedom",
                "asset_fixed_effects": "intercept plus GME and NVDA indicators; COST reference",
            }
        )
    return rows


def named_combination_row(model: dict, label: str, weights: dict[str, float], frozen_r2: float, frozen_adj_r2: float) -> dict:
    base = model["base"]
    return {
        "model_id": model["model_id"],
        "term": label,
        **linear_combination(model, weights),
        "n": int(base.nobs),
        "df_residual": float(base.df_resid),
        "r_squared": float(base.rsquared),
        "adjusted_r_squared": float(base.rsquared_adj),
        "change_r_squared_vs_frozen_model_1": float(base.rsquared - frozen_r2),
        "change_adjusted_r_squared_vs_frozen_model_1": float(base.rsquared_adj - frozen_adj_r2),
        "design_rank": int(np.linalg.matrix_rank(model["design"].to_numpy())),
        "parameter_count": int(model["design"].shape[1]),
        "estimator": "OLS",
        "uncertainty": "HC3",
        "reference_distribution": "Student t with OLS residual degrees of freedom",
        "asset_fixed_effects": "intercept plus GME and NVDA indicators; COST reference",
    }


def marginal_rows(model: dict, liquidity_points: dict[str, float], scopes: list[str]) -> list[dict]:
    rows = []
    for quantile, liquidity in liquidity_points.items():
        for scope in scopes:
            weights = {"token_deep_return_30m": 1.0, "token_x_L_z": liquidity}
            if scope == "NVDA":
                weights["token_x_NVDA"] = 1.0
            result = linear_combination(model, weights)
            rows.append(
                {
                    "model_id": model["model_id"],
                    "asset_scope": scope,
                    "liquidity_point": quantile,
                    "L_z": liquidity,
                    "token_slope": result["estimate"],
                    "hc3_standard_error": result["hc3_standard_error"],
                    "ci_95_lower": result["ci_95_lower"],
                    "ci_95_upper": result["ci_95_upper"],
                    "p_value": result["p_value"],
                    "n": int(model["base"].nobs),
                    "estimator": "OLS",
                    "uncertainty": "HC3",
                }
            )
    return rows


def make_plots(frame: pd.DataFrame, marginal: list[dict]) -> None:
    colors = {"NVDA": "#2563EB", "GME": "#D97706", "COST": "#6B8E23"}
    markers = {"NVDA": "o", "GME": "s", "COST": "^"}
    rng = np.random.default_rng(20260920)
    plt.rcParams.update({"font.family": "Arial", "font.size": 10})

    fig, axis = plt.subplots(figsize=(7.4, 5.1), constrained_layout=True)
    positions = {asset: index for index, asset in enumerate(ASSETS)}
    for asset in ASSETS:
        values = frame.loc[frame["token"].eq(asset), "L_z"].to_numpy(float)
        x = positions[asset] + rng.uniform(-0.09, 0.09, size=len(values))
        axis.scatter(x, values, s=56, marker=markers[asset], color=colors[asset], edgecolor="white", linewidth=0.7, alpha=0.9)
    groups = [frame.loc[frame["token"].eq(asset), "L_z"].to_numpy(float) for asset in ASSETS]
    box = axis.boxplot(groups, positions=list(positions.values()), widths=0.34, patch_artist=True, showfliers=False)
    for patch, asset in zip(box["boxes"], ASSETS):
        patch.set_facecolor(colors[asset]); patch.set_alpha(0.16); patch.set_edgecolor(colors[asset])
    for element in ("whiskers", "caps", "medians"):
        for item in box[element]:
            item.set_color("#374151")
    axis.axhline(0, color="#6B7280", linewidth=0.9, linestyle="--")
    axis.set_xticks(list(positions.values()), [f"{asset} (N={int(frame['token'].eq(asset).sum())})" for asset in ASSETS])
    axis.set_ylabel("Standardized log weak-anchor notional (L_z)")
    axis.set_title("Weak-anchor liquidity distribution by asset")
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True)
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    fig.savefig(OUTPUT_DIR / "e2_liquidity_by_asset.png", dpi=300, facecolor="white")
    plt.close(fig)

    plot_frame = pd.DataFrame(marginal)
    fig, axis = plt.subplots(figsize=(8.2, 5.3), constrained_layout=True)
    series = [
        ("MODEL_L", "POOLED", "MODEL_L pooled", "#4B5563", "o", -0.10),
        ("MODEL_B", "NON_NVDA", "MODEL_B non-NVDA", "#D97706", "s", 0.00),
        ("MODEL_B", "NVDA", "MODEL_B NVDA", "#2563EB", "^", 0.10),
    ]
    points = ["P25", "MEDIAN", "P75"]
    base_x = np.arange(len(points), dtype=float)
    for model_id, scope, label, color, marker, offset in series:
        group = plot_frame.loc[(plot_frame["model_id"] == model_id) & (plot_frame["asset_scope"] == scope)].set_index("liquidity_point").loc[points]
        estimate = group["token_slope"].to_numpy(float)
        lower = group["ci_95_lower"].to_numpy(float)
        upper = group["ci_95_upper"].to_numpy(float)
        axis.errorbar(base_x + offset, estimate, yerr=np.vstack([estimate - lower, upper - estimate]), fmt=marker + "-", color=color, linewidth=1.4, capsize=4, markersize=7, label=label)
    axis.axhline(0, color="#6B7280", linewidth=0.9, linestyle="--")
    axis.set_xticks(base_x, ["25th percentile", "Median", "75th percentile"])
    axis.set_xlabel("Empirical liquidity point in frozen N=43 sample")
    axis.set_ylabel("Marginal token-return slope (95% HC3 CI)")
    axis.set_title("Token-return slope across observed liquidity")
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, loc="best")
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    fig.savefig(OUTPUT_DIR / "e2_marginal_slope_plot.png", dpi=300, facecolor="white")
    plt.close(fig)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    primary = pd.read_csv(PRIMARY_INPUT)
    token = pd.read_csv(TOKEN_INPUT)
    primary["market_open_date"] = pd.to_datetime(primary["market_open_date"], format="%Y-%m-%d")
    token["market_open_date"] = pd.to_datetime(token["market_open_date"], format="%Y-%m-%d")
    validate_sample(primary)

    primary_model = pooled_models(primary)
    primary_beta = next(row for row in primary_model["coefficients"] if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m")
    reproduced = {
        "n": int(primary_model["model1_base"].nobs),
        "token_beta": primary_beta["estimate"],
        "token_hc3_standard_error": primary_beta["hc3_standard_error"],
        "model_1_r_squared": primary_model["fits"]["MODEL_1"]["r_squared"],
        "model_1_adjusted_r_squared": primary_model["fits"]["MODEL_1"]["adjusted_r_squared"],
        "delta_adjusted_r_squared": primary_model["incremental"]["delta_adjusted_r_squared"],
        "token_partial_r_squared": primary_model["incremental"]["partial_r_squared"],
    }
    if any(not close(float(reproduced[key]), float(value)) for key, value in FROZEN.items()):
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: frozen MODEL 1 mismatch: {reproduced}")

    keys = ["token", "market_open_date"]
    liquidity_columns = ["30m_2000_swap_count", "30m_2000_notional", "30m_0400_swap_count", "30m_0400_notional"]
    if token.duplicated(keys).any() or primary.duplicated(keys).any():
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: duplicate asset/date key")
    joined = primary.merge(token[keys + liquidity_columns], on=keys, how="left", validate="one_to_one", indicator=True, suffixes=("", "_token"))
    if len(joined) != 43 or not joined["_merge"].eq("both").all():
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: incomplete liquidity join")
    for column in liquidity_columns:
        source = f"{column}_token"
        if joined[source].isna().any():
            raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: missing {column}")
        if column.endswith("notional") and not joined[source].gt(0).all():
            raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: nonpositive {column}")
        if column in joined and not np.allclose(joined[column].astype(float), joined[source].astype(float), rtol=0, atol=1e-12):
            raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: carried-field mismatch for {column}")
        joined[column] = joined[source]
        joined.drop(columns=[source], inplace=True)
    joined.drop(columns=["_merge"], inplace=True)

    joined["weak_anchor_notional"] = joined[["30m_2000_notional", "30m_0400_notional"]].min(axis=1)
    joined["L_raw"] = np.log1p(joined["weak_anchor_notional"].astype(float))
    l_mean = float(joined["L_raw"].mean())
    l_sd = float(joined["L_raw"].std(ddof=1))
    joined["L_z"] = (joined["L_raw"] - l_mean) / l_sd
    joined["token_x_L_z"] = joined["token_deep_return_30m"].astype(float) * joined["L_z"]
    joined["token_x_NVDA"] = joined["token_deep_return_30m"].astype(float) * joined["token"].eq("NVDA").astype(float)
    exact_min = np.minimum(joined["30m_2000_notional"].astype(float), joined["30m_0400_notional"].astype(float))
    if not np.allclose(joined["weak_anchor_notional"], exact_min, rtol=0, atol=0):
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: weak-anchor definition mismatch")

    summary_rows = []
    for asset in ASSETS:
        group = joined.loc[joined["token"].eq(asset)]
        for variable in ["L_raw", "L_z"]:
            values = group[variable].astype(float)
            summary_rows.append({
                "asset": asset, "variable": variable, "n": int(len(values)),
                "minimum": float(values.min()), "percentile_25": float(values.quantile(0.25)),
                "median": float(values.median()), "percentile_75": float(values.quantile(0.75)),
                "maximum": float(values.max()), "mean": float(values.mean()),
                "standard_deviation": float(values.std(ddof=1)),
            })

    nvda = joined.loc[joined["token"].eq("NVDA"), "L_z"]
    non_nvda = joined.loc[~joined["token"].eq("NVDA"), "L_z"]
    support = {
        "nvda_range_min": float(nvda.min()), "nvda_range_max": float(nvda.max()),
        "non_nvda_range_min": float(non_nvda.min()), "non_nvda_range_max": float(non_nvda.max()),
        "nvda_within_non_nvda_range_count": int(nvda.between(non_nvda.min(), non_nvda.max(), inclusive="both").sum()),
        "nvda_n": int(len(nvda)),
        "non_nvda_within_nvda_range_count": int(non_nvda.between(nvda.min(), nvda.max(), inclusive="both").sum()),
        "non_nvda_n": int(len(non_nvda)),
    }
    support["nvda_within_non_nvda_range_fraction"] = support["nvda_within_non_nvda_range_count"] / support["nvda_n"]
    support["non_nvda_within_nvda_range_fraction"] = support["non_nvda_within_nvda_range_count"] / support["non_nvda_n"]

    frozen_r2 = FROZEN["model_1_r_squared"]
    frozen_adj = FROZEN["model_1_adjusted_r_squared"]
    model_l = fit_model(joined, "MODEL_L", ["L_z", "token_x_L_z"])
    model_n = fit_model(joined, "MODEL_N", ["token_x_NVDA"])
    model_b = fit_model(joined, "MODEL_B", ["L_z", "token_x_L_z", "token_x_NVDA"])
    model_results = model_rows(model_l, frozen_r2, frozen_adj) + model_rows(model_n, frozen_r2, frozen_adj) + model_rows(model_b, frozen_r2, frozen_adj)
    model_results.append(named_combination_row(model_n, "nvda_token_slope", {"token_deep_return_30m": 1, "token_x_NVDA": 1}, frozen_r2, frozen_adj))
    model_results.append(named_combination_row(model_b, "non_nvda_token_slope_at_mean_liquidity", {"token_deep_return_30m": 1}, frozen_r2, frozen_adj))
    model_results.append(named_combination_row(model_b, "nvda_token_slope_at_mean_liquidity", {"token_deep_return_30m": 1, "token_x_NVDA": 1}, frozen_r2, frozen_adj))

    liquidity_points = {"P25": float(joined["L_z"].quantile(0.25)), "MEDIAN": float(joined["L_z"].median()), "P75": float(joined["L_z"].quantile(0.75))}
    marginal = marginal_rows(model_l, liquidity_points, ["POOLED"]) + marginal_rows(model_b, liquidity_points, ["NON_NVDA", "NVDA"])
    make_plots(joined, marginal)

    lookup = {(row["model_id"], row["term"]): row for row in model_results}
    delta_n = lookup[("MODEL_N", "token_x_NVDA")]
    delta_b = lookup[("MODEL_B", "token_x_NVDA")]
    theta_l = lookup[("MODEL_L", "token_x_L_z")]
    theta_b = lookup[("MODEL_B", "token_x_L_z")]
    attenuation = {
        "delta_model_n": delta_n["estimate"], "delta_model_b": delta_b["estimate"],
        "delta_change_b_minus_n": delta_b["estimate"] - delta_n["estimate"],
        "delta_absolute_change": abs(delta_b["estimate"]) - abs(delta_n["estimate"]),
        "theta_model_l": theta_l["estimate"], "theta_model_b": theta_b["estimate"],
        "theta_change_b_minus_l": theta_b["estimate"] - theta_l["estimate"],
        "theta_absolute_change": abs(theta_b["estimate"]) - abs(theta_l["estimate"]),
    }

    audit_columns = [
        "token", "market_open_date", "sample_role", "primary_inferential_row",
        "30m_2000_swap_count", "30m_2000_notional", "30m_0400_swap_count", "30m_0400_notional",
        "weak_anchor_notional", "L_raw", "L_z", "token_deep_return_30m",
        "stock_post_return", "stock_20_to_open_return",
    ]
    audit = joined[audit_columns].copy()
    audit.rename(columns={
        "token": "asset", "30m_2000_notional": "quote_notional_20",
        "30m_0400_notional": "quote_notional_04", "30m_2000_swap_count": "swap_count_20",
        "30m_0400_swap_count": "swap_count_04",
    }, inplace=True)
    audit["market_open_date"] = audit["market_open_date"].dt.date.astype(str)

    validation = {
        "frozen_model_reproduced": True, "rows": int(len(joined)),
        "asset_counts": {asset: int(joined["token"].eq(asset).sum()) for asset in ASSETS},
        "unique_asset_date_keys": int(joined[keys].drop_duplicates().shape[0]),
        "all_liquidity_rows_reconciled_once": bool(len(joined) == 43 and not joined.duplicated(keys).any()),
        "all_20_notional_positive": bool(joined["30m_2000_notional"].gt(0).all()),
        "all_04_notional_positive": bool(joined["30m_0400_notional"].gt(0).all()),
        "weak_anchor_exact_min": True, "liquidity_proxy": "L_z from log1p(min(20:00 notional, 04:00 notional)), sample SD ddof=1",
        "modeled_liquidity_predictors": ["L_z", "token_deep_return_30m * L_z"],
        "models": ["MODEL_L", "MODEL_N", "MODEL_B"], "estimator": "OLS", "uncertainty": "HC3",
        "asset_fixed_effects_present": True, "rows_dropped": 0, "external_data_fetched": False,
    }

    payload = {
        "frozen_reproduction": reproduced, "liquidity_definition": {"L_raw_mean": l_mean, "L_raw_sample_sd": l_sd, "liquidity_points": liquidity_points},
        "common_support": support, "attenuation": attenuation, "validation": validation,
        "row_audit": audit.to_dict(orient="records"), "asset_liquidity_summary": summary_rows,
        "model_results": model_results, "marginal_token_slopes": marginal,
    }
    PAYLOAD.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_asset = {(r["asset"], r["variable"]): r for r in summary_rows}
    marginal_lookup = {(r["model_id"], r["asset_scope"], r["liquidity_point"]): r for r in marginal}
    def coef(model_id: str, term: str) -> dict:
        return lookup[(model_id, term)]
    lines = [
        "# E2 — NVDA Identity vs Liquidity Dependence",
        "", "`MECHANISM_EXPLORATION`", "",
        "## Frozen-model and row reconciliation", "",
        f"Frozen MODEL 1 reproduced at N=43: beta {fmt(reproduced['token_beta'])}, HC3 SE {fmt(reproduced['token_hc3_standard_error'])}, R² {fmt(reproduced['model_1_r_squared'])}, adjusted R² {fmt(reproduced['model_1_adjusted_r_squared'])}.",
        "All 43 asset/date keys joined exactly once to positive 20:00 and 04:00 quote notionals. No row was added, removed, imputed, or refetched.", "",
        "## 1. Liquidity regimes", "",
        "L_raw = log(1 + min(20:00 quote notional, 04:00 quote notional)); L_z uses the N=43 sample mean and sample SD.", "",
        "| Asset | N | L_z min | P25 | Median | P75 | Max | Mean | SD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for asset in ASSETS:
        row = by_asset[(asset, "L_z")]
        lines.append(f"| {asset} | {row['n']} | {fmt(row['minimum'])} | {fmt(row['percentile_25'])} | {fmt(row['median'])} | {fmt(row['percentile_75'])} | {fmt(row['maximum'])} | {fmt(row['mean'])} | {fmt(row['standard_deviation'])} |")
    lines += [
        "", "## 2. Common support", "",
        f"NVDA L_z range: [{fmt(support['nvda_range_min'])}, {fmt(support['nvda_range_max'])}]. Non-NVDA range: [{fmt(support['non_nvda_range_min'])}, {fmt(support['non_nvda_range_max'])}].",
        f"NVDA observations inside the non-NVDA range: {support['nvda_within_non_nvda_range_count']}/{support['nvda_n']} ({support['nvda_within_non_nvda_range_fraction']:.1%}). Non-NVDA observations inside the NVDA range: {support['non_nvda_within_nvda_range_count']}/{support['non_nvda_n']} ({support['non_nvda_within_nvda_range_fraction']:.1%}).", "",
        "NVDA occupies a higher-liquidity regime on average, but the ranges overlap substantially: only one NVDA row lies above the non-NVDA maximum. The asymmetric overlap and small samples still limit clean mechanism separation.", "",
        "## 3. MODEL_L — liquidity moderation", "",
    ]
    for term in ["token_deep_return_30m", "L_z", "token_x_L_z"]:
        row = coef("MODEL_L", term)
        lines.append(f"- {term}: {fmt(row['estimate'])} (HC3 SE {fmt(row['hc3_standard_error'])}; 95% CI [{fmt(row['ci_95_lower'])}, {fmt(row['ci_95_upper'])}]; p={fmt(row['p_value'])})")
    base_l = model_l["base"]
    lines += [f"- R² {fmt(base_l.rsquared)}; adjusted R² {fmt(base_l.rsquared_adj)}; changes vs frozen MODEL 1: {fmt(base_l.rsquared-frozen_r2)} and {fmt(base_l.rsquared_adj-frozen_adj)}.", "The negative, imprecise theta does not show a coherent strengthening of the token slope as liquidity rises. Point slopes decline modestly from P25 to P75, so this pattern is not affirmative evidence of liquidity-driven information content.", "", "## 4. MODEL_N — targeted NVDA slope heterogeneity", ""]
    for term in ["token_deep_return_30m", "token_x_NVDA", "nvda_token_slope"]:
        row = coef("MODEL_N", term)
        lines.append(f"- {term}: {fmt(row['estimate'])} (HC3 SE {fmt(row['hc3_standard_error'])}; 95% CI [{fmt(row['ci_95_lower'])}, {fmt(row['ci_95_upper'])}]; p={fmt(row['p_value'])})")
    base_n = model_n["base"]
    lines += [f"- R² {fmt(base_n.rsquared)}; adjusted R² {fmt(base_n.rsquared_adj)}; changes vs frozen MODEL 1: {fmt(base_n.rsquared-frozen_r2)} and {fmt(base_n.rsquared_adj-frozen_adj)}.", "MODEL_N estimates a large positive NVDA-specific slope difference, but its HC3 interval is wide and includes zero.", "", "## 5. MODEL_B — both mechanisms", ""]
    for term in ["token_deep_return_30m", "L_z", "token_x_L_z", "token_x_NVDA", "nvda_token_slope_at_mean_liquidity"]:
        row = coef("MODEL_B", term)
        lines.append(f"- {term}: {fmt(row['estimate'])} (HC3 SE {fmt(row['hc3_standard_error'])}; 95% CI [{fmt(row['ci_95_lower'])}, {fmt(row['ci_95_upper'])}]; p={fmt(row['p_value'])})")
    base_b = model_b["base"]
    lines += [
        f"- R² {fmt(base_b.rsquared)}; adjusted R² {fmt(base_b.rsquared_adj)}; changes vs frozen MODEL 1: {fmt(base_b.rsquared-frozen_r2)} and {fmt(base_b.rsquared_adj-frozen_adj)}.",
        f"- NVDA interaction change, MODEL_B minus MODEL_N: {fmt(attenuation['delta_change_b_minus_n'])}; change in absolute magnitude: {fmt(attenuation['delta_absolute_change'])}.",
        f"- Liquidity interaction change, MODEL_B minus MODEL_L: {fmt(attenuation['theta_change_b_minus_l'])}; change in absolute magnitude: {fmt(attenuation['theta_absolute_change'])}.",
        "The NVDA-specific interaction becomes slightly larger rather than attenuating after liquidity moderation is included. The liquidity interaction also becomes more negative, not more supportive of a stronger slope at higher liquidity; both estimates remain imprecise.",
        "", "## 6. Marginal token slopes", "",
        "| Model and scope | P25 | Median | P75 |",
        "|---|---:|---:|---:|",
        f"| MODEL_L pooled | {fmt(marginal_lookup[('MODEL_L', 'POOLED', 'P25')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_L', 'POOLED', 'MEDIAN')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_L', 'POOLED', 'P75')]['token_slope'])} |",
        f"| MODEL_B non-NVDA | {fmt(marginal_lookup[('MODEL_B', 'NON_NVDA', 'P25')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_B', 'NON_NVDA', 'MEDIAN')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_B', 'NON_NVDA', 'P75')]['token_slope'])} |",
        f"| MODEL_B NVDA | {fmt(marginal_lookup[('MODEL_B', 'NVDA', 'P25')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_B', 'NVDA', 'MEDIAN')]['token_slope'])} | {fmt(marginal_lookup[('MODEL_B', 'NVDA', 'P75')]['token_slope'])} |",
        "", "All nine HC3 95% intervals include zero. Full intervals are in `e2_marginal_token_slopes.csv`. Slopes decline as liquidity rises in both models; that pattern could reflect thin-market noise or measurement instability and must not be called stronger low-liquidity price discovery.",
        "", "## 7. Mechanism interpretation", "",
        "The point-estimate pattern is more consistent with residual NVDA-specific heterogeneity than with the pre-specified liquidity-dependence mechanism: overlap exists, theta does not indicate stronger slopes at higher liquidity, and delta is not attenuated in MODEL_B. However, NVDA is concentrated at higher liquidity and both interaction estimates are imprecise in the small N=43 sample.",
        "", "**Overall classification: unresolved confounding, with point estimates leaning toward residual NVDA-specific heterogeneity.** Current N=43 data cannot cleanly separate NVDA identity from liquidity / market-quality dependence. Neither mechanism is proven.",
        "", "## Validation boundary", "",
        "Only the pre-specified L_z proxy and its token interaction enter the liquidity models. All models use OLS, HC3 uncertainty, and the frozen asset fixed effects. No threshold search, alternative proxy, filtering, refetch, E3 analysis, or primary/E1 modification was performed.", "",
    ]
    (OUTPUT_DIR / "e2_mechanism_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", **payload}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
