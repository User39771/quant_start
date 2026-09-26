"""Phase A MOM60/REV60 evaluation contract; pure calculations, no data loading."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

PRIMARY_COST_RATE = 0.002
SENSITIVITY_COST_RATES = (0.0, PRIMARY_COST_RATE, 0.003)
PRIMARY_INFORMATION_THRESHOLD = 0.015
MIN_PERIODS = 24
FROZEN_HASHES = dict(
    [
        (
            "scripts/test_mom60_hypothesis_v1_3.py",
            "4b023704f65290a5ccb41833df652e8ca3d108278b0ccf2b00ed22a7fc5f790a",
        ),
        (
            "tests/test_mom60_hypothesis_v1_3.py",
            "f187efffad8d487cdd67aad40bc8d56818ffe1785165a64224bdac7538290953",
        ),
        (
            "data/processed/mom60_factor_panel_v1_3.csv",
            "2c25fb4196da19b24463cdfdb23fa821c85cf22e2d53576d8f13fe792c0aa341",
        ),
        (
            "reports/factor_data_readiness_v1_3.csv",
            "9803c6fba880f2a1679b7275c04cac5a9d1fd6438207e3911fea16b32e6d840e",
        ),
        (
            "reports/factor_ic_periods_mom60_v1_3.csv",
            "a9aedc5a58d847bbd7443bdf8995045f8bb53efdb743d1f15c7cb84b8211e385",
        ),
        (
            "reports/factor_ic_summary_mom60_v1_3.csv",
            "492c29a7d41c4e442769b4d09807c6bc0f962bb066612b1887171edfe633a208",
        ),
        (
            "reports/factor_quantile_returns_mom60_v1_3.csv",
            "f9d168c92dabff2840fa6a97ed0ef4922876f27707d29a87fda79e4f8a72f533",
        ),
        (
            "reports/factor_quantile_summary_mom60_v1_3.csv",
            "5d16d9c1f62178f8d5b283e22a728c33790c7d80ebbf725c624321a1875f8c10",
        ),
        (
            "reports/factor_stability_mom60_v1_3.csv",
            "15d7ef0c95dc098d4a62f22562c8f2d34ce7f71853246ea64c2588ea62f9dd3c",
        ),
        (
            "reports/factor_hypothesis_summary_v1_3.csv",
            "45ed5231c1a2178a7c5b82ffc9d97c565b27fb70af4ceb99b3c183c8cc9c9c40",
        ),
        (
            "reports/factor_research_qa_v1_3.csv",
            "40335ca1f6734f072c2b83fdd0c6036b4f6a3d37145b5da9863ac18f2ee78c7a",
        ),
        (
            "reports/factor_mom60_v1_3.md",
            "7f5f75c24a5b198873a8afaaa4616bc0acd8de089554e4c5eadda62864f9149d",
        ),
        (
            "reports/mom60_v1_3_freeze_review.md",
            "e13f652a7b624fc78ce2735ebea22b56968efcb8541842f132f5fd01f273053c",
        ),
    ]
)

REQUIRED_COLUMNS = {
    "period_index",
    "stock_code",
    "signal_as_of_date",
    "rebalance_date",
    "next_rebalance_date",
    "signal_sample_member",
    "baseline_eligible",
    "mom60",
    "forward_return",
}


def _bool(series: pd.Series, row_keys: pd.DataFrame | None = None) -> pd.Series:
    true_strings = {"true", "1", "yes"}
    false_strings = {"false", "0", "no"}
    parsed: list[bool] = []
    invalid: list[tuple[object, object]] = []
    for index, value in series.items():
        if isinstance(value, (bool, np.bool_)):
            parsed.append(bool(value))
        elif isinstance(value, str) and value.strip().lower() in true_strings | false_strings:
            parsed.append(value.strip().lower() in true_strings)
        else:
            parsed.append(False)
            invalid.append((index, value))
    if invalid:
        examples = []
        for index, _ in invalid[:5]:
            if row_keys is not None:
                row = row_keys.loc[index]
                examples.append(
                    {
                        "period_index": row.get("period_index"),
                        "stock_code": row.get("stock_code"),
                    }
                )
            else:
                examples.append(index)
        values = ["<null>" if pd.isna(value) else repr(value) for _, value in invalid]
        raise ValueError(
            f"invalid_boolean_values column={series.name} count={len(invalid)} "
            f"values={sorted(set(values))} rows={examples}"
        )
    return pd.Series(parsed, index=series.index, dtype=bool, name=series.name)


def _finite(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.isfinite(values), index=series.index)


def assign_contract_members(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze signal-date membership and raw quantiles before inspecting labels."""
    missing = REQUIRED_COLUMNS - set(panel.columns)
    if missing:
        raise ValueError(f"missing_columns={sorted(missing)}")
    result = panel.copy()
    normalized_codes = []
    invalid_codes = []
    for index, value in result["stock_code"].items():
        if not isinstance(value, str):
            invalid_codes.append((index, value))
            normalized_codes.append("")
            continue
        raw = value.strip()
        if not raw or not raw.isascii() or not raw.isdigit() or not 1 <= len(raw) <= 6:
            invalid_codes.append((index, value))
            normalized_codes.append("")
            continue
        normalized_codes.append(raw.zfill(6))
    if invalid_codes:
        examples = [
            {
                "index": index,
                "period_index": result.loc[index, "period_index"],
                "stock_code": "<null>" if pd.isna(value) else repr(value),
            }
            for index, value in invalid_codes[:5]
        ]
        raise ValueError(f"invalid_stock_code count={len(invalid_codes)} rows={examples}")
    result["stock_code"] = normalized_codes
    if result.duplicated(["period_index", "stock_code"]).any():
        duplicates = result.loc[
            result.duplicated(["period_index", "stock_code"], keep=False),
            ["period_index", "stock_code"],
        ].head(5)
        raise ValueError(
            "duplicate_period_stock_after_normalization "
            f"rows={duplicates.to_dict(orient='records')}"
        )
    for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
        result[column] = pd.to_datetime(result[column], errors="raise")
        if result[column].isna().any():
            raise ValueError(f"null_period_date column={column}")
        counts = result.groupby("period_index")[column].nunique(dropna=False)
        inconsistent = counts.loc[counts.ne(1)].index.tolist()
        if inconsistent:
            raise ValueError(f"inconsistent_period_date column={column} periods={inconsistent[:5]}")
    if not (
        (result["signal_as_of_date"] < result["rebalance_date"])
        & (result["rebalance_date"] < result["next_rebalance_date"])
    ).all():
        raise ValueError("invalid_date_order")

    result["mom60"] = pd.to_numeric(result["mom60"], errors="coerce")
    result["forward_return"] = pd.to_numeric(result["forward_return"], errors="coerce")
    row_keys = result[["period_index", "stock_code"]]
    result["baseline_eligible"] = _bool(result["baseline_eligible"], row_keys)
    result["signal_sample_member"] = _bool(result["signal_sample_member"], row_keys)
    result["signal_target_member"] = result["signal_sample_member"] & _finite(result["mom60"])
    result["label_available"] = _finite(result["forward_return"])
    result["evaluation_sample_member"] = result["signal_target_member"] & result["label_available"]
    result["raw_quantile"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["oriented_quantile"] = pd.Series(pd.NA, index=result.index, dtype="Int64")

    audits: list[dict[str, object]] = []
    for period, group in result.groupby("period_index", sort=True):
        target = group.loc[group["signal_target_member"]].sort_values(
            ["mom60", "stock_code"], kind="stable"
        )
        if len(target) >= 5:
            for quantile, indices in enumerate(np.array_split(target.index.to_numpy(), 5), 1):
                result.loc[indices, "raw_quantile"] = quantile
            result.loc[target.index, "oriented_quantile"] = (
                6 - result.loc[target.index, "raw_quantile"]
            )

        assigned = result.loc[target.index]
        duplicate_values = assigned.loc[assigned["mom60"].duplicated(False), "mom60"].unique()
        boundary_values = []
        for value, tied in assigned.groupby("mom60"):
            quantiles = set(tied["raw_quantile"].dropna().astype(int))
            if {1, 2}.issubset(quantiles) or {4, 5}.issubset(quantiles):
                boundary_values.append(value)
        boundary_count = int(assigned["mom60"].isin(boundary_values).sum())
        audits.append(
            {
                "period_index": period,
                "baseline_eligible_count": int(group["baseline_eligible"].sum()),
                "signal_target_count": len(target),
                "valid_forward_return_count": int(group["label_available"].sum()),
                "jointly_valid_count": int(group["evaluation_sample_member"].sum()),
                "jointly_valid_coverage": float(
                    group["evaluation_sample_member"].sum() / len(target)
                )
                if len(target)
                else 0.0,
                "tie_count": int(assigned["mom60"].isin(duplicate_values).sum()),
                "boundary_tie_count": boundary_count,
                "tie_split": boundary_count > 0,
                "boundary_tie_warning": boundary_count > 0,
            }
        )
    return result, pd.DataFrame(audits)


def validate_official_period_mapping(
    panel: pd.DataFrame,
    official_ic: pd.DataFrame,
    readiness: pd.DataFrame,
) -> pd.DataFrame:
    """Match the selected panel to the two frozen sources defining the official 54 periods."""

    date_columns = ["signal_as_of_date", "rebalance_date", "next_rebalance_date"]
    required_ic = {
        "factor_name",
        "sample_basis",
        "period_index",
        "rebalance_date",
        "next_rebalance_date",
    }
    required_readiness = {
        "row_type",
        "main_period_member",
        "period_index",
        *date_columns,
    }
    if not required_ic.issubset(official_ic.columns):
        raise ValueError(f"official_ic_missing_columns={sorted(required_ic - set(official_ic))}")
    if not required_readiness.issubset(readiness.columns):
        raise ValueError(f"readiness_missing_columns={sorted(required_readiness - set(readiness))}")

    ic = official_ic.loc[
        official_ic["factor_name"].eq("MOM60")
        & official_ic["sample_basis"].eq("mom60_primary_sample")
    ].copy()
    readiness_periods = readiness.loc[readiness["row_type"].eq("period")].copy()
    readiness_periods["main_period_member"] = _bool(
        readiness_periods["main_period_member"],
        readiness_periods[["period_index"]],
    )
    ready = readiness_periods.loc[readiness_periods["main_period_member"]].copy()
    for name, frame in (("official_ic", ic), ("readiness", ready)):
        numeric = pd.to_numeric(frame["period_index"], errors="raise")
        if not np.isfinite(numeric).all() or not np.equal(numeric, np.floor(numeric)).all():
            raise ValueError(f"{name}_invalid_period_index")
        frame["period_index"] = numeric.astype(int)
        if len(frame) != 54 or frame["period_index"].duplicated().any():
            raise ValueError(f"{name}_official_period_contract")
    for column in ("rebalance_date", "next_rebalance_date"):
        ic[column] = pd.to_datetime(ic[column], errors="raise")
    for column in date_columns:
        ready[column] = pd.to_datetime(ready[column], errors="raise")

    if set(ic["period_index"]) != set(ready["period_index"]):
        raise ValueError("official_period_key_mismatch_between_sources")
    source = ready[["period_index", *date_columns]].merge(
        ic[["period_index", "rebalance_date", "next_rebalance_date"]],
        on="period_index",
        suffixes=("_readiness", "_ic"),
        validate="one_to_one",
    )
    for column in ("rebalance_date", "next_rebalance_date"):
        if not source[f"{column}_readiness"].equals(source[f"{column}_ic"]):
            raise ValueError(f"official_period_date_mismatch_between_sources column={column}")
    canonical = source[
        [
            "period_index",
            "signal_as_of_date",
            "rebalance_date_readiness",
            "next_rebalance_date_readiness",
        ]
    ].rename(
        columns={
            "rebalance_date_readiness": "rebalance_date",
            "next_rebalance_date_readiness": "next_rebalance_date",
        }
    )

    selected = panel.copy()
    selected["period_index"] = pd.to_numeric(selected["period_index"], errors="raise").astype(int)
    for column in date_columns:
        selected[column] = pd.to_datetime(selected[column], errors="raise")
    panel_dates = selected.groupby("period_index", as_index=False)[date_columns].first()
    if set(panel_dates["period_index"]) != set(canonical["period_index"]):
        missing = sorted(set(canonical["period_index"]) - set(panel_dates["period_index"]))
        extra = sorted(set(panel_dates["period_index"]) - set(canonical["period_index"]))
        raise ValueError(f"panel_official_period_key_mismatch missing={missing} extra={extra}")
    checked = canonical.merge(
        panel_dates,
        on="period_index",
        suffixes=("_official", "_panel"),
        validate="one_to_one",
    )
    for column in date_columns:
        if not checked[f"{column}_official"].equals(checked[f"{column}_panel"]):
            periods = checked.loc[
                checked[f"{column}_official"].ne(checked[f"{column}_panel"]),
                "period_index",
            ].tolist()
            raise ValueError(
                f"panel_official_period_date_mismatch column={column} periods={periods[:5]}"
            )
    return canonical.sort_values("period_index").reset_index(drop=True)


def rank_ic_periods(assigned: pd.DataFrame, minimum_count: int = 25) -> pd.DataFrame:
    rows = []
    for period, group in assigned.groupby("period_index", sort=True):
        target = group.loc[group["signal_target_member"]]
        valid = target.loc[target["label_available"]]
        coverage = len(valid) / len(target) if len(target) else 0.0
        reason = ""
        if len(valid) < minimum_count:
            reason = "insufficient_joint_count"
        elif coverage < 0.80:
            reason = "insufficient_label_coverage"
        elif valid["mom60"].nunique() < 2:
            reason = "constant_factor"
        elif valid["forward_return"].nunique() < 2:
            reason = "constant_return"
        raw = (
            float(valid["mom60"].corr(valid["forward_return"], method="spearman"))
            if not reason
            else math.nan
        )
        if not reason and not np.isfinite(raw):
            reason = "non_finite_correlation"
            raw = math.nan
        rows.append(
            {
                "period_index": period,
                "signal_date": group.iloc[0]["signal_as_of_date"],
                "rebalance_date": group.iloc[0]["rebalance_date"],
                "next_rebalance_date": group.iloc[0]["next_rebalance_date"],
                "eligible_count": int(group["baseline_eligible"].sum()),
                "valid_factor_count": int(_finite(group["mom60"]).sum()),
                "valid_forward_return_count": int(group["label_available"].sum()),
                "rankic_target_count": len(target),
                "rankic_valid_label_count": len(valid),
                "rankic_label_coverage": coverage,
                "raw_rank_ic": raw,
                "oriented_rank_ic": -raw if np.isfinite(raw) else math.nan,
                "absolute_rank_ic": abs(raw) if np.isfinite(raw) else math.nan,
                "rank_ic_valid": bool(np.isfinite(raw)),
                "failure_reason": reason,
                "sample_role": "historical_seen",
                "formal_alpha_conclusion_allowed": False,
                "orientation_alpha_increment": 0,
            }
        )
    return pd.DataFrame(rows)


def lineage_audit(assigned: pd.DataFrame) -> pd.DataFrame:
    """Read-only truth table for the four legacy membership/label fields."""
    columns = [
        "baseline_eligible",
        "signal_sample_member",
        "evaluation_sample_member",
        "label_available",
    ]
    return (
        assigned.groupby(["period_index", *columns], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
    )


def cross_sectional_diagnostics(assigned: pd.DataFrame) -> pd.DataFrame:
    """Descriptive oriented Q5-Q1 spread; never a NAV or primary metric."""
    rows = []
    for period, group in assigned.groupby("period_index", sort=True):
        returns = {}
        roles = {}
        for quantile in (1, 5):
            target = group.loc[
                group["signal_target_member"] & group["oriented_quantile"].eq(quantile)
            ]
            valid = target.loc[target["label_available"]]
            coverage = len(valid) / len(target) if len(target) else 0.0
            usable = len(valid) >= 4 and coverage >= 0.80
            returns[quantile] = float(valid["forward_return"].mean()) if usable else math.nan
            roles[quantile] = (
                "complete_label_diagnostic"
                if usable and coverage == 1.0
                else "partial_label_diagnostic"
                if usable
                else "invalid_diagnostic"
            )
        rows.append(
            {
                "period_index": period,
                "metric_role": "cross_sectional_factor_spread_diagnostic",
                "result_role": "partial_label_diagnostic"
                if "partial_label_diagnostic" in roles.values()
                else "complete_label_diagnostic"
                if all(role == "complete_label_diagnostic" for role in roles.values())
                else "invalid_diagnostic",
                "oriented_q5_gross_return": returns[5],
                "oriented_q1_gross_return": returns[1],
                "oriented_q5_minus_q1_gross_spread": returns[5] - returns[1],
                "is_executable_strategy": False,
                "formal_alpha_evidence": False,
            }
        )
    return pd.DataFrame(rows)


def _target_weights(group: pd.DataFrame, portfolio: str) -> dict[str, float]:
    selected = group.loc[group["signal_target_member"]]
    if portfolio == "oriented_Q5_long_only":
        selected = selected.loc[selected["oriented_quantile"].eq(5)]
    if selected.empty:
        return {}
    weight = 1.0 / len(selected)
    return dict.fromkeys(selected["stock_code"], weight)


def _turnover(
    target: dict[str, float], previous: dict[str, float] | None, previous_returns: dict[str, float]
) -> float:
    if previous is None:
        return 1.0
    total = sum(weight * (1 + previous_returns[code]) for code, weight in previous.items())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("non_positive_drift_value")
    drifted = {
        code: weight * (1 + previous_returns[code]) / total for code, weight in previous.items()
    }
    return 0.5 * sum(
        abs(target.get(code, 0.0) - drifted.get(code, 0.0))
        for code in target.keys() | drifted.keys()
    )


def long_only_paths(assigned: pd.DataFrame, cost_rate: float = PRIMARY_COST_RATE) -> pd.DataFrame:
    """Build Q5 and universe paths; one missing target return breaks both primary paths."""
    rows: list[dict[str, object]] = []
    state = {
        name: {"weights": None, "returns": {}, "nav": 1.0, "valid": True}
        for name in ("oriented_Q5_long_only", "signal_universe_long_only")
    }
    for period, group in assigned.groupby("period_index", sort=True):
        returns = group.set_index("stock_code")["forward_return"].to_dict()
        for name, item in state.items():
            weights = _target_weights(group, name)
            complete = bool(weights) and all(np.isfinite(returns[code]) for code in weights)
            if not item["valid"]:
                status = "broken_prior_path"
            elif not complete:
                status = "invalid_missing_target_return" if weights else "invalid_empty_target"
                item["valid"] = False
            else:
                status = "ok"
            if status != "ok":
                rows.append(
                    {
                        "period_index": period,
                        "portfolio": name,
                        "period_portfolio_status": status,
                        "primary_portfolio_metric_valid": False,
                        "target_count": len(weights),
                    }
                )
                continue

            turnover = _turnover(weights, item["weights"], item["returns"])
            gross = sum(weights[code] * returns[code] for code in weights)
            cost = turnover * cost_rate
            net = gross - cost
            item["nav"] *= 1 + net
            item["weights"], item["returns"] = weights, returns
            rows.append(
                {
                    "period_index": period,
                    "portfolio": name,
                    "period_portfolio_status": "ok",
                    "primary_portfolio_metric_valid": True,
                    "target_count": len(weights),
                    "gross_return": gross,
                    "one_way_turnover": turnover,
                    "cost_rate": cost_rate,
                    "transaction_cost": cost,
                    "net_return": net,
                    "net_nav": item["nav"],
                }
            )
    return pd.DataFrame(rows)


def primary_relative_wealth(paths: pd.DataFrame) -> float:
    if paths.empty or not paths["primary_portfolio_metric_valid"].all():
        return math.nan
    terminal = paths.sort_values("period_index").groupby("portfolio").tail(1).set_index("portfolio")
    required = {"oriented_Q5_long_only", "signal_universe_long_only"}
    if set(terminal.index) != required:
        return math.nan
    return float(
        terminal.loc["oriented_Q5_long_only", "net_nav"]
        / terminal.loc["signal_universe_long_only", "net_nav"]
        - 1
    )


def endpoint_max_drawdown(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="coerce")
    if values.isna().any():
        return math.nan
    nav = pd.concat([pd.Series([1.0]), (1 + values).cumprod()], ignore_index=True)
    return float((nav / nav.cummax() - 1).min())


def moving_block_lower_bound(
    values: pd.Series, block_length: int = 3, resamples: int = 10_000, seed: int = 20260721
) -> float:
    data = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    if len(data) < MIN_PERIODS:
        return math.nan
    rng = np.random.default_rng(seed)
    blocks = math.ceil(len(data) / block_length)
    starts = rng.integers(0, len(data), size=(resamples, blocks))
    offsets = np.arange(block_length)
    samples = data[(starts[..., None] + offsets) % len(data)].reshape(resamples, -1)[:, : len(data)]
    return float(np.quantile(samples.mean(axis=1), 0.05))


def conclusion_status(
    oriented_rank_ic: pd.Series,
    relative_wealth: float,
    *,
    sample_role: str,
    all_required_qa_passed: bool,
    primary_portfolio_path_valid: bool,
) -> str:
    if sample_role != "prospective_test":
        return "descriptive_only"
    values = pd.to_numeric(oriented_rank_ic, errors="coerce").dropna()
    if (
        len(values) < MIN_PERIODS
        or not all_required_qa_passed
        or not primary_portfolio_path_valid
        or not np.isfinite(relative_wealth)
        or not np.isfinite(values).all()
    ):
        return "inconclusive"
    bootstrap_lower = moving_block_lower_bound(values)
    if not np.isfinite(bootstrap_lower):
        return "inconclusive"
    supported = (
        values.mean() >= PRIMARY_INFORMATION_THRESHOLD
        and values.median() > 0
        and (values > 0).mean() > 0.50
        and relative_wealth > 0
        and bootstrap_lower > 0
    )
    return "supported" if supported else "not_supported"


def verify_frozen_hashes(root: Path) -> dict[str, bool]:
    return {
        relative: path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
        for relative, expected in FROZEN_HASHES.items()
        for path in [root / relative]
    }


def experiment_registry() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("MOM40", "return_momentum", True, False),
            ("MOM60", "return_60d", True, False),
            ("MOM80", "return_momentum", True, False),
            ("REV60", "return_60d", True, False),
        ],
        columns=[
            "variant",
            "factor_family_id",
            "distinct_evaluated_variant",
            "statistically_independent",
        ],
    ).assign(
        unique_lookback_variants=3,
        orientation_variants=1,
        orientation_information_increment=0,
    )
