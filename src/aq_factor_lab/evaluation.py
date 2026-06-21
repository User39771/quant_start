from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import annualized_ir, parse_cache_date

FACTOR_COLUMNS = [
    "cashflow_quality_score_neutral",
    "cf_yield_neutral",
    "reversal_20d_neutral",
    "volatility_20d_neutral",
    "composite_alpha",
    "composite_alpha_ic_weighted",
    "main_moneyflow_score",
]
FACTOR_CORRELATION_COLUMNS = [
    "cf_yield_neutral",
    "reversal_20d_neutral",
    "volatility_20d_neutral",
]


def evaluate_factor_panel(panel: pd.DataFrame, group_count: int = 5) -> dict[str, pd.DataFrame]:
    if panel.empty:
        return {
            "coverage": pd.DataFrame(),
            "ic": pd.DataFrame(),
            "ic_summary": pd.DataFrame(),
            "groups": pd.DataFrame(),
            "yearly_ic": pd.DataFrame(),
            "correlations": pd.DataFrame(),
            "factor_correlation": pd.DataFrame(),
        }
    ic = ic_table(panel)
    return {
        "coverage": coverage_table(panel),
        "ic": ic,
        "ic_summary": ic_summary(ic),
        "groups": group_return_table(panel, group_count),
        "yearly_ic": yearly_ic_table(ic),
        "correlations": correlation_table(panel),
        "factor_correlation": factor_correlation_table(panel),
    }


def coverage_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date, group in panel.groupby("date"):
        row = {"date": date, "stocks": group["code"].nunique()}
        for factor in FACTOR_COLUMNS:
            row[f"{factor}_coverage"] = group[factor].notna().mean() if factor in group else np.nan
            row[f"{factor}_count"] = group[factor].notna().sum() if factor in group else 0
        rows.append(row)
    return pd.DataFrame(rows).sort_values("date")


def ic_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date, group in panel.groupby("date"):
        row = {"date": date}
        for factor in FACTOR_COLUMNS:
            valid = group[[factor, "forward_return_20d"]].dropna() if factor in group else pd.DataFrame()
            if valid.shape[0] >= 10:
                row[f"{factor}_ic"] = valid[factor].corr(valid["forward_return_20d"], method="pearson")
                row[f"{factor}_rank_ic"] = valid[factor].corr(valid["forward_return_20d"], method="spearman")
                row[f"{factor}_n"] = valid.shape[0]
            else:
                row[f"{factor}_ic"] = np.nan
                row[f"{factor}_rank_ic"] = np.nan
                row[f"{factor}_n"] = valid.shape[0]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("date")


def ic_summary(ic: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for factor in FACTOR_COLUMNS:
        for kind in ["ic", "rank_ic"]:
            col = f"{factor}_{kind}"
            if col not in ic:
                continue
            values = ic[col].dropna()
            rows.append(
                {
                    "factor": factor,
                    "metric": kind,
                    "periods": values.shape[0],
                    "mean": values.mean(),
                    "std": values.std(ddof=1),
                    "ir_annualized": annualized_ir(values.mean(), values.std(ddof=1)),
                    "win_rate": (values > 0).mean() if not values.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def group_return_table(panel: pd.DataFrame, group_count: int = 5) -> pd.DataFrame:
    rows = []
    for factor in FACTOR_COLUMNS:
        if factor not in panel:
            continue
        for date, group in panel.groupby("date"):
            valid = group[[factor, "forward_return_20d"]].dropna()
            if valid.shape[0] < group_count * 3 or valid[factor].nunique() < group_count:
                continue
            try:
                valid = valid.assign(bucket=pd.qcut(valid[factor], group_count, labels=False, duplicates="drop") + 1)
            except ValueError:
                continue
            for bucket, bucket_df in valid.groupby("bucket"):
                rows.append(
                    {
                        "date": date,
                        "factor": factor,
                        "bucket": int(bucket),
                        "mean_forward_return_20d": bucket_df["forward_return_20d"].mean(),
                        "stocks": bucket_df.shape[0],
                    }
                )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    pivot = out.pivot_table(index=["date", "factor"], columns="bucket", values="mean_forward_return_20d")
    if 1 in pivot.columns:
        top_col = max(pivot.columns)
        pivot["long_short"] = pivot[top_col] - pivot[1]
        out = out.merge(pivot[["long_short"]].reset_index(), on=["date", "factor"], how="left")
    return out


def yearly_ic_table(ic: pd.DataFrame) -> pd.DataFrame:
    if ic.empty:
        return ic
    frame = ic.copy()
    frame["year"] = parse_cache_date(frame["date"]).dt.year
    rows = []
    for year, group in frame.groupby("year"):
        row = {"year": year}
        for factor in FACTOR_COLUMNS:
            for kind in ["ic", "rank_ic"]:
                col = f"{factor}_{kind}"
                row[f"{col}_mean"] = group[col].mean() if col in group else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def correlation_table(panel: pd.DataFrame) -> pd.DataFrame:
    candidates = FACTOR_COLUMNS + ["market_cap", "float_market_cap", "turnover_20d", "momentum_20d"]
    cols = [col for col in candidates if col in panel.columns]
    if len(cols) < 2:
        return pd.DataFrame()
    return panel[cols].corr(method="spearman", min_periods=20)


def factor_correlation_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Average per-date cross-sectional Spearman correlations for neutral sub-factors."""
    columns = [column for column in FACTOR_CORRELATION_COLUMNS if column in panel.columns]
    if len(columns) != len(FACTOR_CORRELATION_COLUMNS) or "date" not in panel:
        return pd.DataFrame()

    matrices = []
    for _date, group in panel.groupby("date"):
        cross_section = group[FACTOR_CORRELATION_COLUMNS].apply(pd.to_numeric, errors="coerce")
        matrix = cross_section.corr(method="spearman", min_periods=2)
        matrices.append(matrix)

    if not matrices:
        return pd.DataFrame()
    stacked = pd.concat(matrices, keys=range(len(matrices)))
    averaged = stacked.groupby(level=1).mean(numeric_only=True)
    averaged = averaged.reindex(index=FACTOR_CORRELATION_COLUMNS, columns=FACTOR_CORRELATION_COLUMNS)
    for factor in FACTOR_CORRELATION_COLUMNS:
        averaged.loc[factor, factor] = 1.0
    averaged.index.name = "factor"
    return averaged
