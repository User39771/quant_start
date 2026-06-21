from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

CACHE_ID_DTYPES = {
    "code": str,
    "db_symbol": str,
    "exchange": str,
    "l1_index_code": str,
    "l2_index_code": str,
    "l3_index_code": str,
    "sw_l1_code": str,
    "sw_l2_code": str,
    "sw_l3_code": str,
}


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def read_cache_csv(path: Path, **kwargs) -> pd.DataFrame:
    dtype = dict(CACHE_ID_DTYPES)
    dtype.update(kwargs.pop("dtype", {}) or {})
    return pd.read_csv(path, dtype=dtype, **kwargs)


def parse_cache_date(series: pd.Series, warnings_list: list[dict[str, object]] | None = None, field: str = "date") -> pd.Series:
    parsed = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    return _parse_cache_fallback(series, parsed, warnings_list, field)


def parse_cache_datetime(
    series: pd.Series,
    warnings_list: list[dict[str, object]] | None = None,
    field: str = "datetime",
) -> pd.Series:
    text = series.astype(str)
    parsed = pd.to_datetime(text, format="%Y-%m-%d %H:%M:%S.%f", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed_seconds = pd.to_datetime(text[missing], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        parsed.loc[missing] = parsed_seconds
    return _parse_cache_fallback(series, parsed, warnings_list, field)


def _parse_cache_fallback(
    source: pd.Series,
    parsed: pd.Series,
    warnings_list: list[dict[str, object]] | None,
    field: str,
) -> pd.Series:
    text = source.astype(str)
    missing = parsed.isna() & text.notna() & ~text.str.strip().isin(["", "nan", "NaT", "None"])
    if missing.any():
        fallback = pd.to_datetime(text[missing], format="mixed", errors="coerce")
        parsed.loc[missing] = fallback
        unresolved = parsed.isna() & missing
        if warnings_list is not None and unresolved.any():
            warnings_list.append(
                {
                    "endpoint": "date_parse",
                    "code": "",
                    "date": "",
                    "duplicate_count": int(unresolved.sum()),
                    "resolution": f"could not parse {field}; set to NaT",
                }
            )
    return parsed


def clean_code(value: object) -> str:
    text = str(value).strip()
    match = re.search(r"(\d{6})", text)
    return match.group(1) if match else text.zfill(6)


def exchange_prefix(code: str) -> str:
    code = clean_code(code)
    if code.startswith(("6", "9")):
        return "SH"
    return "SZ"


def fund_flow_market(code: str) -> str:
    code = clean_code(code)
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("8", "4")):
        return "bj"
    return "sz"


def is_hushen_a(code: str) -> bool:
    code = clean_code(code)
    if not re.fullmatch(r"\d{6}", code):
        return False
    return code.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688"))


def to_numeric(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("--", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    columns = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in columns:
            return columns[key]
    for candidate in candidates:
        for col in df.columns:
            if candidate.strip().lower() in str(col).strip().lower():
                return col
    return None


def safe_divide(numerator: pd.Series, denominator: pd.Series, positive_denominator: bool = False) -> pd.Series:
    den = denominator.astype(float).replace(0, np.nan)
    if positive_denominator:
        den = den.where(den > 1e-8)
    else:
        den = den.where(den.abs() > 1e-8)
    out = numerator.astype(float) / den
    return out.replace([np.inf, -np.inf], np.nan)


def winsorize_by_date(
    df: pd.DataFrame,
    columns: list[str],
    date_col: str = "date",
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col not in result.columns:
            continue
        result[col] = result.groupby(date_col)[col].transform(
            lambda s: s.clip(lower=s.quantile(lower), upper=s.quantile(upper)) if s.notna().sum() >= 5 else s
        )
    return result


def percentile_rank_by_date(df: pd.DataFrame, columns: list[str], date_col: str = "date") -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col in result.columns:
            result[f"{col}_rank"] = result.groupby(date_col)[col].rank(pct=True)
    return result


def finite_mean(values: list[pd.Series | None]) -> pd.Series:
    series = [value for value in values if value is not None]
    if not series:
        return pd.Series(dtype=float)
    frame = pd.concat(series, axis=1)
    return frame.mean(axis=1, skipna=True)


def annualized_ir(mean: float, std: float, periods_per_year: int = 12) -> float:
    if std is None or math.isnan(std) or std == 0:
        return float("nan")
    return mean / std * math.sqrt(periods_per_year)
