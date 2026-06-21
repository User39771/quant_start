from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.db_source import (  # noqa: E402
    DatabaseConfig,
    connect_database,
    fetch_information_schema,
)
from aq_factor_lab.utils import load_env_file, read_cache_csv  # noqa: E402

ADJUSTED_PRICE_COLUMNS = {
    "adjusted_close",
    "qfq_close",
    "hfq_close",
    "adj_factor",
    "pre_close",
}
CORPORATE_ACTION_COLUMNS = {
    "corporate_action",
    "dividend",
    "split",
    "bonus",
    "bonus_share",
}
LIFECYCLE_COLUMNS = {
    "list_date",
    "listing_date",
    "ipo_date",
    "delist_date",
    "delisting_date",
    "listing_status",
    "is_active",
}
TRADING_STATUS_COLUMNS = {
    "suspension",
    "suspend",
    "paused",
    "is_paused",
    "trading_status",
    "limit_up",
    "limit_down",
    "st_flag",
    "is_st",
    "volume",
    "amount",
}
INDUSTRY_ASOF_COLUMNS = {"in_date", "out_date"}
MARKET_CAP_COLUMNS = {"total_market_cap", "circulating_market_cap", "total_market_value", "circulating_market_value"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit market-data realism fields without mutating the database.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--schema", type=Path, default=None)
    parser.add_argument("--no-db", action="store_true", help="Use local db_schema.csv only.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = args.root
    schema = load_schema(root, args.schema, use_db=not args.no_db)
    price_cache_columns = sample_price_cache_columns(root / "data" / "cache" / "price")
    rows = build_audit_rows(schema, price_cache_columns=price_cache_columns)
    observation_rows = load_database_observation_rows(root, schema, use_db=not args.no_db)
    if observation_rows:
        rows = pd.concat([rows, pd.DataFrame(observation_rows)], ignore_index=True)
    save_audit_outputs(rows, root / "data" / "processed", root / "reports")
    print(f"Market data realism audit rows: {len(rows)}")
    print(f"Report written: {root / 'reports' / 'market_data_realism_audit.md'}")


def load_schema(root: Path, schema_path: Path | None, *, use_db: bool) -> pd.DataFrame:
    if use_db:
        try:
            load_env_file(root / ".env")
            config = DatabaseConfig.from_env()
            with connect_database(config) as conn:
                return fetch_information_schema(conn)
        except Exception as exc:
            print(f"[audit_market_data_realism] database_schema_fallback={type(exc).__name__}", flush=True)
    path = schema_path or root / "data" / "processed" / "db_schema.csv"
    if not path.exists():
        return pd.DataFrame(columns=["schema", "table", "column", "data_type"])
    return read_cache_csv(path)


def load_database_observation_rows(root: Path, schema: pd.DataFrame, *, use_db: bool) -> list[dict[str, str]]:
    if not use_db:
        return []
    normalized = normalize_schema(schema)
    try:
        load_env_file(root / ".env")
        config = DatabaseConfig.from_env()
        with connect_database(config) as conn:
            return database_observation_rows(conn, normalized)
    except Exception as exc:
        return [
            {
                "category": "database_sample",
                "check": "sample_query_status",
                "status": "unavailable",
                "evidence": type(exc).__name__,
                "impact": "Sample coverage queries were not available; schema audit still completed.",
                "required_action": "rerun audit when database connectivity is available",
            }
        ]


def database_observation_rows(conn, schema: pd.DataFrame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    rows += coverage_row(
        conn,
        schema,
        "stock_prices",
        "trade_date",
        ["close_price", "total_market_cap", "amount"],
        "stock_prices_close_coverage",
    )
    rows += coverage_row(
        conn,
        schema,
        "stock_prices_history",
        "trade_date",
        ["close_price", "adj_factor", "amount"],
        "stock_prices_history_adj_factor_coverage",
    )
    rows += count_condition_row(
        conn,
        schema,
        "stock_prices",
        "amount",
        "amount = 0",
        "stock_prices_zero_amount_days",
        "Zero-amount days proxy suspension/no-trade events for execution diagnostics.",
    )
    rows += count_condition_row(
        conn,
        schema,
        "stock_prices_history",
        "volume",
        "volume = 0",
        "stock_prices_history_zero_volume_days",
        "Zero-volume days proxy suspension/no-trade events for execution diagnostics.",
    )
    rows += active_status_row(conn, schema)
    rows += count_condition_row(
        conn,
        schema,
        "map_company_industry_sw",
        "out_date",
        "out_date IS NOT NULL AND out_date <> ''",
        "industry_out_date_rows",
        "Non-empty out_date rows indicate industry changes can be modeled as-of.",
    )
    return rows


def coverage_row(
    conn,
    schema: pd.DataFrame,
    table: str,
    date_column: str,
    value_columns: list[str],
    check: str,
) -> list[dict[str, str]]:
    table_schema = table_schema_for(schema, table)
    available = columns_for(schema, table)
    needed = {date_column, *value_columns}
    if table_schema is None or not needed.issubset(available):
        return []
    select_exprs = [
        f"MIN({date_column})",
        f"MAX({date_column})",
        "COUNT(*)",
        *[f"COUNT({column})" for column in value_columns],
    ]
    query = f"SELECT {', '.join(select_exprs)} FROM {table_schema}.{table}"
    with conn.cursor() as cur:
        cur.execute(query)
        result = cur.fetchone()
    min_date, max_date, row_count, *non_null_counts = result
    evidence_parts = [
        f"date_range={min_date}..{max_date}",
        f"rows={row_count}",
        *[
            f"{column}_non_null={count}"
            for column, count in zip(value_columns, non_null_counts, strict=True)
        ],
    ]
    return [
        {
            "category": "database_sample",
            "check": check,
            "status": "available",
            "evidence": "; ".join(evidence_parts),
            "impact": "Date coverage sample helps decide whether fields can support full-period research.",
            "required_action": "compare coverage against backtest window before switching methodology",
        }
    ]


def count_condition_row(
    conn,
    schema: pd.DataFrame,
    table: str,
    required_column: str,
    condition: str,
    check: str,
    impact: str,
) -> list[dict[str, str]]:
    table_schema = table_schema_for(schema, table)
    available = columns_for(schema, table)
    if table_schema is None or required_column not in available:
        return []
    query = f"SELECT COUNT(*) FROM {table_schema}.{table} WHERE {condition}"
    with conn.cursor() as cur:
        cur.execute(query)
        count = cur.fetchone()[0]
    return [
        {
            "category": "database_sample",
            "check": check,
            "status": "available",
            "evidence": f"count={count}",
            "impact": impact,
            "required_action": "use same-day fields only in execution model",
        }
    ]


def active_status_row(conn, schema: pd.DataFrame) -> list[dict[str, str]]:
    table_schema = table_schema_for(schema, "companies")
    available = columns_for(schema, "companies")
    if table_schema is None or "is_active" not in available:
        return []
    query = f"SELECT is_active, COUNT(*) FROM {table_schema}.companies GROUP BY is_active ORDER BY is_active"
    with conn.cursor() as cur:
        cur.execute(query)
        counts = cur.fetchall()
    evidence = ", ".join(f"is_active={status}:count={count}" for status, count in counts)
    return [
        {
            "category": "database_sample",
            "check": "companies_is_active_counts",
            "status": "available",
            "evidence": evidence,
            "impact": "Current active status exists but does not replace historical delist_date/list_date.",
            "required_action": "do not treat current is_active as full point-in-time universe history",
        }
    ]


def table_schema_for(schema: pd.DataFrame, table: str) -> str | None:
    if schema.empty:
        return None
    matched = schema[schema["table"].astype(str) == table]
    if matched.empty:
        return None
    return str(matched.iloc[0]["schema"])


def columns_for(schema: pd.DataFrame, table: str) -> set[str]:
    if schema.empty:
        return set()
    return set(schema.loc[schema["table"].astype(str) == table, "column"].astype(str))


def sample_price_cache_columns(price_dir: Path) -> list[str]:
    if not price_dir.exists():
        return []
    for path in sorted(price_dir.glob("*.csv")):
        try:
            frame = read_cache_csv(path)
        except (OSError, pd.errors.EmptyDataError, UnicodeDecodeError):
            continue
        if not frame.empty:
            return [str(column) for column in frame.columns]
    return []


def build_audit_rows(schema: pd.DataFrame, *, price_cache_columns: Iterable[str] | None = None) -> pd.DataFrame:
    normalized = normalize_schema(schema)
    cache_columns = {str(column) for column in (price_cache_columns or [])}
    rows = [
        audit_column_set(
            normalized,
            "return",
            "adjusted_price_fields",
            ADJUSTED_PRICE_COLUMNS,
            "Strict adjusted returns are possible only if these fields are connected to cache.",
            "Use adjusted_close, qfq/hfq close, or close * adj_factor before portfolio returns.",
        ),
        audit_adjustment_factor(normalized, cache_columns),
        audit_cache_strict_return(cache_columns),
        audit_column_set(
            normalized,
            "return",
            "corporate_action_fields",
            CORPORATE_ACTION_COLUMNS,
            "Corporate action data can independently validate adjustment factors.",
            "Keep caveat if unavailable.",
        ),
        audit_column_set(
            normalized,
            "universe",
            "list_date",
            {"list_date", "listing_date", "ipo_date"},
            "Without list dates, future IPOs can leak into the past if universe construction is careless.",
            "Use list_date <= rebalance_date for point-in-time universe.",
        ),
        audit_column_set(
            normalized,
            "universe",
            "delist_date",
            {"delist_date", "delisting_date"},
            "Without delist dates or historical constituents, survivorship bias remains unresolved.",
            "Keep survivorship caveat until historical delisted names are available.",
        ),
        audit_column_set(
            normalized,
            "universe",
            "listing_status",
            {"listing_status", "is_active"},
            "Current status alone does not reconstruct historical membership.",
            "Use only as a diagnostic unless status history is available.",
        ),
        audit_column_set(
            normalized,
            "execution",
            "trading_status_fields",
            TRADING_STATUS_COLUMNS,
            "Trading status and limit fields improve buy/sell executability modeling.",
            "Use same-day flags only; keep caveat for missing sell-side constraints.",
        ),
        audit_column_set(
            normalized,
            "industry_market_cap",
            "industry_asof_dates",
            INDUSTRY_ASOF_COLUMNS,
            "Industry in/out dates support point-in-time industry classification.",
            "Continue as-of industry join.",
            require_all=True,
        ),
        audit_column_set(
            normalized,
            "industry_market_cap",
            "market_cap_history",
            MARKET_CAP_COLUMNS,
            "Historical market cap is required for size neutralization and current proxy returns.",
            "Verify it is daily historical data, not latest values backfilled.",
        ),
    ]
    return pd.DataFrame(rows)


def normalize_schema(schema: pd.DataFrame) -> pd.DataFrame:
    required = ["schema", "table", "column", "data_type"]
    if schema.empty:
        return pd.DataFrame(columns=required)
    result = schema.copy()
    rename = {"table_schema": "schema", "table_name": "table", "column_name": "column"}
    result = result.rename(columns={key: value for key, value in rename.items() if key in result.columns})
    for column in required:
        if column not in result:
            result[column] = ""
        result[column] = result[column].astype(str)
    result["column_lower"] = result["column"].str.lower()
    return result


def audit_column_set(
    schema: pd.DataFrame,
    category: str,
    check: str,
    candidates: set[str],
    impact_available: str,
    required_action: str,
    *,
    require_all: bool = False,
) -> dict[str, str]:
    found = find_columns(schema, candidates)
    if require_all:
        found_names = {item.split(".")[-1] for item in found}
        status = "available" if candidates.issubset(found_names) else "missing"
    else:
        status = "available" if found else "missing"
    impact = impact_available if found else f"{check} missing; current results may be biased or incomplete."
    return {
        "category": category,
        "check": check,
        "status": status,
        "evidence": ", ".join(found) if found else "not found in schema",
        "impact": impact,
        "required_action": required_action if found else "retain caveat or source missing data",
    }


def audit_adjustment_factor(schema: pd.DataFrame, cache_columns: set[str]) -> dict[str, str]:
    found = find_columns(schema, {"adj_factor"})
    if "adj_factor" in cache_columns or "adjusted_close" in cache_columns:
        status = "cached"
        action = "strict adjusted returns can be used by the local pipeline"
    elif found:
        status = "available_not_cached"
        action = "join or sync adj_factor into local price cache before replacing total_market_cap proxy"
    else:
        status = "missing"
        action = "retain strict_adjusted_return_unavailable caveat"
    return {
        "category": "return",
        "check": "adjustment_factor",
        "status": status,
        "evidence": ", ".join(found) if found else "not found in schema",
        "impact": "adj_factor can construct adjusted_close as close * adj_factor when aligned by code/date."
        if found
        else "No adjustment factor found; strict adjusted returns are unavailable.",
        "required_action": action,
    }


def audit_cache_strict_return(cache_columns: set[str]) -> dict[str, str]:
    has_adjusted = "adjusted_close" in cache_columns or ({"close", "adj_factor"}.issubset(cache_columns))
    return {
        "category": "return",
        "check": "strict_return_cache",
        "status": "available" if has_adjusted else "missing",
        "evidence": ", ".join(sorted(cache_columns)) if cache_columns else "no price cache sample",
        "impact": "Local factor/backtest pipeline can use strict adjusted returns."
        if has_adjusted
        else "price cache lacks adjusted_close or adj_factor; current run must retain return proxy caveat.",
        "required_action": "prefer adjusted_close returns"
        if has_adjusted
        else "do not replace total_market_cap proxy until adjusted data is cached",
    }


def find_columns(schema: pd.DataFrame, candidates: set[str]) -> list[str]:
    if schema.empty:
        return []
    exact = schema[schema["column_lower"].isin({candidate.lower() for candidate in candidates})]
    fuzzy_mask = pd.Series(False, index=schema.index)
    for candidate in candidates:
        fuzzy_mask |= schema["column_lower"].str.contains(candidate.lower(), regex=False, na=False)
    rows = pd.concat([exact, schema[fuzzy_mask]], ignore_index=True).drop_duplicates(
        ["schema", "table", "column"]
    )
    return [
        f"{row.schema}.{row.table}.{row.column}"
        for row in rows.sort_values(["schema", "table", "column"]).itertuples(index=False)
    ]


def render_audit_report(rows: pd.DataFrame) -> str:
    lines = [
        "# Market Data Realism Audit",
        "",
        "- scope=read_only_schema_and_cache_diagnostics",
        "- no_database_mutation=true",
        "",
        "## Summary",
        "",
    ]
    if rows.empty:
        lines.append("- status=no_audit_rows")
        return "\n".join(lines)
    statuses = rows["status"].astype(str).value_counts().to_dict()
    for status, count in sorted(statuses.items()):
        lines.append(f"- {status}={count}")
    strict_cache = rows[(rows["check"] == "strict_return_cache") & (rows["status"] == "available")]
    adj_not_cached = rows[(rows["check"] == "adjustment_factor") & (rows["status"] == "available_not_cached")]
    if strict_cache.empty:
        lines.append("- strict_adjusted_return_unavailable=true")
    else:
        lines.append("- strict_adjusted_return_unavailable=false")
    if not adj_not_cached.empty:
        lines.append("- adjusted_factor_available_but_not_cached=true")
    delist_missing = rows[(rows["check"] == "delist_date") & (rows["status"] == "missing")]
    if not delist_missing.empty:
        lines.append("- survivorship_bias_unresolved=true")
    lines += ["", "## Detail", ""]
    display = rows.copy()
    lines += display.to_markdown(index=False).splitlines()
    lines += [
        "",
        "## Required Fix Priority",
        "",
        "- First: cache and align strict adjusted returns before replacing the current return proxy.",
        "- Second: source historical listing and delisting membership before claiming point-in-time universe correctness.",
        "- Third: extend sell-side execution constraints only with same-day fields; missing status flags remain caveats.",
    ]
    return "\n".join(lines)


def save_audit_outputs(rows: pd.DataFrame, processed_dir: Path, report_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    rows.to_csv(processed_dir / "market_data_realism_audit.csv", index=False, encoding="utf-8-sig")
    (report_dir / "market_data_realism_audit.md").write_text(render_audit_report(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
