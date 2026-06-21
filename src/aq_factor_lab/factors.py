from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import StockData
from .utils import (
    clean_code,
    finite_mean,
    parse_cache_date,
    parse_cache_datetime,
    percentile_rank_by_date,
    read_cache_csv,
    safe_divide,
    winsorize_by_date,
)

MARKET_CAP_UNIT_CANDIDATES = (1.0, 10_000.0, 100_000_000.0)
CF_YIELD_TARGET = 0.05
MIN_UNIT_GUARD_SAMPLES = 3
DEFAULT_NEUTRAL_FACTORS = [
    "cf_yield",
    "cashflow_quality_score",
    "reversal_20d",
    "volatility_20d",
]
SW_PANEL_COLUMNS = [
    "sw_l1_code",
    "sw_l2_code",
    "sw_l3_code",
    "sw_l1_name",
    "sw_l2_name",
    "sw_l3_name",
    "industry_source",
]
INDUSTRY_METHOD_NOTE = (
    "Factors are cross-sectionally neutralized against total market cap and "
    "Shenwan L1 industry; rows with missing industry or insufficient samples "
    "fall back to market-cap-only neutralization."
)
IC_WEIGHT_FACTORS = [
    "cf_yield_neutral",
    "reversal_20d_neutral",
    "volatility_20d_neutral",
]
DEFAULT_IC_SUMMARY_PATH = Path("data") / "processed" / "ic_summary.csv"
FALLBACK_IC_DIRECTIONS = {
    "cf_yield_neutral": 1.0,
    "reversal_20d_neutral": 1.0,
    "volatility_20d_neutral": -1.0,
}


@dataclass(frozen=True)
class FactorProcessor:
    factor_columns: list[str]
    date_col: str = "date"
    market_cap_col: str = "total_market_cap_cny"
    mad_multiplier: float = 3.5
    min_regression_samples: int = 30
    min_market_cap_regression_samples: int = 20
    neutralization_mode: str = "market_cap_industry"

    def process(self, panel: pd.DataFrame) -> pd.DataFrame:
        result = panel.copy()
        if self.neutralization_mode not in {"market_cap", "market_cap_industry"}:
            raise ValueError("neutralization_mode must be market_cap or market_cap_industry")
        result["factor_neutralization_mode"] = self.neutralization_mode
        if self.market_cap_col in result:
            cap = pd.to_numeric(result[self.market_cap_col], errors="coerce")
            result["ln_total_market_cap"] = np.log(cap.where(cap > 0))
        else:
            result["ln_total_market_cap"] = np.nan
        for factor in self.factor_columns:
            result = self._process_factor(result, factor)
        return result

    def _process_factor(self, frame: pd.DataFrame, factor: str) -> pd.DataFrame:
        result = frame.copy()
        winsor_col = f"{factor}_winsor"
        z_col = f"{factor}_z"
        neutral_col = f"{factor}_neutral"
        status_col = f"{factor}_neutral_status"
        if factor not in result.columns:
            result[winsor_col] = np.nan
            result[z_col] = np.nan
            result[neutral_col] = np.nan
            result[status_col] = "missing_factor"
            return result
        result[winsor_col] = result.groupby(self.date_col, group_keys=False)[factor].transform(self._mad_clip)
        result[z_col] = result.groupby(self.date_col, group_keys=False)[winsor_col].transform(self._zscore)
        result[neutral_col] = np.nan
        result[status_col] = "insufficient_sample"
        neutralized = result.groupby(self.date_col, group_keys=False).apply(
            lambda group: self._neutralize_group(group, z_col, neutral_col, status_col),
            include_groups=False,
        )
        if isinstance(neutralized.index, pd.MultiIndex):
            neutralized = neutralized.reset_index(level=0, drop=True)
        result[[neutral_col, status_col]] = neutralized[[neutral_col, status_col]]
        return result

    def _mad_clip(self, series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        valid = values.dropna()
        if valid.shape[0] < 5:
            return values
        median = valid.median()
        mad = (valid - median).abs().median()
        if pd.isna(mad) or mad <= 0:
            return values
        robust_sigma = 1.4826 * mad
        lower = median - self.mad_multiplier * robust_sigma
        upper = median + self.mad_multiplier * robust_sigma
        return values.clip(lower=lower, upper=upper)

    def _zscore(self, series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        valid = values.dropna()
        if valid.shape[0] < 2:
            return pd.Series(np.nan, index=series.index)
        mean = valid.mean()
        std = valid.std(ddof=0)
        if pd.isna(std) or std <= 1e-12:
            return pd.Series(np.nan, index=series.index)
        return (values - mean) / std

    def _neutralize_group(
        self,
        group: pd.DataFrame,
        z_col: str,
        neutral_col: str,
        status_col: str,
    ) -> pd.DataFrame:
        columns = [z_col, "ln_total_market_cap"]
        if "sw_l1_code" in group:
            columns.append("sw_l1_code")
        result = group[columns].copy()
        result[neutral_col] = np.nan
        result[status_col] = "insufficient_sample"
        if self.neutralization_mode == "market_cap":
            self._apply_market_cap_neutralization(result, z_col, neutral_col, status_col, "ok")
            return result
        if "sw_l1_code" not in result:
            self._apply_market_cap_neutralization(
                result,
                z_col,
                neutral_col,
                status_col,
                "fallback_market_cap_only",
            )
            return result
        if not self._apply_market_cap_industry_neutralization(result, z_col, neutral_col, status_col):
            self._apply_market_cap_neutralization(
                result,
                z_col,
                neutral_col,
                status_col,
                "fallback_market_cap_only",
            )
        return result

    def _apply_market_cap_neutralization(
        self,
        result: pd.DataFrame,
        z_col: str,
        neutral_col: str,
        status_col: str,
        success_status: str,
        row_mask: pd.Series | None = None,
    ) -> bool:
        x = pd.to_numeric(result["ln_total_market_cap"], errors="coerce")
        y = pd.to_numeric(result[z_col], errors="coerce")
        valid = x.notna() & y.notna()
        if row_mask is not None:
            valid &= row_mask
        if int(valid.sum()) < self.min_market_cap_regression_samples or x[valid].nunique() < 2:
            return False
        design = np.column_stack([np.ones(int(valid.sum())), x[valid].to_numpy(dtype=float)])
        beta, *_ = np.linalg.lstsq(design, y[valid].to_numpy(dtype=float), rcond=None)
        fitted = design @ beta
        result.loc[valid, neutral_col] = y[valid].to_numpy(dtype=float) - fitted
        result.loc[valid, status_col] = success_status
        return True

    def _apply_market_cap_industry_neutralization(
        self,
        result: pd.DataFrame,
        z_col: str,
        neutral_col: str,
        status_col: str,
    ) -> bool:
        x = pd.to_numeric(result["ln_total_market_cap"], errors="coerce")
        y = pd.to_numeric(result[z_col], errors="coerce")
        industry = result["sw_l1_code"].astype("string")
        valid = x.notna() & y.notna() & industry.notna() & industry.str.strip().ne("")
        valid_count = int(valid.sum())
        distinct_industries = int(industry[valid].nunique())
        if (
            valid_count < self.min_regression_samples
            or distinct_industries < 2
            or x[valid].nunique() < 2
        ):
            return False
        dummies = pd.get_dummies(industry[valid], drop_first=True, dtype=float)
        design = np.column_stack(
            [
                np.ones(valid_count),
                x[valid].to_numpy(dtype=float),
                dummies.to_numpy(dtype=float),
            ]
        )
        if valid_count <= design.shape[1] + 5:
            return False
        beta, *_ = np.linalg.lstsq(design, y[valid].to_numpy(dtype=float), rcond=None)
        fitted = design @ beta
        result.loc[valid, neutral_col] = y[valid].to_numpy(dtype=float) - fitted
        result.loc[valid, status_col] = "ok"
        missing_industry = x.notna() & y.notna() & ~valid
        self._apply_market_cap_neutralization(
            result,
            z_col,
            neutral_col,
            status_col,
            "fallback_market_cap_only",
            row_mask=missing_industry,
        )
        return True


def build_factor_panel(
    stocks: list[StockData],
    holding_days: int = 20,
    min_history_days: int = 120,
    industry_sw: pd.DataFrame | None = None,
    industry_warnings_rows: list[dict[str, object]] | None = None,
    ic_summary_path: Path | str | None = DEFAULT_IC_SUMMARY_PATH,
    ic_summary_source_label: str | None = None,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    eligible = [stock for stock in stocks if stock.price.shape[0] >= min_history_days]
    if not eligible:
        return pd.DataFrame()
    date_series = [stock.price["date"] for stock in eligible if "date" in stock.price]
    if not date_series:
        return pd.DataFrame()
    all_dates = pd.concat(date_series, ignore_index=True)
    obs_dates = month_end_trading_dates(all_dates)
    for stock in eligible:
        if stock.price.shape[0] < min_history_days:
            continue
        panel = stock_observation_panel(stock, holding_days=holding_days, obs_dates=obs_dates)
        if not panel.empty:
            rows.append(panel)
    if not rows:
        return pd.DataFrame()
    raw = pd.concat(rows, ignore_index=True)
    raw = attach_industry_sw(raw, industry_sw, warnings_rows=industry_warnings_rows)
    raw = apply_cf_yield_unit_guard(raw)
    scored = score_cross_section(raw)
    processed = FactorProcessor(DEFAULT_NEUTRAL_FACTORS).process(scored)
    return add_composite_alpha(
        processed,
        ic_summary_path=ic_summary_path,
        ic_summary_source_label=ic_summary_source_label,
    )


def load_industry_sw_cache(cache_dir: Path, codes: list[str] | None = None) -> pd.DataFrame:
    industry_dir = cache_dir / "industry_sw"
    if not industry_dir.exists():
        return pd.DataFrame()
    wanted = {clean_code(code) for code in codes} if codes else None
    frames = []
    for path in sorted(industry_dir.glob("*.csv")):
        if wanted is not None and clean_code(path.stem) not in wanted:
            continue
        frame = read_cache_csv(path)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def attach_industry_sw(
    panel: pd.DataFrame,
    industry_sw: pd.DataFrame | None,
    warnings_rows: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    result = panel.copy()
    for column in SW_PANEL_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    result["industry_source"] = "missing"
    if result.empty or industry_sw is None or industry_sw.empty:
        return result

    industry = normalize_industry_sw_for_join(industry_sw)
    if industry.empty:
        return result
    result["code"] = result["code"].map(clean_code)
    result_dates = parse_cache_date(result["date"])
    for code, row_indexes in result.groupby("code").groups.items():
        history = industry[industry["code"] == code]
        if history.empty:
            continue
        history = history.sort_values(["in_date", "updated_at"])
        for row_index in row_indexes:
            obs_date = result_dates.loc[row_index]
            if pd.isna(obs_date):
                continue
            active = history[
                (history["in_date"].notna())
                & (history["in_date"] <= obs_date)
                & (history["out_date"].isna() | (history["out_date"] >= obs_date))
            ]
            if active.empty:
                continue
            ambiguous = active.shape[0] > 1
            if ambiguous and warnings_rows is not None:
                warnings_rows.append(
                    {
                        "warning_type": "ambiguous_industry_match",
                        "code": code,
                        "date": obs_date.date().isoformat(),
                        "match_count": int(active.shape[0]),
                        "resolution": "kept latest in_date then updated_at",
                    }
                )
            # Industry memberships can overlap after reclassification; latest effective date is stable.
            selected = active.sort_values(["in_date", "updated_at"]).iloc[-1]
            result.loc[row_index, "sw_l1_code"] = selected.get("sw_l1_code", pd.NA)
            result.loc[row_index, "sw_l2_code"] = selected.get("sw_l2_code", pd.NA)
            result.loc[row_index, "sw_l3_code"] = selected.get("sw_l3_code", pd.NA)
            result.loc[row_index, "sw_l1_name"] = selected.get("sw_l1_name", pd.NA)
            result.loc[row_index, "sw_l2_name"] = selected.get("sw_l2_name", pd.NA)
            result.loc[row_index, "sw_l3_name"] = selected.get("sw_l3_name", pd.NA)
            result.loc[row_index, "industry_source"] = "ambiguous" if ambiguous else "shenwan_l1"
    return result


def normalize_industry_sw_for_join(industry_sw: pd.DataFrame) -> pd.DataFrame:
    result = industry_sw.copy()
    aliases = {
        "sw_l1_code": "l1_index_code",
        "sw_l2_code": "l2_index_code",
        "sw_l3_code": "l3_index_code",
        "sw_l1_name": "l1_industry_name",
        "sw_l2_name": "l2_industry_name",
        "sw_l3_name": "l3_industry_name",
    }
    for canonical, legacy in aliases.items():
        if canonical not in result and legacy in result:
            result[canonical] = result[legacy]
    required = ["code", "sw_l1_code", "sw_l2_code", "sw_l3_code", "in_date", "out_date"]
    if any(column not in result for column in required):
        return pd.DataFrame()
    result["code"] = result["code"].map(clean_code)
    for column in ["sw_l1_code", "sw_l2_code", "sw_l3_code", "sw_l1_name", "sw_l2_name", "sw_l3_name"]:
        if column not in result:
            result[column] = pd.NA
        result[column] = result[column].astype("string")
    result["in_date"] = parse_cache_date(result["in_date"])
    result["out_date"] = parse_cache_date(result["out_date"])
    if "updated_at" in result:
        result["updated_at"] = parse_cache_datetime(result["updated_at"])
    else:
        result["updated_at"] = pd.NaT
    return result.dropna(subset=["code", "in_date"]).reset_index(drop=True)


def stock_observation_panel(
    stock: StockData,
    holding_days: int = 20,
    obs_dates: pd.Series | None = None,
) -> pd.DataFrame:
    price = stock.price.copy()
    if price.empty:
        return pd.DataFrame()
    price = price.sort_values("date").reset_index(drop=True)
    obs_dates = month_end_trading_dates(price["date"]) if obs_dates is None else parse_cache_date(obs_dates).dropna()
    if obs_dates.empty:
        return pd.DataFrame()
    price_features = make_price_features(price, holding_days)
    financial = make_financial_features(stock.cashflow, stock.profit)
    moneyflow = make_moneyflow_features(stock.moneyflow, price, stock.float_market_cap)

    rows = []
    for obs_date in obs_dates:
        p = latest_asof(price_features, obs_date, "date")
        if p is None or pd.isna(p.get("forward_return_20d")):
            continue
        fin = latest_asof(financial, obs_date, "available_date") if not financial.empty else None
        mf = latest_asof(moneyflow, obs_date, "date") if not moneyflow.empty else None
        rows.append(
            {
                "date": obs_date,
                "code": stock.code,
                "name": stock.name,
                "industry": stock.industry,
                "market_cap": value_or_fallback(p, "total_market_cap", stock.market_cap),
                "float_market_cap": stock.float_market_cap,
                "total_market_cap": value_or_nan(p, "total_market_cap"),
                "circulating_market_cap": value_or_nan(p, "circulating_market_cap"),
                "forward_return_20d": p.get("forward_return_20d"),
                "momentum_20d": p.get("momentum_20d"),
                "reversal_20d": p.get("reversal_20d"),
                "volatility_20d": p.get("volatility_20d"),
                "turnover_20d": p.get("turnover_20d"),
                "amount": value_or_nan(p, "amount"),
                "amount_20d": value_or_nan(p, "amount_20d"),
                "high": value_or_nan(p, "high"),
                "low": value_or_nan(p, "low"),
                "adjusted_close": value_or_nan(p, "adjusted_close"),
                "adj_factor": value_or_nan(p, "adj_factor"),
                "return_source": p.get("return_source"),
                "operating_cashflow": value_or_nan(fin, "operating_cashflow"),
                "operating_cashflow_reported": value_or_nan(fin, "operating_cashflow_reported"),
                "operating_cashflow_ttm": value_or_nan(fin, "operating_cashflow_ttm"),
                "revenue_ttm": value_or_nan(fin, "revenue_ttm"),
                "parent_net_profit_ttm": value_or_nan(fin, "parent_net_profit_ttm"),
                "cf_to_revenue": value_or_nan(fin, "cf_to_revenue"),
                "cf_to_profit": value_or_nan(fin, "cf_to_profit"),
                "ocf_yoy": value_or_nan(fin, "ocf_yoy"),
                "moneyflow_5d_amount_ratio": value_or_nan(mf, "moneyflow_5d_amount_ratio"),
                "moneyflow_20d_amount_ratio": value_or_nan(mf, "moneyflow_20d_amount_ratio"),
                "moneyflow_5d_pct": value_or_nan(mf, "moneyflow_5d_pct"),
                "moneyflow_20d_pct": value_or_nan(mf, "moneyflow_20d_pct"),
                "moneyflow_20d_float_mv_ratio": value_or_nan(mf, "moneyflow_20d_float_mv_ratio"),
            }
        )
    return pd.DataFrame(rows)


def month_end_trading_dates(dates: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"date": parse_cache_date(dates).dropna()})
    if frame.empty:
        return pd.Series(dtype="datetime64[ns]")
    return frame.groupby(frame["date"].dt.to_period("M"))["date"].max().reset_index(drop=True)


def make_price_features(price: pd.DataFrame, holding_days: int) -> pd.DataFrame:
    df = price.copy().sort_values("date").reset_index(drop=True)
    df = df.drop(columns=["code"], errors="ignore")
    df["code"] = "__single_stock__"
    df = add_grouped_price_momentum_features(df, holding_days=holding_days)
    return df.drop(columns=["code"])


def add_grouped_price_momentum_features(frame: pd.DataFrame, holding_days: int = 20) -> pd.DataFrame:
    """Add price return features with all time-series windows isolated by code."""
    if frame.empty:
        return frame.copy()
    missing = {"code", "date"} - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {','.join(sorted(missing))}")
    result = frame.copy().sort_values(["code", "date"]).reset_index(drop=True)
    return_base, return_source = _select_return_base(result)
    result["adjusted_close"] = (
        pd.to_numeric(result["adjusted_close"], errors="coerce")
        if "adjusted_close" in result
        else pd.Series(np.nan, index=result.index, dtype="float64")
    )
    if return_source == "close_times_adj_factor":
        result["adjusted_close"] = return_base
    result["return_base"] = return_base.where(return_base > 0)

    grouped_return_base = result.groupby("code", group_keys=False)["return_base"]
    result["forward_return_20d"] = grouped_return_base.transform(lambda series: series.shift(-holding_days) / series - 1.0)
    result["momentum_20d"] = grouped_return_base.transform(lambda series: series / series.shift(20) - 1.0)
    result["reversal_20d"] = -result["momentum_20d"]
    daily_return = grouped_return_base.transform(lambda series: series.pct_change(fill_method=None))
    result["volatility_20d"] = daily_return.groupby(result["code"], group_keys=False).transform(
        lambda series: series.rolling(20, min_periods=10).std()
    )

    turnover = (
        pd.to_numeric(result["turnover"], errors="coerce")
        if "turnover" in result
        else pd.Series(np.nan, index=result.index, dtype="float64")
    )
    result["turnover_20d"] = turnover.groupby(result["code"], group_keys=False).transform(
        lambda series: series.rolling(20, min_periods=10).mean()
    )
    amount = (
        pd.to_numeric(result["amount"], errors="coerce")
        if "amount" in result
        else pd.Series(np.nan, index=result.index, dtype="float64")
    )
    result["amount_20d"] = amount.groupby(result["code"], group_keys=False).transform(
        lambda series: series.rolling(20, min_periods=10).mean()
    )
    result["return_source"] = return_source
    return result


def _select_return_base(frame: pd.DataFrame) -> tuple[pd.Series, str]:
    adjusted = (
        pd.to_numeric(frame["adjusted_close"], errors="coerce")
        if "adjusted_close" in frame
        else pd.Series(np.nan, index=frame.index, dtype="float64")
    )
    if adjusted.gt(0).any():
        return adjusted, "adjusted_close"
    if {"close", "adj_factor"}.issubset(frame.columns):
        close = pd.to_numeric(frame["close"], errors="coerce")
        adj_factor = pd.to_numeric(frame["adj_factor"], errors="coerce")
        constructed = close * adj_factor
        if constructed.gt(0).any():
            return constructed, "close_times_adj_factor"
    if "total_market_cap" in frame:
        cap = pd.to_numeric(frame["total_market_cap"], errors="coerce")
    else:
        cap = pd.Series(np.nan, index=frame.index, dtype="float64")
    frame["total_market_cap"] = cap.where(cap > 0)
    return frame["total_market_cap"], "total_market_cap"


def add_composite_alpha(
    panel: pd.DataFrame,
    ic_summary_path: Path | str | None = DEFAULT_IC_SUMMARY_PATH,
    ic_summary_source_label: str | None = None,
) -> pd.DataFrame:
    result = panel.copy()
    required = IC_WEIGHT_FACTORS
    ic_weights = load_ic_composite_weights(ic_summary_path, source_label=ic_summary_source_label)
    result["composite_alpha"] = np.nan
    result["composite_alpha_ic_weighted"] = np.nan
    result["ic_weight_source"] = ic_weights["source"]
    for factor in required:
        result[f"ic_rank_ic_mean_{factor}"] = ic_weights["rank_ic_mean"][factor]
        result[f"ic_weight_{factor}"] = ic_weights["weight"][factor]
        result[f"ic_direction_{factor}"] = ic_weights["direction"][factor]
    if not all(column in result for column in required):
        return result
    components = result[required].apply(pd.to_numeric, errors="coerce")
    valid = components.notna().all(axis=1)
    result.loc[valid, "composite_alpha"] = (
        components.loc[valid, "cf_yield_neutral"]
        + components.loc[valid, "reversal_20d_neutral"]
        - components.loc[valid, "volatility_20d_neutral"]
    )
    weighted = pd.Series(0.0, index=components.index)
    for factor in required:
        weighted = weighted + ic_weights["weight"][factor] * ic_weights["direction"][factor] * components[factor]
    result.loc[valid, "composite_alpha_ic_weighted"] = weighted.loc[valid]
    return result


def load_ic_composite_weights(
    ic_summary_path: Path | str | None = DEFAULT_IC_SUMMARY_PATH,
    *,
    source_label: str | None = None,
) -> dict[str, object]:
    if ic_summary_path is None:
        return fallback_ic_composite_weights()
    path = Path(ic_summary_path)
    if not path.exists():
        return fallback_ic_composite_weights()
    try:
        summary = read_cache_csv(path)
    except (OSError, pd.errors.EmptyDataError, UnicodeDecodeError):
        return fallback_ic_composite_weights()
    if summary.empty or not {"factor", "metric", "mean"}.issubset(summary.columns):
        return fallback_ic_composite_weights()
    rank_ic = summary[summary["metric"].astype(str) == "rank_ic"].copy()
    if rank_ic.empty:
        return fallback_ic_composite_weights()
    if not set(IC_WEIGHT_FACTORS).issubset(set(rank_ic["factor"].astype(str))):
        return fallback_ic_composite_weights()
    values = (
        rank_ic.drop_duplicates(subset=["factor"], keep="last")
        .set_index("factor")["mean"]
        .reindex(IC_WEIGHT_FACTORS)
    )
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().all():
        return fallback_ic_composite_weights()
    filled = numeric.fillna(0.0)
    abs_sum = float(filled.abs().sum())
    if abs_sum <= 0:
        return fallback_ic_composite_weights()
    label = source_label or str(path).replace("\\", "/")
    return {
        "source": label,
        "rank_ic_mean": {factor: float(numeric.loc[factor]) if pd.notna(numeric.loc[factor]) else np.nan for factor in IC_WEIGHT_FACTORS},
        "weight": {factor: float(abs(filled.loc[factor]) / abs_sum) for factor in IC_WEIGHT_FACTORS},
        "direction": {factor: float(np.sign(filled.loc[factor])) for factor in IC_WEIGHT_FACTORS},
    }


def fallback_ic_composite_weights() -> dict[str, object]:
    return {
        "source": "fallback",
        "rank_ic_mean": {factor: np.nan for factor in IC_WEIGHT_FACTORS},
        "weight": {factor: 1.0 / len(IC_WEIGHT_FACTORS) for factor in IC_WEIGHT_FACTORS},
        "direction": FALLBACK_IC_DIRECTIONS.copy(),
    }


def make_financial_features(cashflow: pd.DataFrame, profit: pd.DataFrame) -> pd.DataFrame:
    if cashflow.empty or profit.empty:
        return pd.DataFrame()
    cf = cashflow.copy()
    pr = profit.copy()
    merged = pd.merge(cf, pr, on="report_date", how="inner", suffixes=("_cf", "_profit"))
    if merged.empty:
        return pd.DataFrame()
    announce_cols = [col for col in ["announce_date_cf", "announce_date_profit"] if col in merged.columns]
    if announce_cols:
        merged["announce_date"] = merged[announce_cols].max(axis=1)
    else:
        merged["announce_date"] = pd.NaT
    merged = merged.sort_values("report_date").reset_index(drop=True)
    merged["available_date"] = merged["announce_date"].fillna(merged["report_date"] + pd.Timedelta(days=120))
    merged["operating_cashflow_reported"] = merged["operating_cashflow"]
    merged["operating_cashflow_ttm"] = ttm_from_cumulative_flow(merged["operating_cashflow"], merged["report_date"])
    merged["revenue_ttm"] = ttm_from_cumulative_flow(merged["revenue"], merged["report_date"])
    merged["parent_net_profit_ttm"] = ttm_from_cumulative_flow(merged["parent_net_profit"], merged["report_date"])
    merged["operating_cashflow"] = merged["operating_cashflow_ttm"]
    merged["cf_to_revenue"] = safe_divide(merged["operating_cashflow_ttm"], merged["revenue_ttm"])
    merged["cf_to_profit"] = safe_divide(
        merged["operating_cashflow_ttm"],
        merged["parent_net_profit_ttm"],
        positive_denominator=True,
    )
    merged["ocf_yoy"] = safe_divide(
        merged["operating_cashflow_ttm"] - merged["operating_cashflow_ttm"].shift(4),
        merged["operating_cashflow_ttm"].shift(4).abs(),
    )
    return merged[
        [
            "report_date",
            "available_date",
            "operating_cashflow_reported",
            "operating_cashflow",
            "operating_cashflow_ttm",
            "revenue_ttm",
            "parent_net_profit_ttm",
            "cf_to_revenue",
            "cf_to_profit",
            "ocf_yoy",
        ]
    ]


def ttm_from_cumulative_flow(values: pd.Series, report_dates: pd.Series) -> pd.Series:
    """Convert cumulative financial statement flows to trailing-four-quarter sums."""
    numeric = pd.to_numeric(values, errors="coerce")
    dates = pd.to_datetime(report_dates, errors="coerce")
    frame = pd.DataFrame({"value": numeric, "date": dates}, index=values.index)
    year = frame["date"].dt.year
    previous = frame.groupby(year, dropna=False)["value"].shift(1)
    quarterly = frame["value"] - previous
    quarterly = quarterly.where(previous.notna(), frame["value"])
    return quarterly.rolling(4, min_periods=4).sum()


def apply_cf_yield_unit_guard(raw: pd.DataFrame) -> pd.DataFrame:
    result = raw.copy()
    result["total_market_cap_cny"] = np.nan
    result["cf_yield"] = np.nan
    result["market_cap_unit_multiplier"] = np.nan
    result["cf_yield_unit_guard_status"] = "failed_or_insufficient_sample"
    cashflow_col = "operating_cashflow_ttm" if "operating_cashflow_ttm" in result else "operating_cashflow"
    if cashflow_col not in result or "total_market_cap" not in result:
        return result

    operating_cashflow = pd.to_numeric(result[cashflow_col], errors="coerce")
    market_cap = pd.to_numeric(result["total_market_cap"], errors="coerce")
    valid = operating_cashflow.notna() & market_cap.gt(0)
    if int(valid.sum()) < MIN_UNIT_GUARD_SAMPLES:
        return result

    best_multiplier: float | None = None
    best_distance = np.inf
    for multiplier in MARKET_CAP_UNIT_CANDIDATES:
        candidate = (operating_cashflow[valid].abs() / (market_cap[valid] * multiplier)).replace(
            [np.inf, -np.inf],
            np.nan,
        )
        median_yield = candidate.dropna().median()
        if pd.isna(median_yield) or median_yield <= 0:
            continue
        distance = abs(np.log10(float(median_yield)) - np.log10(CF_YIELD_TARGET))
        if distance < best_distance:
            best_distance = distance
            best_multiplier = multiplier

    if best_multiplier is None:
        return result

    total_market_cap_cny = market_cap * best_multiplier
    result["total_market_cap_cny"] = total_market_cap_cny
    result["cf_yield"] = safe_divide(operating_cashflow, total_market_cap_cny, positive_denominator=True)
    result["market_cap_unit_multiplier"] = best_multiplier
    result["cf_yield_unit_guard_status"] = "ok"
    return result


def make_moneyflow_features(moneyflow: pd.DataFrame, price: pd.DataFrame, float_market_cap: float | None = None) -> pd.DataFrame:
    if moneyflow.empty:
        return pd.DataFrame()
    mf = moneyflow.copy().sort_values("date").reset_index(drop=True)
    price_amount = price[["date", "amount"]].copy() if "amount" in price.columns else pd.DataFrame(columns=["date", "amount"])
    mf = pd.merge(mf, price_amount, on="date", how="left")
    mf["moneyflow_5d_amount_ratio"] = rolling_ratio(mf["main_net_inflow"], mf["amount"], 5)
    mf["moneyflow_20d_amount_ratio"] = rolling_ratio(mf["main_net_inflow"], mf["amount"], 20)
    mf["moneyflow_5d_pct"] = mf["main_net_pct"].rolling(5, min_periods=3).mean()
    mf["moneyflow_20d_pct"] = mf["main_net_pct"].rolling(20, min_periods=10).mean()
    if float_market_cap and float_market_cap > 0:
        mf["moneyflow_20d_float_mv_ratio"] = mf["main_net_inflow"].rolling(20, min_periods=10).sum() / float_market_cap
    else:
        mf["moneyflow_20d_float_mv_ratio"] = np.nan
    return mf


def rolling_ratio(numerator: pd.Series, denominator: pd.Series, window: int) -> pd.Series:
    num = numerator.rolling(window, min_periods=max(3, window // 2)).sum()
    den = denominator.rolling(window, min_periods=max(3, window // 2)).sum()
    return safe_divide(num, den)


def score_cross_section(raw: pd.DataFrame) -> pd.DataFrame:
    components = [
        "cf_to_revenue",
        "cf_to_profit",
        "ocf_yoy",
        "cf_yield",
        "moneyflow_5d_amount_ratio",
        "moneyflow_20d_amount_ratio",
        "moneyflow_5d_pct",
        "moneyflow_20d_pct",
        "moneyflow_20d_float_mv_ratio",
    ]
    scored = winsorize_by_date(raw, components)
    scored = percentile_rank_by_date(scored, components)
    scored["cashflow_quality_score"] = finite_mean(
        [
            scored.get("cf_to_revenue_rank"),
            scored.get("cf_to_profit_rank"),
            scored.get("ocf_yoy_rank"),
            scored.get("cf_yield_rank"),
        ]
    )
    scored["main_moneyflow_score"] = finite_mean(
        [
            scored.get("moneyflow_5d_amount_ratio_rank"),
            scored.get("moneyflow_20d_amount_ratio_rank"),
            scored.get("moneyflow_5d_pct_rank"),
            scored.get("moneyflow_20d_pct_rank"),
            scored.get("moneyflow_20d_float_mv_ratio_rank"),
        ]
    )
    scored.loc[
        scored[["cf_to_revenue", "cf_to_profit", "ocf_yoy", "cf_yield"]].notna().sum(axis=1) == 0,
        "cashflow_quality_score",
    ] = np.nan
    scored.loc[
        scored[
            [
                "moneyflow_5d_amount_ratio",
                "moneyflow_20d_amount_ratio",
                "moneyflow_5d_pct",
                "moneyflow_20d_pct",
                "moneyflow_20d_float_mv_ratio",
            ]
        ]
        .notna()
        .sum(axis=1)
        == 0,
        "main_moneyflow_score",
    ] = np.nan
    return scored.sort_values(["date", "code"]).reset_index(drop=True)


def latest_asof(df: pd.DataFrame, obs_date: pd.Timestamp, date_col: str) -> pd.Series | None:
    if df.empty or date_col not in df.columns:
        return None
    eligible = df[df[date_col] <= obs_date]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


def value_or_nan(row: pd.Series | None, key: str) -> float:
    if row is None or key not in row:
        return float("nan")
    return row[key]


def value_or_fallback(row: pd.Series | None, key: str, fallback: float | None) -> float | None:
    value = value_or_nan(row, key)
    if pd.notna(value):
        return value
    return fallback
