from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_rq2_primary_prospective_first_model import (
    INPUT,
    RESULTS_JSON,
    pooled_models,
    robust_fit,
    validate_sample,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = (
    ROOT
    / "reports"
    / "robinhood_chain_pilot"
    / "rq2_information_content_design"
    / "e1_stability_map"
)
PAYLOAD = OUTPUT_DIR / "e1_stability_payload.json"
SUMMARY_MD = OUTPUT_DIR / "e1_stability_summary.md"
PLOT = OUTPUT_DIR / "e1_coefficient_stability.png"

INFLUENCE_KEYS = [
    ("NVDA", "2026-07-23"),
    ("NVDA", "2026-08-04"),
    ("NVDA", "2026-08-05"),
    ("GME", "2026-09-04"),
]
ASSET_ORDER = ["NVDA", "GME", "COST"]
FIXED_EFFECT_ORDER = ["COST", "GME", "NVDA"]


def coefficient(model_data: dict) -> dict:
    return next(
        row
        for row in model_data["coefficients"]
        if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m"
    )


def metric_bundle(model_data: dict) -> dict:
    token = coefficient(model_data)
    model0 = model_data["fits"]["MODEL_0"]
    model1 = model_data["fits"]["MODEL_1"]
    incremental = model_data["incremental"]
    return {
        "n": model1["n"],
        "token_beta": token["estimate"],
        "token_hc3_standard_error": token["hc3_standard_error"],
        "token_ci_95_lower": token["ci_95_lower"],
        "token_ci_95_upper": token["ci_95_upper"],
        "token_p_value": token["p_value"],
        "model_0_r_squared": model0["r_squared"],
        "model_0_adjusted_r_squared": model0["adjusted_r_squared"],
        "model_1_r_squared": model1["r_squared"],
        "model_1_adjusted_r_squared": model1["adjusted_r_squared"],
        "delta_r_squared": incremental["delta_r_squared"],
        "delta_adjusted_r_squared": incremental["delta_adjusted_r_squared"],
        "token_partial_r_squared": incremental["partial_r_squared"],
        "estimator": "OLS",
        "uncertainty": "HC3",
        "reference_distribution": "Student t with OLS residual degrees of freedom",
        "model_0_formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return",
        "model_1_formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return + token_deep_return_30m",
    }


def fit_subset(frame: pd.DataFrame) -> dict:
    present = [asset for asset in FIXED_EFFECT_ORDER if frame["token"].eq(asset).any()]
    if len(present) < 2:
        raise RuntimeError("E1 subset must contain at least two assets")
    reference = "COST" if "COST" in present else present[0]
    dummy_assets = [asset for asset in FIXED_EFFECT_ORDER if asset in present and asset != reference]
    dummies = pd.get_dummies(frame["token"], dtype=float)[dummy_assets]
    dummies.columns = [f"asset_{asset}" for asset in dummy_assets]
    model0_design = pd.concat(
        [
            pd.Series(1.0, index=frame.index, name=f"intercept_{reference}"),
            dummies,
            frame[["stock_post_return"]].astype(float),
        ],
        axis=1,
    )
    model1_design = pd.concat(
        [model0_design, frame[["token_deep_return_30m"]].astype(float)], axis=1
    )
    outcome = frame["stock_20_to_open_return"].astype(float)
    model0_base, _ = robust_fit(outcome, model0_design)
    model1_base, model1_robust = robust_fit(outcome, model1_design)
    token_index = list(model1_design.columns).index("token_deep_return_30m")
    confidence = np.asarray(model1_robust.conf_int(alpha=0.05))[token_index]
    sse0 = float(np.dot(model0_base.resid, model0_base.resid))
    sse1 = float(np.dot(model1_base.resid, model1_base.resid))
    return {
        "n": int(model1_base.nobs),
        "token_beta": float(model1_robust.params[token_index]),
        "token_hc3_standard_error": float(model1_robust.bse[token_index]),
        "token_ci_95_lower": float(confidence[0]),
        "token_ci_95_upper": float(confidence[1]),
        "token_p_value": float(model1_robust.pvalues[token_index]),
        "model_0_r_squared": float(model0_base.rsquared),
        "model_0_adjusted_r_squared": float(model0_base.rsquared_adj),
        "model_1_r_squared": float(model1_base.rsquared),
        "model_1_adjusted_r_squared": float(model1_base.rsquared_adj),
        "delta_r_squared": float(model1_base.rsquared - model0_base.rsquared),
        "delta_adjusted_r_squared": float(
            model1_base.rsquared_adj - model0_base.rsquared_adj
        ),
        "token_partial_r_squared": float((sse0 - sse1) / sse0),
        "fixed_effect_reference_asset": reference,
        "estimator": "OLS",
        "uncertainty": "HC3",
        "reference_distribution": "Student t with OLS residual degrees of freedom",
        "model_0_formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return",
        "model_1_formula": "stock_20_to_open_return ~ asset fixed effects + stock_post_return + token_deep_return_30m",
    }


def reproduce_frozen(frame: pd.DataFrame, frozen: dict) -> tuple[dict, dict]:
    validate_sample(frame)
    reproduced_model = pooled_models(frame)
    reproduced = metric_bundle(reproduced_model)
    frozen_beta = next(
        row
        for row in frozen["model_coefficients"]
        if row["model_id"] == "MODEL_1" and row["term"] == "token_deep_return_30m"
    )
    expected = {
        "n": frozen["sample"]["rows"],
        "token_beta": frozen_beta["estimate"],
        "token_hc3_standard_error": frozen_beta["hc3_standard_error"],
        "token_ci_95_lower": frozen_beta["ci_95_lower"],
        "token_ci_95_upper": frozen_beta["ci_95_upper"],
        "token_p_value": frozen_beta["p_value"],
        "model_0_r_squared": frozen["models"]["MODEL_0"]["r_squared"],
        "model_0_adjusted_r_squared": frozen["models"]["MODEL_0"]["adjusted_r_squared"],
        "model_1_r_squared": frozen["models"]["MODEL_1"]["r_squared"],
        "model_1_adjusted_r_squared": frozen["models"]["MODEL_1"]["adjusted_r_squared"],
        "delta_r_squared": frozen["incremental_information"]["delta_r_squared"],
        "delta_adjusted_r_squared": frozen["incremental_information"][
            "delta_adjusted_r_squared"
        ],
        "token_partial_r_squared": frozen["incremental_information"][
            "partial_r_squared"
        ],
    }
    differences = {}
    for key, expected_value in expected.items():
        actual = reproduced[key]
        matches = (
            actual == expected_value
            if key == "n"
            else math.isclose(actual, expected_value, rel_tol=1e-12, abs_tol=1e-14)
        )
        differences[key] = {
            "frozen": expected_value,
            "reproduced": actual,
            "absolute_difference": 0 if key == "n" else abs(actual - expected_value),
            "matches": matches,
        }
    if not all(item["matches"] for item in differences.values()):
        raise RuntimeError(
            "STOP_FOR_RESEARCH_REVIEW: frozen primary result did not reproduce: "
            + json.dumps(differences, sort_keys=True)
        )
    return reproduced, differences


def leave_one_session_out(frame: pd.DataFrame, frozen_beta: float) -> list[dict]:
    rows = []
    for index, omitted in frame.iterrows():
        subset = frame.drop(index=index)
        metrics = fit_subset(subset)
        rows.append(
            {
                "sensitivity_label": "E1_A_LEAVE_ONE_SESSION_OUT",
                "omitted_asset": omitted["token"],
                "omitted_market_open_date": omitted["market_open_date"].date().isoformat(),
                "remaining_assets": ";".join(sorted(subset["token"].unique())),
                **metrics,
                "beta_change_from_frozen": metrics["token_beta"] - frozen_beta,
                "absolute_beta_change_from_frozen": abs(
                    metrics["token_beta"] - frozen_beta
                ),
            }
        )
    return rows


def leave_one_asset_out(frame: pd.DataFrame, frozen_beta: float) -> list[dict]:
    rows = []
    for omitted_asset in ASSET_ORDER:
        subset = frame.loc[~frame["token"].eq(omitted_asset)].copy()
        metrics = fit_subset(subset)
        rows.append(
            {
                "sensitivity_label": "E1_B_LEAVE_ONE_ASSET_OUT",
                "omitted_asset": omitted_asset,
                "remaining_assets": ";".join(sorted(subset["token"].unique())),
                **metrics,
                "beta_change_from_frozen": metrics["token_beta"] - frozen_beta,
                "absolute_beta_change_from_frozen": abs(
                    metrics["token_beta"] - frozen_beta
                ),
            }
        )
    return rows


def influence_stress(frame: pd.DataFrame, frozen_beta: float) -> list[dict]:
    key_series = list(zip(frame["token"], frame["market_open_date"].dt.date.astype(str)))
    counts = {key: key_series.count(key) for key in INFLUENCE_KEYS}
    if any(value != 1 for value in counts.values()):
        raise RuntimeError(
            "STOP_FOR_RESEARCH_REVIEW: pre-identified influence key mismatch: "
            + json.dumps({f"{key[0]} {key[1]}": value for key, value in counts.items()})
        )
    excluded = pd.Series(
        [(token, date.date().isoformat()) in INFLUENCE_KEYS for token, date in zip(frame["token"], frame["market_open_date"])],
        index=frame.index,
    )
    subset = frame.loc[~excluded].copy()
    if len(subset) != 39:
        raise RuntimeError(f"STOP_FOR_RESEARCH_REVIEW: influence stress N={len(subset)}, expected 39")
    metrics = fit_subset(subset)
    return [
        {
            "sensitivity_label": "SENSITIVITY_ONLY_INFLUENCE_STRESS",
            "omitted_observation_count": 4,
            "omitted_observations": ";".join(
                f"{asset} {date}" for asset, date in INFLUENCE_KEYS
            ),
            "remaining_assets": ";".join(sorted(subset["token"].unique())),
            **metrics,
            "beta_change_from_frozen": metrics["token_beta"] - frozen_beta,
            "absolute_beta_change_from_frozen": abs(metrics["token_beta"] - frozen_beta),
        }
    ]


def session_summary(rows: list[dict], frozen_beta: float) -> dict:
    betas = np.asarray([row["token_beta"] for row in rows])
    ranked = sorted(rows, key=lambda row: row["absolute_beta_change_from_frozen"], reverse=True)
    return {
        "runs": len(rows),
        "positive_beta_count": int(np.sum(betas > 0)),
        "positive_beta_fraction": float(np.mean(betas > 0)),
        "negative_beta_count": int(np.sum(betas < 0)),
        "negative_beta_fraction": float(np.mean(betas < 0)),
        "zero_beta_count": int(np.sum(betas == 0)),
        "minimum_beta": float(np.min(betas)),
        "maximum_beta": float(np.max(betas)),
        "median_beta": float(np.median(betas)),
        "frozen_beta": frozen_beta,
        "largest_absolute_change_from_frozen": float(
            max(row["absolute_beta_change_from_frozen"] for row in rows)
        ),
        "delta_adjusted_r_squared_minimum": float(
            min(row["delta_adjusted_r_squared"] for row in rows)
        ),
        "delta_adjusted_r_squared_maximum": float(
            max(row["delta_adjusted_r_squared"] for row in rows)
        ),
        "token_partial_r_squared_minimum": float(
            min(row["token_partial_r_squared"] for row in rows)
        ),
        "token_partial_r_squared_maximum": float(
            max(row["token_partial_r_squared"] for row in rows)
        ),
        "largest_beta_changes": [
            {
                "omitted_asset": row["omitted_asset"],
                "omitted_market_open_date": row["omitted_market_open_date"],
                "token_beta": row["token_beta"],
                "beta_change_from_frozen": row["beta_change_from_frozen"],
                "absolute_beta_change_from_frozen": row[
                    "absolute_beta_change_from_frozen"
                ],
            }
            for row in ranked[:5]
        ],
    }


def make_plot(rows: list[dict], frozen_beta: float) -> None:
    ordered = sorted(rows, key=lambda row: row["token_beta"])
    colors = {"NVDA": "#2563EB", "GME": "#D97706", "COST": "#6B8E23"}
    markers = {"NVDA": "o", "GME": "s", "COST": "^"}
    positions = np.arange(len(ordered))
    fig, axis = plt.subplots(figsize=(14, 6.8), constrained_layout=True)
    for asset in ASSET_ORDER:
        indexes = [index for index, row in enumerate(ordered) if row["omitted_asset"] == asset]
        subset = [ordered[index] for index in indexes]
        values = np.asarray([row["token_beta"] for row in subset])
        lower = values - np.asarray([row["token_ci_95_lower"] for row in subset])
        upper = np.asarray([row["token_ci_95_upper"] for row in subset]) - values
        axis.errorbar(
            indexes,
            values,
            yerr=np.vstack([lower, upper]),
            fmt=markers[asset],
            color=colors[asset],
            ecolor=colors[asset],
            elinewidth=0.7,
            capsize=1.5,
            markersize=5.5,
            alpha=0.82,
            label=asset,
        )
    axis.axhline(
        frozen_beta,
        color="#111827",
        linewidth=1.5,
        linestyle="--",
        label=f"Frozen beta = {frozen_beta:.3f}",
    )
    axis.axhline(0, color="#9CA3AF", linewidth=0.8)
    axis.set_xticks(positions)
    axis.set_xticklabels(
        [f"{row['omitted_asset']}\n{row['omitted_market_open_date'][5:]}" for row in ordered],
        rotation=90,
        ha="center",
        fontsize=7,
    )
    axis.set_ylabel("MODEL 1 token beta after one-session omission")
    axis.set_xlabel("Omitted observation (ordered by resulting beta)")
    axis.set_title("E1-A leave-one-session-out coefficient stability")
    axis.grid(True, axis="y", color="#E5E7EB", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, ncol=4, loc="upper center")
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    fig.savefig(PLOT, dpi=300, facecolor="white")
    plt.close(fig)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def write_summary(
    reproduced: dict,
    session: dict,
    asset_rows: list[dict],
    stress_row: dict,
) -> None:
    asset_map = {row["omitted_asset"]: row for row in asset_rows}
    top = session["largest_beta_changes"]
    sign_text = (
        "The beta sign is fully stable across all 43 omissions."
        if session["positive_beta_count"] == session["runs"]
        else "The beta sign changes in at least one leave-one-session-out run."
    )
    lines = [
        "# E1 Stability Map",
        "",
        "## Frozen reference",
        "",
        "The existing pipeline reproduces the frozen N=43 primary result within floating-point tolerance:",
        "",
        f"- token beta: {fmt(reproduced['token_beta'])}",
        f"- HC3 SE: {fmt(reproduced['token_hc3_standard_error'])}",
        f"- 95% CI: [{fmt(reproduced['token_ci_95_lower'])}, {fmt(reproduced['token_ci_95_upper'])}]",
        f"- p-value: {fmt(reproduced['token_p_value'])}",
        f"- MODEL 0 R² / adjusted R²: {fmt(reproduced['model_0_r_squared'])} / {fmt(reproduced['model_0_adjusted_r_squared'])}",
        f"- MODEL 1 R² / adjusted R²: {fmt(reproduced['model_1_r_squared'])} / {fmt(reproduced['model_1_adjusted_r_squared'])}",
        f"- delta R² / delta adjusted R²: {fmt(reproduced['delta_r_squared'])} / {fmt(reproduced['delta_adjusted_r_squared'])}",
        f"- token partial R²: {fmt(reproduced['token_partial_r_squared'])}",
        "",
        "## E1-A — leave one session out",
        "",
        f"All 43 runs contain N=42. Positive betas: {session['positive_beta_count']}/43 "
        f"({session['positive_beta_fraction']:.1%}); negative betas: {session['negative_beta_count']}/43 "
        f"({session['negative_beta_fraction']:.1%}). {sign_text}",
        "",
        f"Beta range: {fmt(session['minimum_beta'])} to {fmt(session['maximum_beta'])}; "
        f"median: {fmt(session['median_beta'])}; largest absolute change from the frozen beta: "
        f"{fmt(session['largest_absolute_change_from_frozen'])}.",
        "",
        f"Delta adjusted R² ranges from {fmt(session['delta_adjusted_r_squared_minimum'])} to "
        f"{fmt(session['delta_adjusted_r_squared_maximum'])}; token partial R² ranges from "
        f"{fmt(session['token_partial_r_squared_minimum'])} to {fmt(session['token_partial_r_squared_maximum'])}.",
        "",
        "Largest absolute beta changes:",
        "",
        "| Omitted observation | Resulting beta | Change from frozen |",
        "|---|---:|---:|",
    ]
    for row in top:
        lines.append(
            f"| {row['omitted_asset']} {row['omitted_market_open_date']} | "
            f"{fmt(row['token_beta'])} | {fmt(row['beta_change_from_frozen'])} |"
        )
    lines += [
        "",
        "These rankings are descriptive only and do not recommend deleting any observation.",
        "",
        "## E1-B — leave one asset out",
        "",
        "| Omitted asset | N | Token beta | HC3 SE | 95% CI | Delta adjusted R² | Partial R² |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for asset in ASSET_ORDER:
        row = asset_map[asset]
        lines.append(
            f"| {asset} | {row['n']} | {fmt(row['token_beta'])} | "
            f"{fmt(row['token_hc3_standard_error'])} | "
            f"[{fmt(row['token_ci_95_lower'])}, {fmt(row['token_ci_95_upper'])}] | "
            f"{fmt(row['delta_adjusted_r_squared'])} | {fmt(row['token_partial_r_squared'])} |"
        )
    without_nvda = asset_map["NVDA"]
    lines += [
        "",
        f"Without NVDA, the token beta is {fmt(without_nvda['token_beta'])}, delta adjusted R² is "
        f"{fmt(without_nvda['delta_adjusted_r_squared'])}, and partial R² is "
        f"{fmt(without_nvda['token_partial_r_squared'])}. This subset is a sensitivity diagnostic, not a replacement primary model.",
        "",
        "## E1-C — pre-identified influence stress",
        "",
        "`SENSITIVITY_ONLY_INFLUENCE_STRESS`",
        "",
        f"After simultaneously omitting the four pre-identified observations, N = {stress_row['n']}. "
        f"The token beta is {fmt(stress_row['token_beta'])} (HC3 SE {fmt(stress_row['token_hc3_standard_error'])}; "
        f"95% CI [{fmt(stress_row['token_ci_95_lower'])}, {fmt(stress_row['token_ci_95_upper'])}]; "
        f"p = {fmt(stress_row['token_p_value'])}). Delta adjusted R² is "
        f"{fmt(stress_row['delta_adjusted_r_squared'])} and partial R² is "
        f"{fmt(stress_row['token_partial_r_squared'])}.",
        "",
        "This stress result does not correct or replace the frozen N=43 primary estimate. No additional observation was searched for or removed.",
        "",
        "## Interpretation boundary",
        "",
        "E1 evaluates whether the frozen positive incremental association is stable to bounded, pre-specified omissions. It does not establish causality, reliable prediction, price discovery, trading profitability, or a basis for changing the primary sample.",
        "",
    ]
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(INPUT)
    frame["market_open_date"] = pd.to_datetime(frame["market_open_date"], format="%Y-%m-%d")
    for column in (
        "token_deep_return_30m",
        "stock_post_return",
        "stock_20_to_open_return",
        "stock_total_open_gap",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frozen = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    reproduced, reproduction_checks = reproduce_frozen(frame, frozen)
    frozen_beta = reproduced["token_beta"]

    session_rows = leave_one_session_out(frame, frozen_beta)
    asset_rows = leave_one_asset_out(frame, frozen_beta)
    stress_rows = influence_stress(frame, frozen_beta)
    session = session_summary(session_rows, frozen_beta)

    if len(session_rows) != 43 or any(row["n"] != 42 for row in session_rows):
        raise RuntimeError("E1-A validation failure")
    if len(asset_rows) != 3:
        raise RuntimeError("E1-B validation failure")
    if stress_rows[0]["n"] != 39:
        raise RuntimeError("E1-C validation failure")
    if frame["sample_role"].eq("DISCOVERY").any() or frame["token"].eq("TSLA").any():
        raise RuntimeError("Forbidden discovery or TSLA row entered E1")

    make_plot(session_rows, frozen_beta)
    write_summary(reproduced, session, asset_rows, stress_rows[0])
    payload = {
        "status": "COMPLETE",
        "analysis": "E1_STABILITY_MAP",
        "canonical_input_rows": len(frame),
        "primary_reproduction": reproduced,
        "primary_reproduction_checks": reproduction_checks,
        "leave_one_session_out": session_rows,
        "leave_one_session_out_summary": session,
        "leave_one_asset_out": asset_rows,
        "influence_stress": stress_rows,
        "validation": {
            "frozen_sample_rows": len(frame),
            "e1_a_runs": len(session_rows),
            "all_e1_a_n_42": all(row["n"] == 42 for row in session_rows),
            "e1_b_runs": len(asset_rows),
            "e1_c_n": stress_rows[0]["n"],
            "discovery_rows": int(frame["sample_role"].eq("DISCOVERY").sum()),
            "tsla_rows": int(frame["token"].eq("TSLA").sum()),
            "all_estimators_ols_hc3": all(
                row["estimator"] == "OLS" and row["uncertainty"] == "HC3"
                for row in session_rows + asset_rows + stress_rows
            ),
        },
    }
    PAYLOAD.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "primary_reproduction": reproduced,
                "leave_one_session_out_summary": session,
                "leave_one_asset_out": asset_rows,
                "influence_stress": stress_rows,
                "validation": payload["validation"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
