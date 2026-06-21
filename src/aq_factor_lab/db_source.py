from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import (
    clean_code,
    exchange_prefix,
    parse_cache_date,
    parse_cache_datetime,
    read_cache_csv,
)

ALLOWED_PRICE_ADJUSTMENTS = {"raw", "qfq", "hfq", "unknown"}
FINANCIAL_ENDPOINTS = {"cashflow", "profit"}
INDUSTRY_SW_FIELDS = {
    "sw_l1_code",
    "sw_l2_code",
    "sw_l3_code",
    "in_date",
    "out_date",
}
PRICE_ADJUSTMENT_CANDIDATES = {
    "adjusted_close": {"unit": "CNY/share", "multiplier": 1},
    "qfq_close": {"unit": "CNY/share", "multiplier": 1},
    "hfq_close": {"unit": "CNY/share", "multiplier": 1},
    "adj_factor": {"unit": "factor", "multiplier": 1},
    "pre_close": {"unit": "CNY/share", "multiplier": 1},
    "is_adjusted": {"unit": "boolean", "multiplier": 1},
}
UNADJUSTED_PRICE_WARNING = "警告：价格未复权，收益率计算包含除权除息带来的极度失真，后续必须引入复权因子。"

cache_iso_date = parse_cache_date
cache_datetime = parse_cache_datetime


class MappingError(ValueError):
    pass


class DependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    statement_timeout_ms: int = 120_000
    idle_timeout_ms: int = 60_000
    connect_timeout: int = 10

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> DatabaseConfig:
        values = env or os.environ
        missing = [
            key
            for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            if not values.get(key)
        ]
        if missing:
            raise RuntimeError(f"Missing database environment variables: {', '.join(missing)}")
        return cls(
            host=values["DB_HOST"],
            port=int(values["DB_PORT"]),
            dbname=values["DB_NAME"],
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
        )

    @property
    def options(self) -> str:
        return (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={self.statement_timeout_ms} "
            f"-c idle_in_transaction_session_timeout={self.idle_timeout_ms}"
        )

    def __repr__(self) -> str:
        return (
            "DatabaseConfig("
            f"host={self.host!r}, port={self.port!r}, dbname={self.dbname!r}, "
            f"user={self.user!r}, password='***', statement_timeout_ms={self.statement_timeout_ms!r}, "
            f"idle_timeout_ms={self.idle_timeout_ms!r})"
        )


@dataclass(frozen=True)
class QueryPlan:
    endpoint: str
    schema: str
    table: str
    selected_columns: list[str]
    output_columns: list[str]
    params: dict[str, object]
    query: object


class QueryObject:
    """Import-safe stand-in for tests when psycopg is not installed."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self) -> str:
        return f"QueryObject({self.text!r})"


def require_psycopg():
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise DependencyError("Install psycopg[binary] before using database sync.") from exc
    return psycopg, sql


def connect_database(config: DatabaseConfig):
    psycopg, _sql = require_psycopg()
    return psycopg.connect(
        sslmode="disable",
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
        options=config.options,
        connect_timeout=config.connect_timeout,
    )


def load_db_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Explicit database mapping is required: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def apply_price_adjustment_probe(
    mapping: dict[str, Any],
    available_columns: dict[tuple[str, str], set[str]],
) -> dict[str, Any]:
    """Add discovered adjustment-related price columns to the runtime mapping."""
    result = deepcopy(mapping)
    price = result.get("endpoints", {}).get("price", {})
    if not price.get("enabled", False):
        return result
    schema = str(price.get("schema", ""))
    table = str(price.get("table", ""))
    available = available_columns.get((schema, table), set())
    found = [column for column in PRICE_ADJUSTMENT_CANDIDATES if column in available]
    optional = price.setdefault("optional_fields", {})
    units = price.setdefault("units", {})
    for column in found:
        optional.setdefault(column, column)
        units.setdefault(column, dict(PRICE_ADJUSTMENT_CANDIDATES[column]))
    warning = "" if found else UNADJUSTED_PRICE_WARNING
    price["adjustment_probe"] = {
        "table": f"{schema}.{table}",
        "fields_checked": list(PRICE_ADJUSTMENT_CANDIDATES),
        "fields_found": found,
        "warning": warning,
    }
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_db_mapping(
    mapping: dict[str, Any],
    available_columns: dict[tuple[str, str], set[str]] | None,
) -> None:
    endpoints = mapping.get("endpoints")
    if not isinstance(endpoints, dict):
        raise MappingError("db_mapping.json must contain an endpoints object")
    for endpoint, config in endpoints.items():
        if not config.get("enabled", False):
            continue
        _validate_endpoint(endpoint, config, available_columns)


def _validate_endpoint(
    endpoint: str,
    config: dict[str, Any],
    available_columns: dict[tuple[str, str], set[str]] | None,
) -> None:
    schema = _require_text(config, "schema", endpoint)
    table = _require_text(config, "table", endpoint)
    symbol_column = _require_text(config, "symbol_column", endpoint)
    mapped_columns = [symbol_column]

    if endpoint == "universe":
        pass
    elif endpoint in FINANCIAL_ENDPOINTS:
        if config.get("date_column"):
            raise MappingError(f"{endpoint} must not use date_column; use report_date_column and ann/pub date")
        mapped_columns.append(_require_text(config, "report_date_column", endpoint))
        ann = config.get("ann_date_column") or config.get("pub_date_column")
        if not ann:
            raise MappingError(f"{endpoint} requires ann_date_column or pub_date_column")
        mapped_columns.append(str(ann))
    elif endpoint == "industry_sw":
        if config.get("date_column"):
            raise MappingError("industry_sw must not use date_column; cache all classification rows")
    else:
        mapped_columns.append(_require_text(config, "date_column", endpoint))

    if endpoint == "price":
        adjustment = config.get("adjustment")
        if adjustment not in ALLOWED_PRICE_ADJUSTMENTS:
            raise MappingError("price adjustment must be one of raw/qfq/hfq/unknown")

    fields = _field_mapping(config)
    if endpoint in {"universe", "price"} and not fields:
        raise MappingError(f"{endpoint} requires required_fields")
    if endpoint == "cashflow" and "operating_cashflow" not in fields:
        raise MappingError("cashflow requires required_fields.operating_cashflow")
    if endpoint == "profit":
        missing = [field for field in ["revenue", "parent_net_profit"] if field not in fields]
        if missing:
            raise MappingError(f"profit requires required_fields: {', '.join(missing)}")
    if endpoint == "industry_sw":
        missing = [field for field in sorted(INDUSTRY_SW_FIELDS) if field not in fields]
        if missing:
            raise MappingError(f"industry_sw requires fields: {', '.join(missing)}")
    if endpoint == "industry_sw":
        joined_name_outputs = {"sw_l1_name", "sw_l2_name", "sw_l3_name"}
        mapped_columns.extend(
            source for output, source in fields.items() if output not in joined_name_outputs
        )
    else:
        mapped_columns.extend(fields.values())
    _validate_units(endpoint, config, fields)
    _validate_known_columns(endpoint, schema, table, mapped_columns, available_columns)


def _require_text(config: dict[str, Any], key: str, endpoint: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MappingError(f"{endpoint} requires {key}")
    return value


def _field_mapping(config: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for section in ["required_fields", "optional_fields"]:
        values = config.get(section, {})
        if values is None:
            continue
        if not isinstance(values, dict):
            raise MappingError(f"{section} must be an object")
        fields.update({str(output): str(source) for output, source in values.items()})
    return fields


def _validate_units(endpoint: str, config: dict[str, Any], fields: dict[str, str]) -> None:
    units = config.get("units", {})
    if not isinstance(units, dict):
        raise MappingError(f"{endpoint} units must be an object")
    for output_col in fields:
        unit = units.get(output_col)
        if not isinstance(unit, dict) or "multiplier" not in unit:
            raise MappingError(f"{endpoint}.{output_col} requires a unit multiplier")


def _validate_known_columns(
    endpoint: str,
    schema: str,
    table: str,
    columns: list[str],
    available_columns: dict[tuple[str, str], set[str]] | None,
) -> None:
    if available_columns is None:
        return
    known = available_columns.get((schema, table))
    if known is None:
        raise MappingError(f"{endpoint} table not found in information_schema: {schema}.{table}")
    missing = [column for column in columns if column not in known]
    if missing:
        raise MappingError(f"{endpoint} columns not found in {schema}.{table}: {', '.join(missing)}")


def build_query_plan(
    endpoint: str,
    config: dict[str, Any],
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> QueryPlan:
    date_column = config.get("date_column") or config.get("report_date_column")
    ann_column = config.get("ann_date_column") or config.get("pub_date_column")
    fields = _field_mapping(config)
    selected = [config["symbol_column"], *fields.values()]
    if date_column:
        selected.insert(1, str(date_column))
    if ann_column:
        selected.insert(2, str(ann_column))
    if config.get("updated_at_column"):
        selected.append(config["updated_at_column"])
    output_columns = ["db_symbol", *fields.keys()]
    if date_column:
        output_columns.insert(1, "date")
    if ann_column:
        output_columns.insert(2, "announce_date")
    query = _build_select_query(
        config["schema"],
        config["table"],
        selected,
        config["symbol_column"],
        str(date_column) if date_column else None,
    )
    return QueryPlan(
        endpoint=endpoint,
        schema=config["schema"],
        table=config["table"],
        selected_columns=selected,
        output_columns=output_columns,
        params={"symbols": symbols, "start_date": start_date, "end_date": end_date},
        query=query,
    )


def _build_select_query(
    schema: str,
    table: str,
    columns: list[str],
    symbol_column: str,
    date_column: str | None,
) -> object:
    try:
        _psycopg, sql = require_psycopg()
    except DependencyError:
        return QueryObject(f"SELECT {columns!r} FROM {schema}.{table}")
    base = sql.SQL("SELECT {fields} FROM {table}").format(
        fields=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        table=sql.Identifier(schema, table),
    )
    if date_column:
        return base + sql.SQL(
            " WHERE {symbol_col} = ANY(%(symbols)s) "
            "AND {date_col} >= %(start_date)s AND {date_col} <= %(end_date)s"
        ).format(
            symbol_col=sql.Identifier(symbol_column),
            date_col=sql.Identifier(date_column),
        )
    return base + sql.SQL(" WHERE {symbol_col} IS NOT NULL").format(
        symbol_col=sql.Identifier(symbol_column)
    )


def fetch_information_schema(conn) -> pd.DataFrame:
    query = (
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY table_schema, table_name, ordinal_position"
    )
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["schema", "table", "column", "data_type"])


def available_columns_from_schema(schema_frame: pd.DataFrame) -> dict[tuple[str, str], set[str]]:
    if schema_frame.empty:
        return {}
    return {
        (str(schema), str(table)): set(group["column"].astype(str))
        for (schema, table), group in schema_frame.groupby(["schema", "table"])
    }


def make_mapping_template(schema_frame: pd.DataFrame) -> dict[str, Any]:
    tables = []
    if not schema_frame.empty:
        for (schema, table), group in schema_frame.groupby(["schema", "table"]):
            tables.append(
                {
                    "schema": schema,
                    "table": table,
                    "columns": group[["column", "data_type"]].to_dict("records"),
                }
            )
    return {
        "version": 1,
        "notes": "Fill this template manually, then save as config/db_mapping.json.",
        "candidate_tables": tables,
        "endpoints": default_mapping_template()["endpoints"],
    }


def default_mapping_template() -> dict[str, Any]:
    return {
        "version": 1,
        "endpoints": {
            "universe": {"enabled": False},
            "price": {
                "enabled": False,
                "adjustment": "unknown",
                "required_fields": {"close": ""},
                "optional_fields": {"amount": "", "turnover": ""},
                "units": {
                    "close": {"multiplier": 1, "unit": "database_native"},
                    "amount": {"multiplier": 1, "unit": "database_native"},
                    "turnover": {"multiplier": 1, "unit": "database_native"},
                },
            },
            "cashflow": {"enabled": False},
            "profit": {"enabled": False},
            "moneyflow": {"enabled": False},
            "industry_sw": {
                "enabled": False,
                "schema": "public",
                "table": "map_company_industry_sw",
                "symbol_column": "company_id",
                "required_fields": {
                    "l1_index_code": "l1_index_code",
                    "l2_index_code": "l2_index_code",
                    "l3_index_code": "l3_index_code",
                    "in_date": "in_date",
                    "out_date": "out_date",
                    "is_new": "is_new",
                    "updated_at": "updated_at",
                },
                "optional_fields": {"l1_industry_name": ""},
                "units": {
                    "l1_index_code": {"unit": "text", "multiplier": 1},
                    "l2_index_code": {"unit": "text", "multiplier": 1},
                    "l3_index_code": {"unit": "text", "multiplier": 1},
                    "in_date": {"unit": "text", "multiplier": 1},
                    "out_date": {"unit": "text", "multiplier": 1},
                    "is_new": {"unit": "text", "multiplier": 1},
                    "updated_at": {"unit": "text", "multiplier": 1},
                    "l1_industry_name": {"unit": "text", "multiplier": 1},
                },
            },
        },
    }


class SyncPlanner:
    def __init__(
        self,
        root_dir: Path,
        mapping: dict[str, Any],
        available_columns: dict[tuple[str, str], set[str]] | None,
    ):
        self.root_dir = root_dir
        self.mapping = mapping
        self.available_columns = available_columns
        validate_db_mapping(mapping, available_columns)

    def dry_run(
        self,
        endpoints: list[str],
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> list[dict[str, object]]:
        rows = []
        for endpoint in endpoints:
            config = self.mapping["endpoints"].get(endpoint, {})
            if not config.get("enabled", False):
                rows.append({"endpoint": endpoint, "status": "disabled", "symbol_count": len(symbols)})
                continue
            plan = build_query_plan(endpoint, config, symbols, start_date, end_date)
            rows.append(
                {
                    "endpoint": endpoint,
                    "status": "would_query",
                    "schema": plan.schema,
                    "table": plan.table,
                    "fields": ",".join(plan.selected_columns),
                    "start_date": start_date,
                    "end_date": end_date,
                    "symbol_count": len(symbols),
                }
            )
        return rows


def normalize_db_symbol(value: object) -> tuple[str, str, str]:
    db_symbol = str(value).strip()
    code = clean_code(db_symbol)
    exchange = exchange_prefix(code)
    return db_symbol, code, exchange


def convert_units(frame: pd.DataFrame, mapping: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    for column, unit in mapping.get("units", {}).items():
        if isinstance(unit, dict) and unit.get("unit") == "text":
            continue
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce") * float(unit["multiplier"])
    return result


def deduplicate_cache_frame(
    frame: pd.DataFrame,
    endpoint: str,
    warnings: list[dict[str, object]],
) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    if "code" in result.columns:
        result["code"] = result["code"].map(clean_code)
    if "db_symbol" in result.columns:
        result["db_symbol"] = result["db_symbol"].astype(str)
    if "exchange" in result.columns:
        result["exchange"] = result["exchange"].astype(str)
    if endpoint == "industry_sw":
        return deduplicate_industry_sw_frame(result, warnings)
    date_col = "date" if "date" in result.columns else "report_date"
    result[date_col] = cache_iso_date(result[date_col], warnings, date_col)
    sort_cols = ["code", date_col]
    for optional_col in ["ann_date", "pub_date", "updated_at"]:
        if optional_col in result.columns:
            result[optional_col] = cache_datetime(result[optional_col], warnings, optional_col)
            sort_cols.append(optional_col)
    if "announce_date" in result.columns:
        result["announce_date"] = cache_iso_date(result["announce_date"], warnings, "announce_date")
        sort_cols.append("announce_date")
    duplicate_keys = ["code", date_col]
    duplicate_mask = result.duplicated(duplicate_keys, keep=False)
    if duplicate_mask.any():
        for (code, key_date), group in result[duplicate_mask].groupby(duplicate_keys):
            warnings.append(
                {
                    "endpoint": endpoint,
                    "code": code,
                    "date": cache_iso_date(pd.Series([key_date])).iloc[0].date().isoformat(),
                    "duplicate_count": int(group.shape[0]),
                    "resolution": "kept latest ann/pub/updated row",
                }
            )
    result = result.sort_values(sort_cols).drop_duplicates(duplicate_keys, keep="last")
    return result.sort_values(["code", date_col]).reset_index(drop=True)


def normalize_industry_sw_dates(
    frame: pd.DataFrame,
    warnings: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    for column in ["in_date", "out_date"]:
        if column not in result:
            continue
        parsed = parse_industry_sw_date(result[column])
        bad = parsed.isna() & result[column].astype(str).str.strip().ne("") & ~result[column].isna()
        if warnings is not None and bad.any():
            warnings.append(
                {
                    "endpoint": "industry_sw",
                    "code": "",
                    "date": "",
                    "duplicate_count": int(bad.sum()),
                    "resolution": f"could not parse {column}; set to null",
                }
            )
        result[column] = parsed.dt.date.map(lambda value: value.isoformat() if pd.notna(value) else pd.NA)
    if "updated_at" in result:
        result["updated_at"] = cache_datetime(result["updated_at"], warnings, "updated_at")
    return result


def parse_industry_sw_date(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], format="%Y-%m-%d", errors="coerce")
    return parsed


def deduplicate_industry_sw_frame(
    frame: pd.DataFrame,
    warnings: list[dict[str, object]],
) -> pd.DataFrame:
    result = normalize_industry_sw_dates(frame, warnings)
    result = ensure_industry_sw_aliases(result)
    text_cols = [
        "db_symbol",
        "code",
        "exchange",
        "sw_l1_code",
        "sw_l2_code",
        "sw_l3_code",
        "sw_l1_name",
        "sw_l2_name",
        "sw_l3_name",
        "l1_index_code",
        "l2_index_code",
        "l3_index_code",
        "l1_industry_name",
        "is_new",
    ]
    for column in text_cols:
        if column in result:
            result[column] = result[column].astype("string")
    duplicate_keys = ["code", "sw_l1_code", "sw_l2_code", "sw_l3_code", "in_date", "out_date"]
    duplicate_keys = [column for column in duplicate_keys if column in result]
    duplicate_mask = result.duplicated(duplicate_keys, keep=False)
    if duplicate_mask.any():
        for key, group in result[duplicate_mask].groupby(duplicate_keys, dropna=False):
            warnings.append(
                {
                    "endpoint": "industry_sw",
                    "code": key[0] if isinstance(key, tuple) else "",
                    "date": "",
                    "duplicate_count": int(group.shape[0]),
                    "resolution": "kept latest updated row",
                }
            )
    sort_cols = [column for column in ["code", "in_date", "updated_at"] if column in result]
    result = result.sort_values(sort_cols).drop_duplicates(duplicate_keys, keep="last")
    return result.sort_values(sort_cols).reset_index(drop=True)


def ensure_industry_sw_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep old cache names readable while making sw_* the canonical schema."""
    result = frame.copy()
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
        if legacy not in result and canonical in result:
            result[legacy] = result[canonical]
    return result


def atomic_write_csv(frame: pd.DataFrame, path: Path, required_columns: list[str]) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Cannot write {path}; missing required columns: {', '.join(missing)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    check = read_cache_csv(tmp_path)
    if check.shape[0] != frame.shape[0]:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(f"Atomic write validation failed for {path}: row count changed")
    if any(column not in check.columns for column in required_columns):
        tmp_path.unlink(missing_ok=True)
        raise ValueError(f"Atomic write validation failed for {path}: required columns missing")
    tmp_path.replace(path)
