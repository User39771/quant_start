from __future__ import annotations

import logging
import random
import ssl
import time
from dataclasses import dataclass
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

from .config import ResearchConfig, yyyymmdd
from .utils import (
    clean_code,
    ensure_dirs,
    exchange_prefix,
    first_existing_column,
    fund_flow_market,
    is_hushen_a,
    parse_cache_date,
    read_cache_csv,
    to_numeric,
)

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())
NETWORK_EXCEPTIONS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.SSLError,
    TimeoutError,
    RemoteDisconnected,
    ssl.SSLError,
)


def safe_fetch(
    label: str,
    fetcher: Callable[[], Any],
    *,
    max_attempts: int = 3,
    base_sleep: float = 0.5,
    random_sleep_range: tuple[float, float] = (0.0, 0.5),
    timeout_seconds: float = 20,
    logger: logging.Logger | None = None,
    after_attempt: Callable[[int], None] | None = None,
) -> Any:
    active_logger = logger or LOGGER
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fetcher()
        except NETWORK_EXCEPTIONS as exc:
            last_error = exc
            active_logger.warning(
                "%s AkShare request attempt %s/%s failed: %s",
                label,
                attempt,
                max_attempts,
                exc,
            )
        except Exception as exc:
            last_error = exc
            active_logger.warning(
                "%s AkShare request attempt %s/%s failed with non-network error: %s",
                label,
                attempt,
                max_attempts,
                exc,
            )
        finally:
            if after_attempt is not None:
                after_attempt(attempt)

        if attempt < max_attempts:
            backoff = base_sleep * (2 ** (attempt - 1))
            jitter = random.uniform(*random_sleep_range) if random_sleep_range else 0
            if backoff + jitter > 0:
                time.sleep(backoff + jitter)

    active_logger.error(
        "%s AkShare request failed after %s attempts within timeout=%ss: %s",
        label,
        max_attempts,
        timeout_seconds,
        last_error,
    )
    raise RuntimeError(
        f"{label} AkShare request failed after {max_attempts} attempts: {last_error}"
    ) from last_error


@dataclass
class StockData:
    code: str
    name: str
    industry: str | None
    market_cap: float | None
    float_market_cap: float | None
    price: pd.DataFrame
    cashflow: pd.DataFrame
    profit: pd.DataFrame
    moneyflow: pd.DataFrame


class AkShareClient:
    def __init__(self, config: ResearchConfig):
        if ak is None:
            raise RuntimeError("AkShare is not installed. Install requirements.txt first.")
        self.config = config
        self.failures: list[dict[str, object]] = []
        self.failed_symbols: list[dict[str, object]] = []
        self.fetch_stats: dict[str, dict[str, int]] = {}
        self._retry_base_sleep = 0.5
        ensure_dirs([config.cache_dir, config.processed_dir, config.report_dir])

    def universe(self) -> pd.DataFrame:
        cache_path = self.config.cache_dir / "universe_spot.csv"
        if self.config.use_cache and cache_path.exists():
            raw = read_cache_csv(cache_path)
        else:
            try:
                raw = self._akshare_fetch("universe", "", ak.stock_zh_a_spot_em)
                raw.to_csv(cache_path, index=False, encoding="utf-8-sig")
            except Exception as exc:
                if not cache_path.exists():
                    raise
                self._bump_stat("universe", "cache_fallback")
                self._record_failure(
                    "", "", "universe", exc, attempts=self._attempts_for("universe"), cache_fallback=True
                )
                raw = read_cache_csv(cache_path)
        return normalize_universe(raw, self.config.max_symbols)

    def stock_data(self, row: pd.Series) -> StockData:
        code = clean_code(row["code"])
        name = str(row.get("name", ""))
        industry = row.get("industry")
        market_cap = row.get("market_cap")
        float_market_cap = row.get("float_market_cap")
        try:
            price = self.price_history(code)
        except Exception as exc:
            self._bump_stat("price", "skipped_required_price")
            self._record_failure(
                code, name, "price", exc, attempts=self._attempts_for("price"), cache_fallback=False
            )
            self._record_failed_symbol(code, name, "price", exc)
            raise

        cashflow = self._optional_endpoint(
            code,
            name,
            "cashflow",
            self.cashflow_statement,
            financial_empty("cashflow"),
        )
        profit = self._optional_endpoint(
            code,
            name,
            "profit",
            self.profit_statement,
            financial_empty("profit"),
        )
        moneyflow = self._optional_endpoint(
            code,
            name,
            "moneyflow",
            self.moneyflow_history,
            moneyflow_empty(),
        )
        return StockData(
            code=code,
            name=name,
            industry=industry if isinstance(industry, str) else None,
            market_cap=float(market_cap) if pd.notna(market_cap) else None,
            float_market_cap=float(float_market_cap) if pd.notna(float_market_cap) else None,
            price=price,
            cashflow=cashflow,
            profit=profit,
            moneyflow=moneyflow,
        )

    def _optional_endpoint(
        self,
        code: str,
        name: str,
        endpoint: str,
        fetcher,
        empty_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        cache_path = self.config.cache_dir / endpoint / f"{code}.csv"
        if self.config.cache_only and not cache_path.exists():
            return empty_frame
        try:
            return fetcher(code)
        except Exception as exc:
            self._record_failure(
                code, name, endpoint, exc, attempts=self._attempts_for(endpoint), cache_fallback=False
            )
            return empty_frame

    def _record_failure(
        self,
        code: str,
        name: str,
        endpoint: str,
        exc: Exception,
        attempts: int | None = None,
        cache_fallback: bool = False,
    ) -> None:
        attempt_text = attempts if attempts is not None else ""
        self.failures.append(
            {
                "code": code,
                "name": name,
                "endpoint": endpoint,
                "error_type": type(exc).__name__,
                "attempts": attempt_text,
                "cache_fallback": cache_fallback,
                "error": f"{exc} (attempts={attempt_text}, cache_fallback={cache_fallback})",
            }
        )

    def _record_failed_symbol(self, code: str, name: str, endpoint: str, exc: Exception) -> None:
        self.failed_symbols.append(
            {
                "code": code,
                "name": name,
                "endpoint": endpoint,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )

    def _read_or_fetch(self, path: Path, fetcher) -> pd.DataFrame:
        if (self.config.use_cache or self.config.cache_only) and path.exists():
            return read_cache_csv(path)
        if self.config.cache_only:
            raise FileNotFoundError(f"Cache file not found for {path.parent.name} {path.stem}: {path}")
        try:
            df = fetcher()
        except Exception as exc:
            if not path.exists():
                raise
            endpoint = path.parent.name
            self._bump_stat(endpoint, "cache_fallback")
            self._record_failure(
                path.stem,
                "",
                endpoint,
                exc,
                attempts=self._attempts_for(endpoint),
                cache_fallback=True,
            )
            return read_cache_csv(path)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return df

    def _akshare_fetch(self, endpoint: str, code: str, fetcher) -> pd.DataFrame:
        max_attempts = self._attempts_for(endpoint)
        label = f"{endpoint} {code}".strip()
        try:
            df = safe_fetch(
                label,
                fetcher,
                max_attempts=max_attempts,
                base_sleep=self._retry_base_sleep,
                random_sleep_range=(0, self._retry_base_sleep),
                timeout_seconds=20,
                after_attempt=lambda _attempt: self._request_throttle(),
            )
        except Exception:
            self._bump_stat(endpoint, "failed")
            raise
        self._bump_stat(endpoint, "success")
        return df

    def _attempts_for(self, endpoint: str) -> int:
        return 5 if endpoint == "price" else 3

    def _retry_delay(self, attempt: int) -> float:
        base = self._retry_base_sleep * (2 ** (attempt - 1))
        jitter = random.uniform(0, self._retry_base_sleep) if self._retry_base_sleep > 0 else 0
        return base + jitter

    def _request_throttle(self) -> None:
        self._sleep(self.config.sleep_seconds)

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def sleep_between_symbols(self) -> None:
        if self.config.sleep_seconds <= 0:
            return
        self._sleep(random.uniform(self.config.sleep_seconds * 0.5, self.config.sleep_seconds * 1.5))

    def _bump_stat(self, endpoint: str, field: str) -> None:
        row = self.fetch_stats.setdefault(
            endpoint,
            {"success": 0, "failed": 0, "cache_fallback": 0, "skipped_required_price": 0},
        )
        row[field] = row.get(field, 0) + 1

    def fetch_summary_frame(self) -> pd.DataFrame:
        columns = ["endpoint", "success", "failed", "cache_fallback", "skipped_required_price"]
        rows = []
        for endpoint, stats in sorted(self.fetch_stats.items()):
            rows.append(
                {
                    "endpoint": endpoint,
                    "success": stats.get("success", 0),
                    "failed": stats.get("failed", 0),
                    "cache_fallback": stats.get("cache_fallback", 0),
                    "skipped_required_price": stats.get("skipped_required_price", 0),
                }
            )
        return pd.DataFrame(rows, columns=columns)

    def failed_symbols_frame(self) -> pd.DataFrame:
        columns = ["code", "name", "endpoint", "error_type", "error"]
        return pd.DataFrame(self.failed_symbols, columns=columns)

    def precache_price(self, code: str, name: str = "") -> bool:
        try:
            self.price_history(clean_code(code))
        except Exception as exc:
            cleaned = clean_code(code)
            self._record_failure(
                cleaned,
                name,
                "price",
                exc,
                attempts=self._attempts_for("price"),
                cache_fallback=False,
            )
            self._record_failed_symbol(cleaned, name, "price", exc)
            return False
        return True

    def price_history(self, code: str) -> pd.DataFrame:
        path = self.config.cache_dir / "price" / f"{code}.csv"
        ensure_dirs([path.parent])
        if self.config.price_cache_only:
            if path.exists():
                return normalize_price(read_cache_csv(path))
            raise FileNotFoundError(f"Price cache file not found for {code}: {path}")

        def fetch() -> pd.DataFrame:
            return self._akshare_fetch(
                "price",
                code,
                lambda: ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=yyyymmdd(self.config.start_date),
                    end_date=yyyymmdd(self.config.end_date),
                    adjust="qfq",
                    timeout=20,
                ),
            )

        return normalize_price(self._read_or_fetch(path, fetch))

    def cashflow_statement(self, code: str) -> pd.DataFrame:
        path = self.config.cache_dir / "cashflow" / f"{code}.csv"
        ensure_dirs([path.parent])

        def fetch() -> pd.DataFrame:
            return self._akshare_fetch(
                "cashflow",
                code,
                lambda: ak.stock_cash_flow_sheet_by_report_em(
                    symbol=f"{exchange_prefix(code)}{code}"
                ),
            )

        return normalize_cashflow(self._read_or_fetch(path, fetch))

    def profit_statement(self, code: str) -> pd.DataFrame:
        path = self.config.cache_dir / "profit" / f"{code}.csv"
        ensure_dirs([path.parent])

        def fetch() -> pd.DataFrame:
            return self._akshare_fetch(
                "profit",
                code,
                lambda: ak.stock_profit_sheet_by_report_em(symbol=f"{exchange_prefix(code)}{code}"),
            )

        return normalize_profit(self._read_or_fetch(path, fetch))

    def moneyflow_history(self, code: str) -> pd.DataFrame:
        path = self.config.cache_dir / "moneyflow" / f"{code}.csv"
        ensure_dirs([path.parent])

        def fetch() -> pd.DataFrame:
            return self._akshare_fetch(
                "moneyflow",
                code,
                lambda: ak.stock_individual_fund_flow(
                    stock=code,
                    market=fund_flow_market(code),
                ),
            )

        return normalize_moneyflow(self._read_or_fetch(path, fetch))

def financial_empty(endpoint: str) -> pd.DataFrame:
    if endpoint == "cashflow":
        return pd.DataFrame(columns=["report_date", "announce_date", "operating_cashflow"])
    if endpoint == "profit":
        return pd.DataFrame(
            columns=["report_date", "announce_date", "revenue", "parent_net_profit"]
        )
    raise ValueError(f"Unknown financial endpoint: {endpoint}")


def moneyflow_empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "main_net_inflow", "main_net_pct", "close"])


def normalize_universe(raw: pd.DataFrame, max_symbols: int | None = None) -> pd.DataFrame:
    code_col = first_existing_column(raw, ["代码", "SECURITY_CODE", "code"])
    name_col = first_existing_column(raw, ["名称", "SECURITY_NAME_ABBR", "name"])
    industry_col = first_existing_column(raw, ["行业", "所处行业", "industry"])
    market_cap_col = first_existing_column(raw, ["总市值", "market_cap", "TOTAL_MARKET_CAP"])
    float_cap_col = first_existing_column(raw, ["流通市值", "float_market_cap", "FREE_MARKET_CAP"])
    if code_col is None or name_col is None:
        raise ValueError(f"Cannot identify universe code/name columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "code": raw[code_col].map(clean_code),
            "name": raw[name_col].astype(str),
            "industry": raw[industry_col].astype(str) if industry_col else np.nan,
            "market_cap": to_numeric(raw[market_cap_col]) if market_cap_col else np.nan,
            "float_market_cap": to_numeric(raw[float_cap_col]) if float_cap_col else np.nan,
        }
    )
    df = df[df["code"].map(is_hushen_a)]
    df = df[~df["name"].str.contains("ST|PT|退", case=False, na=False)]
    df = df.drop_duplicates("code").sort_values("code")
    if max_symbols is not None:
        df = df.head(max_symbols)
    return df.reset_index(drop=True)


def normalize_price(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "close",
                "adjusted_close",
                "adj_factor",
                "amount",
                "high",
                "low",
                "turnover",
                "total_market_cap",
                "circulating_market_cap",
            ]
        )
    date_col = first_existing_column(raw, ["日期", "date"])
    close_col = first_existing_column(raw, ["收盘", "close"])
    adjusted_close_col = first_existing_column(raw, ["adjusted_close", "qfq_close", "hfq_close"])
    adj_factor_col = first_existing_column(raw, ["adj_factor"])
    amount_col = first_existing_column(raw, ["成交额", "amount"])
    turnover_col = first_existing_column(raw, ["换手率", "turnover"])
    high_col = first_existing_column(raw, ["high", "HIGH", "最高", "最高价"])
    low_col = first_existing_column(raw, ["low", "LOW", "最低", "最低价"])
    total_cap_col = first_existing_column(raw, ["total_market_cap", "TOTAL_MARKET_CAP"])
    circulating_cap_col = first_existing_column(
        raw,
        ["circulating_market_cap", "float_market_cap", "FREE_MARKET_CAP"],
    )
    if date_col is None or close_col is None:
        raise ValueError(f"Cannot identify price date/close columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "date": parse_cache_date(raw[date_col]),
            "close": to_numeric(raw[close_col]),
            "adjusted_close": to_numeric(raw[adjusted_close_col]) if adjusted_close_col else np.nan,
            "adj_factor": to_numeric(raw[adj_factor_col]) if adj_factor_col else np.nan,
            "amount": to_numeric(raw[amount_col]) if amount_col else np.nan,
            "high": to_numeric(raw[high_col]) if high_col else np.nan,
            "low": to_numeric(raw[low_col]) if low_col else np.nan,
            "turnover": to_numeric(raw[turnover_col]) if turnover_col else np.nan,
            "total_market_cap": to_numeric(raw[total_cap_col]) if total_cap_col else np.nan,
            "circulating_market_cap": (
                to_numeric(raw[circulating_cap_col]) if circulating_cap_col else np.nan
            ),
        }
    )
    return df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)


def normalize_cashflow(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["report_date", "announce_date", "operating_cashflow"])
    date_col = first_existing_column(raw, ["report_date", "REPORT_DATE", "报告期", "日期", "截止日期"])
    announce_col = first_existing_column(raw, ["announce_date", "公告日期", "公告日", "ANNOUNCE_DATE", "NOTICE_DATE"])
    ocf_col = first_existing_column(
        raw,
        [
            "operating_cashflow",
            "经营活动产生的现金流量净额",
            "经营活动现金流量净额",
            "NETCASH_OPERATE",
            "NET_CASH_FLOWS_OPERATE_ACT",
            "NETCASH_OPERATE_A",
        ],
    )
    if date_col is None or ocf_col is None:
        raise ValueError(f"Cannot identify cashflow report/OCF columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "report_date": parse_cache_date(raw[date_col]),
            "announce_date": parse_cache_date(raw[announce_col]) if announce_col else pd.NaT,
            "operating_cashflow": to_numeric(raw[ocf_col]),
        }
    )
    return df.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)


def normalize_profit(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["report_date", "announce_date", "revenue", "parent_net_profit"])
    date_col = first_existing_column(raw, ["report_date", "REPORT_DATE", "报告期", "日期", "截止日期"])
    announce_col = first_existing_column(raw, ["announce_date", "公告日期", "公告日", "ANNOUNCE_DATE", "NOTICE_DATE"])
    revenue_col = first_existing_column(raw, ["revenue", "营业总收入", "营业收入", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME"])
    profit_col = first_existing_column(
        raw,
        ["parent_net_profit", "归属于母公司股东的净利润", "归母净利润", "PARENT_NETPROFIT", "NETPROFIT_PARENT_COMPANY"],
    )
    if date_col is None or revenue_col is None or profit_col is None:
        raise ValueError(f"Cannot identify profit report/revenue/net profit columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "report_date": parse_cache_date(raw[date_col]),
            "announce_date": parse_cache_date(raw[announce_col]) if announce_col else pd.NaT,
            "revenue": to_numeric(raw[revenue_col]),
            "parent_net_profit": to_numeric(raw[profit_col]),
        }
    )
    return df.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)


def normalize_moneyflow(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["date", "main_net_inflow", "main_net_pct", "close"])
    date_col = first_existing_column(raw, ["日期", "date"])
    main_amt_col = first_existing_column(raw, ["主力净流入-净额", "main_net_inflow"])
    main_pct_col = first_existing_column(raw, ["主力净流入-净占比", "main_net_pct"])
    close_col = first_existing_column(raw, ["收盘价", "收盘", "close"])
    if date_col is None or main_amt_col is None:
        raise ValueError(f"Cannot identify moneyflow date/main amount columns: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "date": parse_cache_date(raw[date_col]),
            "main_net_inflow": to_numeric(raw[main_amt_col]),
            "main_net_pct": to_numeric(raw[main_pct_col]) / 100.0 if main_pct_col else np.nan,
            "close": to_numeric(raw[close_col]) if close_col else np.nan,
        }
    )
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
