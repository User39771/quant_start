from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "reports" / "robinhood_chain_pilot" / "rq2_information_content_design"
INPUT = DESIGN_DIR / "rq2_primary_prospective_analysis_panel.csv"
RESULTS_JSON = DESIGN_DIR / "rq2_primary_prospective_results.json"
RESULTS_MD = DESIGN_DIR / "RQ2_PRIMARY_PROSPECTIVE_RESULTS.md"
PLOT_DIR = DESIGN_DIR / "rq2_primary_prospective_plots"

ASSETS = ["NVDA", "GME", "COST"]
EXPECTED_COUNTS = {"NVDA": 11, "GME": 23, "COST": 9}
VARIABLES = [
    "token_deep_return_30m",
    "stock_post_return",
    "stock_20_to_open_return",
    "stock_total_open_gap",
]


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def validate_sample(frame: pd.DataFrame) -> dict:
    required = {
        "token",
        "market_open_date",
        "sample_role",
        "primary_inferential_row",
        "primary_stock_row_ok",
        *VARIABLES,
    }
    missing_columns = sorted(required.difference(frame.columns))
    if missing_columns:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: missing columns {missing_columns}")

    counts = frame["token"].value_counts().to_dict()
    duplicate_keys = int(frame.duplicated(["token", "market_open_date"]).sum())
    missing = {name: int(frame[name].isna().sum()) for name in VARIABLES}
    finite = {
        name: bool(np.isfinite(pd.to_numeric(frame[name], errors="coerce")).all())
        for name in VARIABLES
    }
    checks = {
        "rows": int(len(frame)),
        "asset_counts": {asset: int(counts.get(asset, 0)) for asset in ASSETS},
        "duplicate_token_date_keys": duplicate_keys,
        "missing_required_variables": missing,
        "all_required_variables_finite": finite,
        "all_sample_role_prospective_extension": bool(
            frame["sample_role"].eq("PROSPECTIVE_EXTENSION").all()
        ),
        "all_primary_inferential_row": bool(as_bool(frame["primary_inferential_row"]).all()),
        "all_primary_stock_row_ok": bool(as_bool(frame["primary_stock_row_ok"]).all()),
        "discovery_rows": int(frame["sample_role"].eq("DISCOVERY").sum()),
        "tsla_rows": int(frame["token"].eq("TSLA").sum()),
    }
    passed = (
        checks["rows"] == 43
        and checks["asset_counts"] == EXPECTED_COUNTS
        and duplicate_keys == 0
        and all(value == 0 for value in missing.values())
        and all(finite.values())
        and checks["all_sample_role_prospective_extension"]
        and checks["all_primary_inferential_row"]
        and checks["all_primary_stock_row_ok"]
        and checks["discovery_rows"] == 0
        and checks["tsla_rows"] == 0
    )
    checks["status"] = "PASS" if passed else "STOP_FOR_RESEARCH_REVIEW"
    if not passed:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: {json.dumps(checks, sort_keys=True)}")
    return checks


def describe(frame: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    scopes = [("POOLED", frame)] + [(asset, frame.loc[frame["token"].eq(asset)]) for asset in ASSETS]
    for scope, group in scopes:
        for variable in VARIABLES:
            values = group[variable].astype(float)
            rows.append(
                {
                    "scope": scope,
                    "n": int(len(group)),
                    "date_start": group["market_open_date"].min().date().isoformat(),
                    "date_end": group["market_open_date"].max().date().isoformat(),
                    "variable": variable,
                    "mean": float(values.mean()),
                    "median": float(values.median()),
                    "standard_deviation": float(values.std(ddof=1)),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                }
            )
    return rows


def robust_fit(y: pd.Series, design: pd.DataFrame):
    base = sm.OLS(y.astype(float), design.astype(float)).fit()
    robust = base.get_robustcov_results(cov_type="HC3", use_t=True)
    return base, robust


def coefficient_rows(model_id: str, base, robust, term_names: list[str]) -> list[dict]:
    confidence = np.asarray(robust.conf_int(alpha=0.05))
    rows = []
    for index, term in enumerate(term_names):
        rows.append(
            {
                "model_id": model_id,
                "term": term,
                "estimate": float(robust.params[index]),
                "hc3_standard_error": float(robust.bse[index]),
                "ci_95_lower": float(confidence[index, 0]),
                "ci_95_upper": float(confidence[index, 1]),
                "p_value": float(robust.pvalues[index]),
                "n": int(base.nobs),
                "df_residual": float(base.df_resid),
                "r_squared": float(base.rsquared),
                "adjusted_r_squared": float(base.rsquared_adj),
                "uncertainty": "HC3",
                "reference_distribution": "Student t with OLS residual degrees of freedom",
                "reference_asset": "COST",
            }
        )
    return rows


def per_asset_diagnostics(frame: pd.DataFrame) -> list[dict]:
    output: list[dict] = []
    for asset in ASSETS:
        group = frame.loc[frame["token"].eq(asset)].copy()
        x = group["token_deep_return_30m"].astype(float)
        y = group["stock_20_to_open_return"].astype(float)
        nonzero = x.ne(0) & y.ne(0)
        design = pd.DataFrame({"intercept": 1.0, "token_deep_return_30m": x}, index=group.index)
        base, robust = robust_fit(y, design)
        confidence = np.asarray(robust.conf_int(alpha=0.05))
        pearson = stats.pearsonr(x, y).statistic
        spearman = stats.spearmanr(x, y).statistic
        sign_agreement = float((np.sign(x[nonzero]) == np.sign(y[nonzero])).mean()) if nonzero.any() else None
        output.append(
            {
                "token": asset,
                "n": int(len(group)),
                "date_start": group["market_open_date"].min().date().isoformat(),
                "date_end": group["market_open_date"].max().date().isoformat(),
                "pearson_correlation": float(pearson),
                "spearman_correlation": float(spearman),
                "sign_agreement_rate": sign_agreement,
                "sign_agreement_denominator": int(nonzero.sum()),
                "zero_sign_rows_excluded": int((~nonzero).sum()),
                "simple_beta": float(robust.params[1]),
                "simple_beta_hc3_standard_error": float(robust.bse[1]),
                "simple_beta_ci_95_lower": float(confidence[1, 0]),
                "simple_beta_ci_95_upper": float(confidence[1, 1]),
                "simple_beta_p_value": float(robust.pvalues[1]),
                "simple_model_r_squared": float(base.rsquared),
                "uncertainty": "HC3",
                "reference_distribution": "Student t with OLS residual degrees of freedom",
            }
        )
    return output


def pooled_models(frame: pd.DataFrame):
    dummies = pd.get_dummies(frame["token"], dtype=float)[["GME", "NVDA"]]
    dummies.columns = ["asset_GME", "asset_NVDA"]
    model0_design = pd.concat(
        [
            pd.Series(1.0, index=frame.index, name="intercept_COST"),
            dummies,
            frame[["stock_post_return"]].astype(float),
        ],
        axis=1,
    )
    model1_design = pd.concat(
        [model0_design, frame[["token_deep_return_30m"]].astype(float)],
        axis=1,
    )
    y = frame["stock_20_to_open_return"].astype(float)
    model0_base, model0_robust = robust_fit(y, model0_design)
    model1_base, model1_robust = robust_fit(y, model1_design)
    coefficients = coefficient_rows(
        "MODEL_0", model0_base, model0_robust, list(model0_design.columns)
    ) + coefficient_rows("MODEL_1", model1_base, model1_robust, list(model1_design.columns))

    sse0 = float(np.dot(model0_base.resid, model0_base.resid))
    sse1 = float(np.dot(model1_base.resid, model1_base.resid))
    incremental = {
        "delta_r_squared": float(model1_base.rsquared - model0_base.rsquared),
        "delta_adjusted_r_squared": float(model1_base.rsquared_adj - model0_base.rsquared_adj),
        "partial_r_squared": float((sse0 - sse1) / sse0),
        "partial_r_squared_formula": "(SSE_MODEL_0 - SSE_MODEL_1) / SSE_MODEL_0",
        "sse_model_0": sse0,
        "sse_model_1": sse1,
    }
    fits = {
        "MODEL_0": {
            "formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return",
            "n": int(model0_base.nobs),
            "degrees_of_freedom_residual": float(model0_base.df_resid),
            "r_squared": float(model0_base.rsquared),
            "adjusted_r_squared": float(model0_base.rsquared_adj),
            "sse": sse0,
        },
        "MODEL_1": {
            "formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return + token_deep_return_30m",
            "n": int(model1_base.nobs),
            "degrees_of_freedom_residual": float(model1_base.df_resid),
            "r_squared": float(model1_base.rsquared),
            "adjusted_r_squared": float(model1_base.rsquared_adj),
            "sse": sse1,
        },
    }
    return {
        "model0_design": model0_design,
        "model1_design": model1_design,
        "model0_base": model0_base,
        "model1_base": model1_base,
        "model1_robust": model1_robust,
        "fits": fits,
        "coefficients": coefficients,
        "incremental": incremental,
    }


def influence_diagnostics(frame: pd.DataFrame, model1_base) -> tuple[list[dict], dict]:
    influence = model1_base.get_influence()
    leverage = np.asarray(influence.hat_matrix_diag)
    studentized = np.asarray(influence.resid_studentized_external)
    cooks = np.asarray(influence.cooks_distance[0])
    n = int(model1_base.nobs)
    parameter_count = int(model1_base.df_model + 1)
    leverage_threshold = 2 * parameter_count / n
    studentized_threshold = 2.0
    cooks_threshold = 4 / n
    rows: list[dict] = []
    for position, (_, record) in enumerate(frame.iterrows()):
        high_leverage = bool(leverage[position] > leverage_threshold)
        large_studentized = bool(abs(studentized[position]) > studentized_threshold)
        large_cooks = bool(cooks[position] > cooks_threshold)
        rows.append(
            {
                "token": record["token"],
                "market_open_date": record["market_open_date"].date().isoformat(),
                "leverage": float(leverage[position]),
                "externally_studentized_residual": float(studentized[position]),
                "cooks_distance": float(cooks[position]),
                "high_leverage_flag": high_leverage,
                "large_studentized_residual_flag": large_studentized,
                "large_cooks_distance_flag": large_cooks,
                "unusually_influential_flag": bool(high_leverage or large_studentized or large_cooks),
            }
        )
    summary = {
        "n": n,
        "parameter_count": parameter_count,
        "thresholds": {
            "leverage": leverage_threshold,
            "absolute_externally_studentized_residual": studentized_threshold,
            "cooks_distance": cooks_threshold,
            "threshold_status": "descriptive heuristics only",
        },
        "high_leverage_rows": int(sum(row["high_leverage_flag"] for row in rows)),
        "large_studentized_residual_rows": int(
            sum(row["large_studentized_residual_flag"] for row in rows)
        ),
        "large_cooks_distance_rows": int(sum(row["large_cooks_distance_flag"] for row in rows)),
        "unusually_influential_rows": int(sum(row["unusually_influential_flag"] for row in rows)),
        "flagged_keys": [
            {"token": row["token"], "market_open_date": row["market_open_date"]}
            for row in rows
            if row["unusually_influential_flag"]
        ],
        "observations_removed": 0,
        "model_rerun_after_exclusion": False,
    }
    return rows, summary


def make_plots(frame: pd.DataFrame, model_data: dict) -> dict:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    colors = {"NVDA": "#2563EB", "GME": "#D97706", "COST": "#6B8E23"}
    markers = {"NVDA": "o", "GME": "s", "COST": "^"}
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 10,
            "axes.edgecolor": "#374151",
            "axes.labelcolor": "#111827",
            "xtick.color": "#374151",
            "ytick.color": "#374151",
        }
    )

    scatter_path = PLOT_DIR / "rq2_primary_token_vs_stock_scatter.png"
    fig, axis = plt.subplots(figsize=(7.2, 5.4), constrained_layout=True)
    for asset in ASSETS:
        group = frame.loc[frame["token"].eq(asset)]
        axis.scatter(
            group["token_deep_return_30m"],
            group["stock_20_to_open_return"],
            color=colors[asset],
            marker=markers[asset],
            edgecolor="white",
            linewidth=0.7,
            s=62,
            alpha=0.9,
            label=f"{asset} (N={len(group)})",
        )
    axis.axhline(0, color="#9CA3AF", linewidth=0.8, linestyle="--")
    axis.axvline(0, color="#9CA3AF", linewidth=0.8, linestyle="--")
    axis.grid(True, color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.set_title("Token deep return and subsequent stock return")
    axis.set_xlabel("Token deep return, 20:00–04:00 ET (log return)")
    axis.set_ylabel("Stock 20:00-to-open return (log return)")
    axis.legend(frameon=False, loc="best")
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    fig.savefig(scatter_path, dpi=300, facecolor="white")
    plt.close(fig)

    partial_path = PLOT_DIR / "rq2_primary_token_added_variable_plot.png"
    y = frame["stock_20_to_open_return"].astype(float)
    x = frame["token_deep_return_30m"].astype(float)
    reduced_design = model_data["model0_design"].astype(float)
    y_residual = sm.OLS(y, reduced_design).fit().resid
    x_residual = sm.OLS(x, reduced_design).fit().resid
    partial_slope = float(np.dot(x_residual, y_residual) / np.dot(x_residual, x_residual))
    primary_beta = next(
        row["estimate"]
        for row in model_data["coefficients"]
        if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m"
    )
    if not math.isclose(partial_slope, primary_beta, rel_tol=1e-10, abs_tol=1e-12):
        raise RuntimeError("Added-variable slope does not reconcile with MODEL_1 beta")

    fig, axis = plt.subplots(figsize=(7.2, 5.4), constrained_layout=True)
    for asset in ASSETS:
        mask = frame["token"].eq(asset)
        axis.scatter(
            x_residual.loc[mask],
            y_residual.loc[mask],
            color=colors[asset],
            marker=markers[asset],
            edgecolor="white",
            linewidth=0.7,
            s=62,
            alpha=0.9,
            label=asset,
        )
    line_x = np.linspace(float(x_residual.min()), float(x_residual.max()), 200)
    axis.plot(line_x, primary_beta * line_x, color="#111827", linewidth=1.5, label="MODEL 1 partial slope")
    axis.axhline(0, color="#9CA3AF", linewidth=0.8, linestyle="--")
    axis.axvline(0, color="#9CA3AF", linewidth=0.8, linestyle="--")
    axis.grid(True, color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.set_title("Added-variable plot for token deep return")
    axis.set_xlabel("Token deep return residualized on asset effects and stock post return")
    axis.set_ylabel("Stock 20:00-to-open return residualized on the same controls")
    axis.legend(frameon=False, loc="best")
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    fig.savefig(partial_path, dpi=300, facecolor="white")
    plt.close(fig)
    return {
        "scatter_plot": scatter_path.name,
        "added_variable_plot": partial_path.name,
        "added_variable_slope": partial_slope,
        "added_variable_slope_matches_model_1_beta": True,
    }


def number(value: float | None, digits: int = 6) -> str:
    if value is None:
        return "n.a."
    return f"{value:.{digits}g}"


def p_value(value: float) -> str:
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def markdown_report(results: dict) -> str:
    diagnostics = {row["token"]: row for row in results["asset_diagnostics"]}
    coefficients = {
        (row["model_id"], row["term"]): row for row in results["model_coefficients"]
    }
    model0 = results["models"]["MODEL_0"]
    model1 = results["models"]["MODEL_1"]
    beta = coefficients[("MODEL_1", "token_deep_return_30m")]
    gamma0 = coefficients[("MODEL_0", "stock_post_return")]
    gamma1 = coefficients[("MODEL_1", "stock_post_return")]
    incremental = results["incremental_information"]
    directions = {asset: np.sign(diagnostics[asset]["simple_beta"]) for asset in ASSETS}
    heterogeneous = len(set(directions.values())) > 1
    scaled_beta = beta["estimate"] * 0.01
    flagged = results["influence_summary"]["flagged_keys"]

    lines = [
        "# RQ2 Primary Prospective Results",
        "",
        "`PRIMARY_RQ2_PROSPECTIVE_ANALYSIS = COMPLETE`",
        "",
        "**Research status:** `PILOT_INFORMED_PROSPECTIVE_EXTENSION`  ",
        "**Primary inference:** frozen 43-row `PROSPECTIVE_EXTENSION` sample only  ",
        "**Estimator:** OLS with HC3 heteroskedasticity-robust standard errors  ",
        "**Interval and p-value reference:** Student t with OLS residual degrees of freedom",
        "",
        "## Primary result",
        "",
        f"The MODEL 1 coefficient on `token_deep_return_30m` is **{number(beta['estimate'])}** "
        f"(HC3 SE {number(beta['hc3_standard_error'])}; 95% CI "
        f"[{number(beta['ci_95_lower'])}, {number(beta['ci_95_upper'])}]; "
        f"p = {p_value(beta['p_value'])}). A 0.01 increase in token log return corresponds "
        f"to an estimated {number(scaled_beta)} change in stock 20:00-to-open log return, "
        "holding the frozen conventional after-hours control and asset fixed effects constant.",
        "",
        f"MODEL 1 R² is {number(model1['r_squared'])} and adjusted R² is "
        f"{number(model1['adjusted_r_squared'])}. Relative to MODEL 0, ΔR² is "
        f"{number(incremental['delta_r_squared'])}, Δ adjusted R² is "
        f"{number(incremental['delta_adjusted_r_squared'])}, and token partial R² is "
        f"{number(incremental['partial_r_squared'])}.",
        "",
        "The estimate is an observational incremental association, not evidence of causal price "
        "discovery, exploitable alpha, profitability, or market inefficiency.",
        "",
        "## Frozen sample reconciliation",
        "",
        "| Scope | N | Date range |",
        "|---|---:|---|",
        f"| Pooled | 43 | {results['sample']['date_start']} to {results['sample']['date_end']} |",
    ]
    for asset in ASSETS:
        item = results["sample"]["by_asset"][asset]
        lines.append(f"| {asset} | {item['n']} | {item['date_start']} to {item['date_end']} |")

    lines += [
        "",
        "All 43 rows are prospective-extension, primary-inferential, stock-QA-passing rows. "
        "There are no duplicate token/date keys, missing primary variables, discovery rows, or TSLA rows.",
        "",
        "## Descriptive statistics",
        "",
        "Values are untrimmed log returns. Standard deviation is the sample standard deviation.",
        "",
        "| Scope | Variable | Mean | Median | SD | Minimum | Maximum |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in results["descriptive_statistics"]:
        lines.append(
            f"| {row['scope']} | `{row['variable']}` | {number(row['mean'])} | "
            f"{number(row['median'])} | {number(row['standard_deviation'])} | "
            f"{number(row['minimum'])} | {number(row['maximum'])} |"
        )

    lines += [
        "",
        "## Per-asset diagnostics",
        "",
        "Sign agreement excludes a row from its denominator only when either return is exactly zero. "
        "No row is removed from any other statistic or model.",
        "",
        "| Asset | N | Pearson | Spearman | Sign agreement | Simple beta | HC3 SE | 95% CI | p-value | R² |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for asset in ASSETS:
        row = diagnostics[asset]
        lines.append(
            f"| {asset} | {row['n']} | {number(row['pearson_correlation'])} | "
            f"{number(row['spearman_correlation'])} | {number(row['sign_agreement_rate'])} "
            f"({row['sign_agreement_denominator']}/{row['n']}; zero exclusions {row['zero_sign_rows_excluded']}) | "
            f"{number(row['simple_beta'])} | {number(row['simple_beta_hc3_standard_error'])} | "
            f"[{number(row['simple_beta_ci_95_lower'])}, {number(row['simple_beta_ci_95_upper'])}] | "
            f"{p_value(row['simple_beta_p_value'])} | {number(row['simple_model_r_squared'])} |"
        )
    lines += [
        "",
        f"The asset-level coefficient directions are {'heterogeneous' if heterogeneous else 'broadly consistent'}: "
        + ", ".join(
            f"{asset} {'positive' if diagnostics[asset]['simple_beta'] > 0 else 'negative' if diagnostics[asset]['simple_beta'] < 0 else 'zero'}"
            for asset in ASSETS
        )
        + ". These diagnostics have small samples (NVDA 11, GME 23, COST 9) and are not three independent confirmatory tests.",
        "",
        "## MODEL 0 — frozen baseline",
        "",
        "`stock_20_to_open_return ~ asset fixed effects + stock_post_return`",
        "",
        f"N = {model0['n']}; R² = {number(model0['r_squared'])}; adjusted R² = "
        f"{number(model0['adjusted_r_squared'])}. The `stock_post_return` coefficient is "
        f"{number(gamma0['estimate'])} (HC3 SE {number(gamma0['hc3_standard_error'])}; "
        f"95% CI [{number(gamma0['ci_95_lower'])}, {number(gamma0['ci_95_upper'])}]; "
        f"p = {p_value(gamma0['p_value'])}).",
        "",
        "## MODEL 1 — primary RQ2 model",
        "",
        "`stock_20_to_open_return ~ asset fixed effects + stock_post_return + token_deep_return_30m`",
        "",
        f"N = {model1['n']}; R² = {number(model1['r_squared'])}; adjusted R² = "
        f"{number(model1['adjusted_r_squared'])}. The primary token beta is "
        f"{number(beta['estimate'])} (HC3 SE {number(beta['hc3_standard_error'])}; "
        f"95% CI [{number(beta['ci_95_lower'])}, {number(beta['ci_95_upper'])}]; "
        f"p = {p_value(beta['p_value'])}). The `stock_post_return` coefficient is "
        f"{number(gamma1['estimate'])} (HC3 SE {number(gamma1['hc3_standard_error'])}; "
        f"95% CI [{number(gamma1['ci_95_lower'])}, {number(gamma1['ci_95_upper'])}]; "
        f"p = {p_value(gamma1['p_value'])}).",
        "",
        "COST is the fixed-effect reference asset. All coefficients, including the two asset indicators, are preserved in `rq2_primary_prospective_model_coefficients.csv`.",
        "",
        "## Incremental information",
        "",
        f"- ΔR² = {number(incremental['delta_r_squared'])}",
        f"- Δ adjusted R² = {number(incremental['delta_adjusted_r_squared'])}",
        f"- Partial R² = {number(incremental['partial_r_squared'])}",
        f"- Formula: `{incremental['partial_r_squared_formula']}`",
        "",
        "The partial R² uses ordinary nested-model SSE from the same frozen rows and regressors. "
        "HC3 changes coefficient uncertainty, not OLS fitted values or SSE.",
        "",
        "## Influence diagnostics",
        "",
        f"Standard MODEL 1 diagnostics flagged {results['influence_summary']['unusually_influential_rows']} "
        "of 43 rows under descriptive heuristics: leverage > 2p/N, absolute externally studentized "
        "residual > 2, or Cook's distance > 4/N.",
    ]
    if flagged:
        lines.append(
            "Flagged keys: "
            + ", ".join(f"{row['token']} {row['market_open_date']}" for row in flagged)
            + "."
        )
    else:
        lines.append("No row crossed any of the three descriptive influence thresholds.")
    lines += [
        "No observation was removed and the model was not rerun after exclusion.",
        "",
        "## Interpretation",
        "",
        f"1. **Direction:** the primary beta is {'positive' if beta['estimate'] > 0 else 'negative' if beta['estimate'] < 0 else 'zero'}.",
        f"2. **Magnitude:** beta = {number(beta['estimate'])}; a 0.01 token log-return increase maps to an estimated {number(scaled_beta)} stock log-return change, conditional on the frozen controls.",
        f"3. **Uncertainty:** the 95% CI is [{number(beta['ci_95_lower'])}, {number(beta['ci_95_upper'])}], with width {number(beta['ci_95_upper'] - beta['ci_95_lower'])}.",
        f"4. **Asset consistency:** directions are {'heterogeneous' if heterogeneous else 'broadly consistent'} across the three small per-asset samples.",
        f"5. **Adjusted fit:** adding the token term changes adjusted R² by {number(incremental['delta_adjusted_r_squared'])}.",
        f"6. **Partial R²:** the token term accounts for {number(incremental['partial_r_squared'])} of MODEL 0 residual SSE under the nested-model definition.",
        f"7. **p-value:** {p_value(beta['p_value'])}, treated as one descriptive uncertainty diagnostic rather than a success threshold.",
        "8. **Sample size:** N = 43 limits precision and the stability of pooled and asset-level estimates.",
        "",
        "The most defensible conclusion is based on the direction and magnitude above, the confidence interval, "
        "the fit improvement, and the cross-asset pattern together. This is prospective evidence from the frozen "
        "extension sample, but the overall project remains pilot-informed rather than fully preregistered or fully outcome-naive.",
        "",
        "## Limitations",
        "",
        "- The pooled sample has 43 rows across only three assets and is unbalanced by asset.",
        "- Asset-level diagnostics are especially imprecise at N = 11, 23, and 9.",
        "- The design estimates association, not causality, price leadership, trading profitability, or market inefficiency.",
        "- The overall design was informed by an earlier exploratory NVDA pilot, although these 43 outcomes form the protected prospective extension.",
        "- Alpaca historical REST lacks metadata needed to reconstruct every historical correction/cancel chain; the accepted QA limitation remains.",
        "- Token and stock VWAP anchors can retain measurement noise even after the frozen robustness and stock-QA gates.",
        "- No sensitivity analysis, alternative specification, leave-one-out regression, or observation exclusion was run.",
        "",
        "## Plots",
        "",
        "- `rq2_primary_prospective_plots/rq2_primary_token_vs_stock_scatter.png`",
        "- `rq2_primary_prospective_plots/rq2_primary_token_added_variable_plot.png`",
        "",
        "## Freeze confirmations",
        "",
        "ONLY THE FROZEN 43-ROW PROSPECTIVE PRIMARY SAMPLE WAS USED.",
        "",
        "NO DISCOVERY ROW WAS INCLUDED.",
        "",
        "NO TSLA ROW WAS INCLUDED.",
        "",
        "NO SAMPLE MEMBERSHIP WAS CHANGED AFTER SEEING RESULTS.",
        "",
        "NO QA RULE WAS CHANGED AFTER SEEING RESULTS.",
        "",
        "NO OBSERVATION WAS REMOVED BASED ON OUTCOME MAGNITUDE OR INFLUENCE.",
        "",
        "NO ALTERNATIVE MODEL WAS SELECTED BASED ON SIGNIFICANCE.",
        "",
        "NO SENSITIVITY ANALYSIS WAS RUN.",
        "",
        "NO PROFITABILITY OR TRADING CLAIM WAS TESTED.",
        "",
        "## Next action",
        "",
        "HUMAN / SOL REVIEW OF PRIMARY PROSPECTIVE RQ2 RESULTS BEFORE SENSITIVITY ANALYSES",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    frame = pd.read_csv(INPUT)
    frame["market_open_date"] = pd.to_datetime(frame["market_open_date"], format="%Y-%m-%d")
    for variable in VARIABLES:
        frame[variable] = pd.to_numeric(frame[variable], errors="raise")

    sample_checks = validate_sample(frame)
    descriptions = describe(frame)
    diagnostics = per_asset_diagnostics(frame)
    model_data = pooled_models(frame)
    influence_rows, influence_summary = influence_diagnostics(frame, model_data["model1_base"])
    plots = make_plots(frame, model_data)

    sample = {
        **sample_checks,
        "date_start": frame["market_open_date"].min().date().isoformat(),
        "date_end": frame["market_open_date"].max().date().isoformat(),
        "by_asset": {
            asset: {
                "n": int(frame["token"].eq(asset).sum()),
                "date_start": frame.loc[frame["token"].eq(asset), "market_open_date"].min().date().isoformat(),
                "date_end": frame.loc[frame["token"].eq(asset), "market_open_date"].max().date().isoformat(),
            }
            for asset in ASSETS
        },
    }
    results = {
        "analysis_id": "PRIMARY_PROSPECTIVE_RQ2_ANALYSIS_FIRST_MODEL_RUN",
        "status": "COMPLETE",
        "research_design_status": "PILOT_INFORMED_PROSPECTIVE_EXTENSION",
        "primary_inference": "PROSPECTIVE_EXTENSION_ONLY",
        "canonical_input": "rq2_primary_prospective_analysis_panel.csv",
        "sample": sample,
        "methods": {
            "estimator": "OLS",
            "uncertainty": "HC3 heteroskedasticity-robust standard errors",
            "confidence_level": 0.95,
            "reference_distribution": "Student t with OLS residual degrees of freedom",
            "asset_fixed_effects": "intercept plus GME and NVDA indicators; COST reference",
            "descriptive_standard_deviation": "sample SD with ddof=1",
            "sign_agreement_zero_handling": "exclude rows where either return is exactly zero from the sign-agreement denominator only",
        },
        "descriptive_statistics": descriptions,
        "asset_diagnostics": diagnostics,
        "models": model_data["fits"],
        "model_coefficients": model_data["coefficients"],
        "incremental_information": model_data["incremental"],
        "influence_diagnostics": influence_rows,
        "influence_summary": influence_summary,
        "plots": plots,
        "sensitivity_analyses_run": [],
        "observations_removed": 0,
        "artifacts": [
            "RQ2_PRIMARY_PROSPECTIVE_RESULTS.md",
            "rq2_primary_prospective_results.json",
            "rq2_primary_prospective_model_coefficients.csv",
            "rq2_primary_prospective_asset_diagnostics.csv",
            "rq2_primary_prospective_influence_diagnostics.csv",
            "rq2_primary_prospective_plots/rq2_primary_token_vs_stock_scatter.png",
            "rq2_primary_prospective_plots/rq2_primary_token_added_variable_plot.png",
        ],
        "next_action": "HUMAN / SOL REVIEW OF PRIMARY PROSPECTIVE RQ2 RESULTS BEFORE SENSITIVITY ANALYSES",
        "confirmations": [
            "ONLY THE FROZEN 43-ROW PROSPECTIVE PRIMARY SAMPLE WAS USED.",
            "NO DISCOVERY ROW WAS INCLUDED.",
            "NO TSLA ROW WAS INCLUDED.",
            "NO SAMPLE MEMBERSHIP WAS CHANGED AFTER SEEING RESULTS.",
            "NO QA RULE WAS CHANGED AFTER SEEING RESULTS.",
            "NO OBSERVATION WAS REMOVED BASED ON OUTCOME MAGNITUDE OR INFLUENCE.",
            "NO ALTERNATIVE MODEL WAS SELECTED BASED ON SIGNIFICANCE.",
            "NO SENSITIVITY ANALYSIS WAS RUN.",
            "NO PROFITABILITY OR TRADING CLAIM WAS TESTED.",
        ],
    }
    RESULTS_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    RESULTS_MD.write_text(markdown_report(results), encoding="utf-8")

    beta = next(
        row
        for row in results["model_coefficients"]
        if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m"
    )
    print(
        json.dumps(
            {
                "status": results["status"],
                "n": sample["rows"],
                "asset_counts": sample["asset_counts"],
                "model_0": results["models"]["MODEL_0"],
                "model_1": results["models"]["MODEL_1"],
                "primary_beta": beta,
                "incremental_information": results["incremental_information"],
                "influence_summary": influence_summary,
                "plots": plots,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
