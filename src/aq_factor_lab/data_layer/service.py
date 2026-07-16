from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import requests

from .akshare_client import AkSharePublicClient
from .cache import (
    build_query_payload,
    cache_paths,
    query_key,
    read_clean_cache,
    write_csv,
    write_manifest,
)
from .config import DataLayerConfig, default_config
from .errors import CacheMissError, PublicDataFetchError
from .normalize import (
    CONCEPT_COLUMNS,
    INDEX_COLUMNS,
    PRICE_COLUMNS,
    UNIVERSE_COLUMNS,
    normalize_concept_members,
    normalize_daily_price,
    normalize_index_price,
    normalize_universe,
    yyyymmdd,
)
from .quality import append_failure, append_quality_warning, validate_price_frame
from .rate_limit import RequestBudget

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class DataLayerService:
    def __init__(
        self,
        config: DataLayerConfig | None = None,
        client: AkSharePublicClient | None = None,
    ) -> None:
        self.config = config or default_config()
        self.client = client or AkSharePublicClient()
        self.budget = RequestBudget(self.config)

    def get_daily_price(self, symbol: str, start: str, end: str, adjusted: bool = True) -> pd.DataFrame:
        payload = build_query_payload(
            endpoint="daily_price",
            config=self.config,
            symbol=symbol,
            start=start,
            end=end,
            adjusted=adjusted,
        )
        return self._cache_first(
            endpoint="daily_price",
            payload=payload,
            empty_columns=PRICE_COLUMNS,
            date_columns=["date"],
            adjust_mode="qfq" if adjusted else "raw",
            fetch=lambda: self.client.stock_daily(
                symbol=symbol,
                start=yyyymmdd(start),
                end=yyyymmdd(end),
                adjusted=adjusted,
                timeout=self.config.timeout_seconds,
            ),
            normalize=lambda raw: normalize_daily_price(
                raw,
                symbol=symbol,
                start=start,
                end=end,
                adjusted=adjusted,
            ),
            validate=lambda clean: validate_price_frame(clean, endpoint="daily_price"),
        )

    def get_index_price(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        payload = build_query_payload(
            endpoint="index_price",
            config=self.config,
            index_code=index_code,
            start=start,
            end=end,
            adjusted=False,
        )
        return self._cache_first(
            endpoint="index_price",
            payload=payload,
            empty_columns=INDEX_COLUMNS,
            date_columns=["date"],
            adjust_mode="raw",
            fetch=lambda: self.client.index_daily(
                index_code=index_code,
                start=yyyymmdd(start),
                end=yyyymmdd(end),
                timeout=self.config.timeout_seconds,
            ),
            normalize=lambda raw: normalize_index_price(raw, index_code=index_code, start=start, end=end),
            validate=lambda clean: validate_price_frame(
                clean.rename(columns={"index_code": "_index_code"}),
                endpoint="index_price",
            ),
        )

    def get_stock_universe(self, date: str, filters: dict | None = None) -> pd.DataFrame:
        payload = build_query_payload(
            endpoint="stock_universe",
            config=self.config,
            requested_date=date,
            filters=filters,
        )

        def normalize(raw: pd.DataFrame) -> pd.DataFrame:
            clean, warnings = normalize_universe(raw)
            for warning in warnings:
                append_quality_warning(self.config.log_dir, warning)
            return clean

        return self._cache_first(
            endpoint="stock_universe",
            payload=payload,
            empty_columns=UNIVERSE_COLUMNS,
            date_columns=["list_date", "delist_date"],
            adjust_mode="none",
            fetch=self.client.stock_universe,
            normalize=normalize,
            validate=lambda _clean: None,
        )

    def get_concept_members(self, concept_name: str, date: str | None = None) -> pd.DataFrame:
        payload = build_query_payload(
            endpoint="concept_members",
            config=self.config,
            concept_name=concept_name,
            requested_date=date,
        )
        return self._cache_first(
            endpoint="concept_members",
            payload=payload,
            empty_columns=CONCEPT_COLUMNS,
            date_columns=[],
            adjust_mode="none",
            fetch=lambda: self.client.concept_members(concept_name),
            normalize=lambda raw: normalize_concept_members(
                raw,
                concept_name=concept_name,
                requested_date=date,
            ),
            validate=lambda _clean: None,
        )

    def _cache_first(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        empty_columns: list[str],
        date_columns: list[str],
        adjust_mode: str,
        fetch: Callable[[], pd.DataFrame],
        normalize: Callable[[pd.DataFrame], pd.DataFrame],
        validate: Callable[[pd.DataFrame], None],
    ) -> pd.DataFrame:
        key = query_key(payload)
        paths = cache_paths(self.config, endpoint, key)
        if paths.clean.exists():
            LOGGER.info("data_layer cache hit endpoint=%s key=%s", endpoint, key)
            return read_clean_cache(paths.clean, date_columns=date_columns)
        if self.config.cache_only:
            LOGGER.info("data_layer cache-only miss endpoint=%s key=%s", endpoint, key)
            raise CacheMissError(f"Exact clean cache not found for {endpoint}: {paths.clean}")
        if self.config.dry_run:
            LOGGER.info("data_layer dry-run planned request endpoint=%s key=%s", endpoint, key)
            return pd.DataFrame(columns=empty_columns)

        raw = self._fetch_with_retry(endpoint, key, fetch)
        clean = normalize(raw)
        validate(clean)
        write_csv(paths.raw, raw)
        write_csv(paths.clean, clean)
        write_manifest(
            path=paths.manifest,
            akshare_version=self.client.version,
            endpoint=endpoint,
            source=self.config.source,
            schema_version=self.config.schema_version,
            query_key_value=key,
            adjust_mode=adjust_mode,
            raw_row_count=len(raw),
            clean_row_count=len(clean),
            raw_path=paths.raw,
            clean_path=paths.clean,
        )
        return clean

    def _fetch_with_retry(
        self,
        endpoint: str,
        key: str,
        fetch: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            self.budget.acquire()
            try:
                raw = fetch()
                self.budget.sleep_after_request()
                return raw
            except (requests.ConnectionError, requests.Timeout, TimeoutError) as exc:
                last_error = exc
                LOGGER.warning(
                    "data_layer transient request failure endpoint=%s key=%s attempt=%s/%s error=%s",
                    endpoint,
                    key,
                    attempt,
                    self.config.max_attempts,
                    exc,
                )
                if attempt < self.config.max_attempts and self.config.sleep_seconds > 0:
                    time.sleep(self.config.sleep_seconds)
            except Exception as exc:
                last_error = exc
                break
        append_failure(
            self.config.log_dir,
            {
                "endpoint": endpoint,
                "query_key": key,
                "error_type": type(last_error).__name__,
                "error": str(last_error),
            },
        )
        raise PublicDataFetchError(
            f"{endpoint} public data request failed after {self.config.max_attempts} attempts: "
            f"{last_error}"
        ) from last_error


_SERVICE: DataLayerService | None = None


def configure_data_layer(config: DataLayerConfig | None = None) -> None:
    global _SERVICE
    _SERVICE = DataLayerService(config or default_config())


def service() -> DataLayerService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DataLayerService()
    return _SERVICE


def get_daily_price(symbol: str, start: str, end: str, adjusted: bool = True) -> pd.DataFrame:
    return service().get_daily_price(symbol, start, end, adjusted)


def get_index_price(index_code: str, start: str, end: str) -> pd.DataFrame:
    return service().get_index_price(index_code, start, end)


def get_stock_universe(date: str, filters: dict | None = None) -> pd.DataFrame:
    return service().get_stock_universe(date, filters)


def get_concept_members(concept_name: str, date: str | None = None) -> pd.DataFrame:
    return service().get_concept_members(concept_name, date)
