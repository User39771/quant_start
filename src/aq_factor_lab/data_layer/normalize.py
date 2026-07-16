from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from aq_factor_lab.utils import clean_code, exchange_prefix, first_existing_column, to_numeric

from .errors import DataQualityError

PRICE_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover",
    "adjusted",
    "source",
]
INDEX_COLUMNS = [
    "index_code",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover",
    "adjusted",
    "source",
]
UNIVERSE_COLUMNS = [
    "symbol",
    "name",
    "exchange",
    "market",
    "industry",
    "list_date",
    "delist_date",
    "listing_status",
    "asof_quality",
    "source",
]
CONCEPT_COLUMNS = [
    "concept_name",
    "symbol",
    "name",
    "date",
    "requested_date",
    "asof_quality",
    "source",
]


def yyyymmdd(value: str) -> str:
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.strftime("%Y%m%d")


def today_text() -> str:
    return date.today().isoformat()


def _parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%Y-%m-%d", errors="coerce").dt.normalize()


def _price_base(raw: pd.DataFrame, *, symbol: str, adjusted: bool, source: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    date_col = first_existing_column(raw, ["日期", "date"])
    open_col = first_existing_column(raw, ["开盘", "open"])
    high_col = first_existing_column(raw, ["最高", "high"])
    low_col = first_existing_column(raw, ["最低", "low"])
    close_col = first_existing_column(raw, ["收盘", "close"])
    volume_col = first_existing_column(raw, ["成交量", "volume"])
    amount_col = first_existing_column(raw, ["成交额", "amount"])
    turnover_col = first_existing_column(raw, ["换手率", "turnover"])
    missing = [
        name
        for name, col in [
            ("date", date_col),
            ("open", open_col),
            ("high", high_col),
            ("low", low_col),
            ("close", close_col),
        ]
        if col is None
    ]
    if missing:
        raise DataQualityError(f"Cannot identify required price columns: {missing}")
    df = pd.DataFrame(
        {
            "symbol": clean_code(symbol),
            "date": _parse_date(raw[date_col]),
            "open": to_numeric(raw[open_col]),
            "high": to_numeric(raw[high_col]),
            "low": to_numeric(raw[low_col]),
            "close": to_numeric(raw[close_col]),
            "volume": to_numeric(raw[volume_col]) * 100.0 if volume_col else np.nan,
            "amount": to_numeric(raw[amount_col]) if amount_col else np.nan,
            "turnover": to_numeric(raw[turnover_col]) if turnover_col else np.nan,
            "adjusted": bool(adjusted),
            "source": source,
        }
    )
    if df["date"].isna().any():
        raise DataQualityError("Cannot parse one or more price dates")
    return df[PRICE_COLUMNS].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def normalize_daily_price(
    raw: pd.DataFrame,
    *,
    symbol: str,
    start: str,
    end: str,
    adjusted: bool,
) -> pd.DataFrame:
    df = _price_base(
        raw,
        symbol=symbol,
        adjusted=adjusted,
        source="akshare.stock_zh_a_hist",
    )
    if df.empty:
        return df
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    return df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].reset_index(drop=True)


def normalize_index_price(raw: pd.DataFrame, *, index_code: str, start: str, end: str) -> pd.DataFrame:
    base = _price_base(
        raw,
        symbol=index_code,
        adjusted=False,
        source="akshare.index_zh_a_hist",
    )
    if base.empty:
        return pd.DataFrame(columns=INDEX_COLUMNS)
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    base = base[(base["date"] >= start_dt) & (base["date"] <= end_dt)].reset_index(drop=True)
    base.insert(0, "index_code", str(index_code))
    base["symbol"] = str(index_code)
    return base[INDEX_COLUMNS]


def normalize_universe(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    if raw.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS), []
    symbol_col = first_existing_column(raw, ["代码", "SECURITY_CODE", "symbol", "code"])
    name_col = first_existing_column(raw, ["名称", "SECURITY_NAME_ABBR", "name"])
    if symbol_col is None or name_col is None:
        raise DataQualityError(f"Cannot identify universe symbol/name columns: {list(raw.columns)}")

    exchange_col = first_existing_column(raw, ["exchange", "交易所"])
    market_col = first_existing_column(raw, ["market", "市场"])
    industry_col = first_existing_column(raw, ["industry", "行业", "所属行业"])
    list_col = first_existing_column(raw, ["list_date", "上市日期"])
    delist_col = first_existing_column(raw, ["delist_date", "退市日期"])
    status_col = first_existing_column(raw, ["listing_status", "上市状态", "status"])

    symbols = raw[symbol_col].map(clean_code)
    df = pd.DataFrame(
        {
            "symbol": symbols,
            "name": raw[name_col].astype(str),
            "exchange": raw[exchange_col].astype(str) if exchange_col else symbols.map(exchange_prefix),
            "market": raw[market_col].astype(str) if market_col else np.nan,
            "industry": raw[industry_col].astype(str) if industry_col else np.nan,
            "list_date": _parse_date(raw[list_col]) if list_col else pd.NaT,
            "delist_date": _parse_date(raw[delist_col]) if delist_col else pd.NaT,
            "listing_status": raw[status_col].astype(str) if status_col else np.nan,
            "asof_quality": "current_snapshot",
            "source": "akshare.stock_zh_a_spot_em",
        }
    )
    missing_optional = [
        name
        for name, col in [
            ("market", market_col),
            ("industry", industry_col),
            ("list_date", list_col),
            ("delist_date", delist_col),
            ("listing_status", status_col),
        ]
        if col is None
    ]
    warnings = []
    if missing_optional:
        warnings.append(
            {
                "endpoint": "stock_universe",
                "warning_type": "missing_optional_universe_metadata",
                "details": ",".join(missing_optional),
            }
        )
    return df[UNIVERSE_COLUMNS].drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True), warnings


def normalize_concept_members(
    raw: pd.DataFrame,
    *,
    concept_name: str,
    requested_date: str | None,
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=CONCEPT_COLUMNS)
    symbol_col = first_existing_column(raw, ["代码", "SECURITY_CODE", "symbol", "code"])
    name_col = first_existing_column(raw, ["名称", "SECURITY_NAME_ABBR", "name"])
    if symbol_col is None or name_col is None:
        raise DataQualityError(f"Cannot identify concept symbol/name columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "concept_name": concept_name,
            "symbol": raw[symbol_col].map(clean_code),
            "name": raw[name_col].astype(str),
            "date": today_text(),
            "requested_date": requested_date or "",
            "asof_quality": "current_snapshot",
            "source": "akshare.stock_board_concept_cons_em",
        }
    )
    return df[CONCEPT_COLUMNS].drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)
