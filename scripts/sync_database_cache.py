from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.db_source import (  # noqa: E402
    DatabaseConfig,
    SyncPlanner,
    apply_price_adjustment_probe,
    atomic_write_csv,
    available_columns_from_schema,
    build_query_plan,
    connect_database,
    convert_units,
    deduplicate_cache_frame,
    ensure_industry_sw_aliases,
    load_db_mapping,
    normalize_db_symbol,
    normalize_industry_sw_dates,
    require_psycopg,
)
from aq_factor_lab.utils import load_env_file, parse_cache_date, read_cache_csv  # noqa: E402

SUPPORTED_ENDPOINTS = {"universe", "price", "cashflow", "profit", "industry_sw"}
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_STATEMENT_TIMEOUT_MS = 120_000
MAX_DIAGNOSTIC_ERROR_CHARS = 240

load_env_file(ROOT / ".env")


def diag(message: str, **fields: object) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"[{timestamp}] [sync_database_cache] {message}" + (f" {details}" if details else ""),
        flush=True,
    )


def mask_optional_host(host: str) -> str:
    return mask_host(host) if host else "***"


def mask_optional_identifier(value: str) -> str:
    return mask_host(value) if value else "***"


def safe_error_message(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    if len(message) > MAX_DIAGNOSTIC_ERROR_CHARS:
        return f"{message[:MAX_DIAGNOSTIC_ERROR_CHARS]}..."
    return message


def rollback_after_db_error(conn, context: dict[str, object]) -> None:
    try:
        conn.rollback()
    except Exception as rollback_exc:
        diag(
            "db_rollback_failed",
            error=type(rollback_exc).__name__,
            message=safe_error_message(rollback_exc),
            **context,
        )
        return
    diag("db_rollback_after_error", **context)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync read-only PostgreSQL data into local CSV cache."
    )
    parser.add_argument("--mapping", type=Path, default=ROOT / "config" / "db_mapping.json")
    parser.add_argument("--endpoints", type=str, default="universe,price")
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--years", type=int, default=1)
    parser.add_argument("--start-date", type=str, default="")
    parser.add_argument("--end-date", type=str, default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    return parser


def date_range(args: argparse.Namespace) -> tuple[str, str]:
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else end - timedelta(days=365 * args.years + 90)
    )
    return start.isoformat(), end.isoformat()


def parse_endpoints(value: str) -> list[str]:
    endpoints = [item.strip() for item in value.split(",") if item.strip()]
    unsupported = [endpoint for endpoint in endpoints if endpoint not in SUPPORTED_ENDPOINTS]
    if unsupported:
        raise SystemExit(f"Unsupported endpoints: {', '.join(unsupported)}")
    return endpoints


def parse_symbols(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def ensure_db_timeout_defaults(config: DatabaseConfig) -> DatabaseConfig:
    updates: dict[str, int] = {}
    if not getattr(config, "connect_timeout", 0):
        diag(
            "db_timeout_warning",
            field="connect_timeout",
            action="using_default",
            value=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )
        updates["connect_timeout"] = DEFAULT_CONNECT_TIMEOUT_SECONDS
    if not getattr(config, "statement_timeout_ms", 0):
        diag(
            "db_timeout_warning",
            field="statement_timeout_ms",
            action="using_default",
            value=DEFAULT_STATEMENT_TIMEOUT_MS,
        )
        updates["statement_timeout_ms"] = DEFAULT_STATEMENT_TIMEOUT_MS
    return replace(config, **updates) if updates else config


def log_db_config(config: DatabaseConfig) -> None:
    statement_timeout_ms = getattr(config, "statement_timeout_ms", 0)
    connect_timeout = getattr(config, "connect_timeout", 0)
    diag(
        "db_config",
        host=mask_optional_host(config.host),
        port=config.port,
        db_name=mask_optional_identifier(config.dbname),
        user=mask_optional_identifier(config.user),
        connect_timeout=connect_timeout if connect_timeout else "missing",
        statement_timeout_ms=statement_timeout_ms if statement_timeout_ms else "missing",
        idle_timeout_ms=getattr(config, "idle_timeout_ms", "missing"),
    )
    if connect_timeout <= 0:
        diag("db_timeout_warning", field="connect_timeout", issue="not_positive")
    if statement_timeout_ms <= 0:
        diag("db_timeout_warning", field="statement_timeout_ms", issue="not_positive")


def log_session_timeout_settings(conn) -> None:
    for setting in ["statement_timeout", "idle_in_transaction_session_timeout"]:
        started = time.perf_counter()
        try:
            rows, _columns = fetch_all_with_diagnostics(
                conn,
                f"SHOW {setting}",
                None,
                {"endpoint": "db_session", "stage": f"show_{setting}"},
            )
        except Exception as exc:
            diag(
                "db_session_timeout_check_failed",
                setting=setting,
                error=type(exc).__name__,
                message=safe_error_message(exc),
            )
            rollback_after_db_error(conn, {"endpoint": "db_session", "setting": setting})
            continue
        value = rows[0][0] if rows else ""
        diag(
            "db_session_timeout",
            setting=setting,
            value=value,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )


def summarize_params(params: dict[str, object] | None) -> dict[str, object]:
    if not params:
        return {}
    result: dict[str, object] = {}
    symbols = params.get("symbols")
    if isinstance(symbols, list):
        result["symbols_count"] = len(symbols)
        result["symbol_first"] = symbols[0] if symbols else ""
    elif symbols is not None:
        result["symbols"] = "set"
    for key in ["start_date", "end_date"]:
        if key in params:
            result[key] = params[key]
    return result


def fetch_all_with_diagnostics(
    conn,
    query,
    params: dict[str, object] | None,
    context: dict[str, object],
) -> tuple[list[tuple[object, ...]], list[str]]:
    safe_context = {
        "endpoint": context.get("endpoint", "unknown"),
        "schema": context.get("schema", ""),
        "table": context.get("table", ""),
        "symbol_index": context.get("symbol_index", ""),
        "symbols_count": context.get("symbols_count", ""),
        "db_symbol": context.get("db_symbol", ""),
        "window_index": context.get("window_index", ""),
        "windows_count": context.get("windows_count", ""),
        "chunk_id": context.get("chunk_id", ""),
        "limit": context.get("limit", "none"),
        "offset": context.get("offset", "none"),
        "stage": context.get("stage", "query"),
        "query_type": type(query).__name__,
    }
    safe_context.update(summarize_params(params))
    with conn.cursor() as cur:
        execute_start = time.perf_counter()
        diag("query_execute_before", **safe_context)
        if params is None:
            cur.execute(query)
        else:
            cur.execute(query, params)
        diag(
            "query_execute_after",
            elapsed_ms=int((time.perf_counter() - execute_start) * 1000),
            **safe_context,
        )
        fetch_start = time.perf_counter()
        diag("query_fetchall_before", **safe_context)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        diag(
            "query_fetchall_after",
            rows=len(rows),
            columns_count=len(columns),
            elapsed_ms=int((time.perf_counter() - fetch_start) * 1000),
            **safe_context,
        )
    return rows, columns


def fetch_information_schema_with_diagnostics(conn) -> pd.DataFrame:
    started = time.perf_counter()
    query = (
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY table_schema, table_name, ordinal_position"
    )
    rows, columns = fetch_all_with_diagnostics(
        conn,
        query,
        None,
        {
            "endpoint": "information_schema",
            "stage": "fetch_schema",
            "limit": "none",
            "offset": "none",
        },
    )
    frame = pd.DataFrame(rows, columns=columns)
    diag(
        "information_schema_loaded",
        rows=frame.shape[0],
        columns=frame.shape[1],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return frame.rename(
        columns={
            "table_schema": "schema",
            "table_name": "table",
            "column_name": "column",
            "data_type": "data_type",
        }
    )


def validate_query_windows(
    endpoint: str,
    db_symbol: str,
    windows: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    validated: list[tuple[str, str]] = []
    previous: tuple[str, str] | None = None
    for index, window in enumerate(windows, start=1):
        query_start, query_end = window
        diag(
            "query_window_plan",
            endpoint=endpoint,
            db_symbol=db_symbol,
            window_index=index,
            windows_count=len(windows),
            start_date=query_start,
            end_date=query_end,
            chunk_id=f"{endpoint}:{db_symbol}:{index}/{len(windows)}",
            limit="none",
            offset="none",
            pagination="per_symbol_date_windows",
        )
        if pd.Timestamp(query_start) > pd.Timestamp(query_end):
            raise RuntimeError(
                f"Invalid query window for {endpoint} {db_symbol}: {query_start}>{query_end}"
            )
        if window in seen:
            raise RuntimeError(
                f"Repeated query window for {endpoint} {db_symbol}: {query_start}..{query_end}"
            )
        if previous and window == previous:
            raise RuntimeError(
                f"Non-advancing query window for {endpoint} {db_symbol}: {query_start}..{query_end}"
            )
        seen.add(window)
        validated.append(window)
        previous = window
    return validated


def cache_file_size(path: Path) -> int | str:
    return path.stat().st_size if path.exists() else "missing"


def write_cache_with_diagnostics(
    frame: pd.DataFrame,
    path: Path,
    required_columns: list[str],
    context: dict[str, object],
) -> None:
    started = time.perf_counter()
    diag(
        "cache_write_before",
        endpoint=context.get("endpoint", ""),
        db_symbol=context.get("db_symbol", ""),
        path=path,
        rows=frame.shape[0],
        columns=frame.shape[1],
        existing_size_bytes=cache_file_size(path),
    )
    atomic_write_csv(frame, path, required_columns)
    diag(
        "cache_write_after",
        endpoint=context.get("endpoint", ""),
        db_symbol=context.get("db_symbol", ""),
        path=path,
        rows=frame.shape[0],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        size_bytes=cache_file_size(path),
    )


def write_dataframe_csv_with_diagnostics(
    frame: pd.DataFrame, path: Path, **to_csv_kwargs: object
) -> None:
    started = time.perf_counter()
    diag(
        "csv_write_before",
        path=path,
        rows=frame.shape[0],
        columns=frame.shape[1],
        existing_size_bytes=cache_file_size(path),
    )
    frame.to_csv(path, **to_csv_kwargs)
    diag(
        "csv_write_after",
        path=path,
        rows=frame.shape[0],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        size_bytes=cache_file_size(path),
    )


def main() -> None:
    args = build_parser().parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    started_at = datetime.now().isoformat(timespec="seconds")
    wall_start = time.perf_counter()
    endpoints = parse_endpoints(args.endpoints)
    start_date, end_date = date_range(args)
    mapping = load_db_mapping(args.mapping)
    db_config = ensure_db_timeout_defaults(DatabaseConfig.from_env())
    processed_dir = ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    diag(
        "run_start",
        endpoints=",".join(endpoints),
        years=args.years,
        start_date=start_date,
        end_date=end_date,
        refresh_existing=args.refresh_existing,
        max_symbols=args.max_symbols if args.max_symbols is not None else "none",
    )
    log_db_config(db_config)

    diag("db_connect_before", pool="none")
    with connect_database(db_config) as conn:
        diag("db_connect_after", elapsed_ms=int((time.perf_counter() - wall_start) * 1000))
        log_session_timeout_settings(conn)
        schema = fetch_information_schema_with_diagnostics(conn)
        available = available_columns_from_schema(schema)
        mapping = apply_price_adjustment_probe(mapping, available)
        planner = SyncPlanner(ROOT, mapping, available)
        symbols = parse_symbols(args.symbols)
        if not symbols and "universe" in endpoints:
            symbols = sync_universe(conn, mapping, start_date, end_date, args, dry_run=args.dry_run)
        if args.max_symbols is not None:
            symbols = symbols[: args.max_symbols]

        if args.dry_run:
            rows = planner.dry_run(endpoints, symbols, start_date, end_date)
            write_dataframe_csv_with_diagnostics(
                pd.DataFrame(rows), processed_dir / "db_sync_dry_run.csv", index=False
            )
            print(pd.DataFrame(rows).to_string(index=False))
            return

        warnings: list[dict[str, object]] = []
        summary: list[dict[str, object]] = []
        for endpoint in endpoints:
            if endpoint == "universe":
                continue
            diag("endpoint_sync_start", endpoint=endpoint, symbols_count=len(symbols))
            summary.extend(
                sync_endpoint(
                    conn, mapping, endpoint, symbols, start_date, end_date, args, warnings
                )
            )
            diag("endpoint_sync_end", endpoint=endpoint, summary_rows=len(summary))
        output = write_sync_outputs(
            processed_dir,
            summary,
            warnings,
            args,
            db_config,
            endpoints,
            symbols,
            start_date,
            end_date,
            run_id,
            started_at,
            elapsed_seconds=time.perf_counter() - wall_start,
            mapping=mapping,
        )
        print_sync_summary(output, summary, processed_dir)


def sync_universe(
    conn,
    mapping: dict[str, object],
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    dry_run: bool,
) -> list[str]:
    endpoint = mapping["endpoints"].get("universe", {})
    if not endpoint.get("enabled", False):
        return []
    plan = build_query_plan("universe", endpoint, [], start_date, end_date)
    diag(
        "query_plan_ready",
        endpoint="universe",
        schema=plan.schema,
        table=plan.table,
        years=args.years,
        start_date=start_date,
        end_date=end_date,
        symbols_count=0,
        selected_columns=len(plan.selected_columns),
        limit="none",
        offset="none",
        chunk_id="universe:all",
    )
    if dry_run:
        return []
    rows, columns = fetch_all_with_diagnostics(
        conn,
        plan.query,
        plan.params,
        {
            "endpoint": "universe",
            "schema": plan.schema,
            "table": plan.table,
            "symbols_count": 0,
            "chunk_id": "universe:all",
            "limit": "none",
            "offset": "none",
        },
    )
    raw = pd.DataFrame(rows, columns=columns)
    if raw.empty:
        diag("universe_empty", start_date=start_date, end_date=end_date)
        return []
    frame = transform_endpoint_frame("universe", raw, endpoint)
    path = ROOT / "data" / "cache" / "universe_spot.csv"
    write_cache_with_diagnostics(
        frame, path, ["code", "name"], {"endpoint": "universe", "db_symbol": "all"}
    )
    symbols = (
        frame["db_symbol"].astype(str).tolist()
        if "db_symbol" in frame
        else frame["code"].astype(str).tolist()
    )
    diag(
        "universe_symbols_loaded",
        symbols_count=len(symbols),
        returned_symbols=args.max_symbols if args.max_symbols else len(symbols),
    )
    return symbols[: args.max_symbols] if args.max_symbols else symbols


def sync_price(
    conn,
    mapping: dict[str, object],
    symbols: list[str],
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    warnings: list[dict[str, object]],
    root_dir: Path = ROOT,
) -> list[dict[str, object]]:
    return sync_endpoint(
        conn, mapping, "price", symbols, start_date, end_date, args, warnings, root_dir=root_dir
    )


def sync_endpoint(
    conn,
    mapping: dict[str, object],
    endpoint_name: str,
    symbols: list[str],
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    warnings: list[dict[str, object]],
    root_dir: Path = ROOT,
) -> list[dict[str, object]]:
    endpoint = mapping["endpoints"].get(endpoint_name, {})
    if not endpoint.get("enabled", False):
        return []
    summary = []
    diag("endpoint_symbol_loop_start", endpoint=endpoint_name, symbols_count=len(symbols))
    for symbol_index, symbol in enumerate(symbols, start=1):
        symbol_start = time.perf_counter()
        db_symbol, code, exchange = normalize_db_symbol(symbol)
        cache_path = root_dir / "data" / "cache" / endpoint_name / f"{code}.csv"
        cache_date_column = cache_date_column_for_endpoint(endpoint_name)
        before = cache_file_stats(cache_path, cache_date_column)
        status, windows = cache_query_windows(
            cache_path, start_date, end_date, args.refresh_existing, cache_date_column
        )
        windows = validate_query_windows(endpoint_name, db_symbol, windows)
        diag(
            "symbol_sync_start",
            endpoint=endpoint_name,
            symbol_index=symbol_index,
            symbols_count=len(symbols),
            db_symbol=db_symbol,
            code=code,
            exchange=exchange,
            status=status,
            windows_count=len(windows),
            cache_rows_before=before["rows"],
            cache_min_date=before["min_date"],
            cache_max_date=before["max_date"],
        )
        if status == "skipped":
            summary.append(
                row_summary(
                    db_symbol,
                    code,
                    exchange,
                    endpoint_name,
                    status,
                    start_date,
                    end_date,
                    before,
                    before,
                    windows,
                    0,
                    symbol_start,
                )
            )
            diag(
                "symbol_sync_skipped",
                endpoint=endpoint_name,
                symbol_index=symbol_index,
                symbols_count=len(symbols),
                db_symbol=db_symbol,
                elapsed_ms=int((time.perf_counter() - symbol_start) * 1000),
            )
            continue
        raw_parts = []
        try:
            for window_index, (query_start, query_end) in enumerate(windows, start=1):
                chunk_id = f"{endpoint_name}:{db_symbol}:{window_index}/{len(windows)}"
                if endpoint_name == "industry_sw":
                    rows, columns = fetch_industry_sw_rows(
                        conn,
                        endpoint,
                        [db_symbol],
                        {
                            "endpoint": endpoint_name,
                            "schema": endpoint.get("schema", ""),
                            "table": endpoint.get("table", ""),
                            "symbol_index": symbol_index,
                            "symbols_count": len(symbols),
                            "db_symbol": db_symbol,
                            "start_date": query_start,
                            "end_date": query_end,
                            "window_index": window_index,
                            "windows_count": len(windows),
                            "chunk_id": chunk_id,
                            "limit": "none",
                            "offset": "none",
                        },
                    )
                else:
                    plan = build_query_plan(
                        endpoint_name, endpoint, [db_symbol], query_start, query_end
                    )
                    diag(
                        "query_plan_ready",
                        endpoint=endpoint_name,
                        schema=plan.schema,
                        table=plan.table,
                        symbol_index=symbol_index,
                        symbols_count=len(symbols),
                        db_symbol=db_symbol,
                        start_date=query_start,
                        end_date=query_end,
                        selected_columns=len(plan.selected_columns),
                        window_index=window_index,
                        windows_count=len(windows),
                        chunk_id=chunk_id,
                        limit="none",
                        offset="none",
                    )
                    rows, columns = fetch_all_with_diagnostics(
                        conn,
                        plan.query,
                        plan.params,
                        {
                            "endpoint": endpoint_name,
                            "schema": plan.schema,
                            "table": plan.table,
                            "symbol_index": symbol_index,
                            "symbols_count": len(symbols),
                            "db_symbol": db_symbol,
                            "window_index": window_index,
                            "windows_count": len(windows),
                            "chunk_id": chunk_id,
                            "limit": "none",
                            "offset": "none",
                        },
                    )
                if rows:
                    raw_parts.append(pd.DataFrame(rows, columns=columns))
        except Exception as exc:
            diag(
                "symbol_sync_failed",
                endpoint=endpoint_name,
                symbol_index=symbol_index,
                symbols_count=len(symbols),
                db_symbol=db_symbol,
                error=type(exc).__name__,
                message=safe_error_message(exc),
            )
            rollback_after_db_error(
                conn,
                {
                    "endpoint": endpoint_name,
                    "symbol_index": symbol_index,
                    "symbols_count": len(symbols),
                    "db_symbol": db_symbol,
                },
            )
            after = cache_file_stats(cache_path, cache_date_column)
            summary.append(
                row_summary(
                    db_symbol,
                    code,
                    exchange,
                    endpoint_name,
                    "failed",
                    start_date,
                    end_date,
                    before,
                    after,
                    windows,
                    0,
                    symbol_start,
                )
            )
            continue
        raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
        if raw.empty:
            empty_status = "backfill_no_rows" if status == "partial" else "no_rows"
            after = cache_file_stats(cache_path, cache_date_column)
            diag(
                "symbol_sync_no_rows",
                endpoint=endpoint_name,
                symbol_index=symbol_index,
                symbols_count=len(symbols),
                db_symbol=db_symbol,
                status=empty_status,
                elapsed_ms=int((time.perf_counter() - symbol_start) * 1000),
            )
            summary.append(
                row_summary(
                    db_symbol,
                    code,
                    exchange,
                    endpoint_name,
                    empty_status,
                    start_date,
                    end_date,
                    before,
                    after,
                    windows,
                    0,
                    symbol_start,
                )
            )
            continue
        frame = transform_endpoint_frame(endpoint_name, raw, endpoint)
        frame["code"] = code
        existing = (
            read_cache_csv(cache_path)
            if cache_path.exists() and not args.refresh_existing
            else pd.DataFrame()
        )
        combined = pd.concat([existing, frame], ignore_index=True) if not existing.empty else frame
        out = deduplicate_cache_frame(combined, endpoint_name, warnings)
        write_cache_with_diagnostics(
            out,
            cache_path,
            required_columns_for_endpoint(endpoint_name),
            {"endpoint": endpoint_name, "db_symbol": db_symbol},
        )
        after = cache_file_stats(cache_path, cache_date_column)
        summary.append(
            row_summary(
                db_symbol,
                code,
                exchange,
                endpoint_name,
                status,
                start_date,
                end_date,
                before,
                after,
                windows,
                len(frame),
                symbol_start,
            )
        )
        diag(
            "symbol_sync_end",
            endpoint=endpoint_name,
            symbol_index=symbol_index,
            symbols_count=len(symbols),
            db_symbol=db_symbol,
            rows_fetched=len(frame),
            cache_rows_after=after["rows"],
            elapsed_ms=int((time.perf_counter() - symbol_start) * 1000),
        )
    return summary


def transform_endpoint_frame(
    endpoint: str, raw: pd.DataFrame, mapping: dict[str, object]
) -> pd.DataFrame:
    fields = {**mapping.get("required_fields", {}), **mapping.get("optional_fields", {})}
    date_column = mapping.get("date_column") or mapping.get("report_date_column")
    if endpoint in {"cashflow", "profit"}:
        rename = {mapping["symbol_column"]: "db_symbol", date_column: "report_date"}
        ann_column = mapping.get("ann_date_column") or mapping.get("pub_date_column")
        if ann_column:
            rename[str(ann_column)] = "announce_date"
    elif endpoint == "industry_sw":
        rename = {mapping["symbol_column"]: "db_symbol"}
    else:
        rename = {mapping["symbol_column"]: "db_symbol", date_column: "date"}
    rename.update({source: output for output, source in fields.items() if source in raw.columns})
    frame = raw.rename(columns=rename)
    if "db_symbol" in frame:
        normalized = frame["db_symbol"].map(normalize_db_symbol)
        frame["code"] = normalized.map(lambda item: item[1])
        frame["exchange"] = normalized.map(lambda item: item[2])
    frame = convert_units(frame, mapping)
    if endpoint == "price" and "adjusted_close" not in frame and {"close", "adj_factor"}.issubset(frame.columns):
        frame["adjusted_close"] = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(
            frame["adj_factor"], errors="coerce"
        )
    if endpoint == "industry_sw":
        frame = normalize_industry_sw_dates(frame)
        frame = ensure_industry_sw_aliases(frame)
    return frame


def fetch_industry_sw_rows(
    conn,
    mapping: dict[str, object],
    symbols: list[str],
    context: dict[str, object] | None = None,
) -> tuple[list[tuple[object, ...]], list[str]]:
    _psycopg, sql = require_psycopg()
    schema = str(mapping["schema"])
    map_table = str(mapping["table"])
    symbol_column = str(mapping["symbol_column"])
    category_schema = str(mapping.get("category_schema", schema))
    category_table = str(mapping.get("category_table", "dim_industry_categories_sw"))
    category_code_column = str(mapping.get("category_code_column", "index_code"))
    category_name_column = str(mapping.get("category_name_column", "industry_name"))
    query = sql.SQL(
        """
        SELECT
          m.{symbol_column} AS company_id,
          m.l1_index_code,
          m.l2_index_code,
          m.l3_index_code,
          l1.{category_name_column} AS l1_industry_name,
          l2.{category_name_column} AS l2_industry_name,
          l3.{category_name_column} AS l3_industry_name,
          m.in_date,
          m.out_date,
          m.is_new,
          m.updated_at
        FROM {map_table} m
        LEFT JOIN {category_table} l1 ON l1.{category_code_column} = m.l1_index_code
        LEFT JOIN {category_table} l2 ON l2.{category_code_column} = m.l2_index_code
        LEFT JOIN {category_table} l3 ON l3.{category_code_column} = m.l3_index_code
        WHERE m.{symbol_column} = ANY(%(symbols)s)
        """
    ).format(
        symbol_column=sql.Identifier(symbol_column),
        category_name_column=sql.Identifier(category_name_column),
        map_table=sql.Identifier(schema, map_table),
        category_table=sql.Identifier(category_schema, category_table),
        category_code_column=sql.Identifier(category_code_column),
    )
    diag(
        "query_plan_ready",
        endpoint="industry_sw",
        schema=schema,
        table=map_table,
        symbols_count=len(symbols),
        start_date=(context or {}).get("start_date", ""),
        end_date=(context or {}).get("end_date", ""),
        selected_columns=11,
        limit="none",
        offset="none",
        chunk_id=(context or {}).get("chunk_id", "industry_sw:unknown"),
    )
    return fetch_all_with_diagnostics(
        conn,
        query,
        {"symbols": symbols},
        {
            "endpoint": "industry_sw",
            "schema": schema,
            "table": map_table,
            "symbols_count": len(symbols),
            "limit": "none",
            "offset": "none",
            **(context or {}),
        },
    )


def required_columns_for_endpoint(endpoint: str) -> list[str]:
    if endpoint == "industry_sw":
        return [
            "code",
            "sw_l1_code",
            "sw_l2_code",
            "sw_l3_code",
            "sw_l1_name",
            "sw_l2_name",
            "sw_l3_name",
            "in_date",
            "out_date",
        ]
    if endpoint == "price":
        return ["code", "date", "close"]
    if endpoint == "cashflow":
        return ["code", "report_date", "announce_date", "operating_cashflow"]
    if endpoint == "profit":
        return ["code", "report_date", "announce_date", "revenue", "parent_net_profit"]
    return ["code"]


def cache_date_column_for_endpoint(endpoint: str) -> str:
    if endpoint == "industry_sw":
        return "in_date"
    if endpoint in {"cashflow", "profit"}:
        return "report_date"
    return "date"


def cache_query_windows(
    path: Path,
    start_date: str,
    end_date: str,
    refresh_existing: bool,
    date_column: str = "date",
) -> tuple[str, list[tuple[str, str]]]:
    if refresh_existing or not path.exists():
        return "success", [(start_date, end_date)]
    cached = read_cache_csv(path)
    if cached.empty or date_column not in cached:
        return "success", [(start_date, end_date)]
    dates = parse_cache_date(cached[date_column]).dropna()
    if dates.empty:
        return "success", [(start_date, end_date)]
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    min_cached = dates.min()
    max_cached = dates.max()
    if min_cached <= start and max_cached >= end:
        return "skipped", []
    windows = []
    if min_cached > start:
        left_end = (min_cached - pd.Timedelta(days=1)).date().isoformat()
        windows.append((start_date, left_end))
    if max_cached < end:
        right_start = (max_cached + pd.Timedelta(days=1)).date().isoformat()
        windows.append((right_start, end_date))
    return "partial", windows or [(start_date, end_date)]


def row_summary(
    db_symbol: str,
    code: str,
    exchange: str,
    endpoint: str,
    status: str,
    start_date: str,
    end_date: str,
    cache_before: dict[str, object],
    cache_after: dict[str, object],
    query_windows: list[tuple[str, str]],
    rows_fetched: int,
    started_at: float,
) -> dict[str, object]:
    return {
        "db_symbol": db_symbol,
        "code": code,
        "exchange": exchange,
        "endpoint": endpoint,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "cache_before_rows": cache_before["rows"],
        "cache_before_min_date": cache_before["min_date"],
        "cache_before_max_date": cache_before["max_date"],
        "query_windows": format_query_windows(query_windows),
        "rows_fetched": rows_fetched,
        "cache_after_rows": cache_after["rows"],
        "cache_after_min_date": cache_after["min_date"],
        "cache_after_max_date": cache_after["max_date"],
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
    }


def cache_file_stats(path: Path, date_column: str = "date") -> dict[str, object]:
    if not path.exists():
        return {"rows": 0, "min_date": "", "max_date": ""}
    frame = read_cache_csv(path)
    if frame.empty or date_column not in frame:
        return {"rows": int(frame.shape[0]), "min_date": "", "max_date": ""}
    dates = parse_cache_date(frame[date_column]).dropna()
    return {
        "rows": int(frame.shape[0]),
        "min_date": dates.min().date().isoformat() if not dates.empty else "",
        "max_date": dates.max().date().isoformat() if not dates.empty else "",
    }


def format_query_windows(windows: list[tuple[str, str]]) -> str:
    return ";".join(f"{start}..{end}" for start, end in windows)


def write_sync_outputs(
    processed_dir: Path,
    summary: list[dict[str, object]],
    warnings_rows: list[dict[str, object]],
    args: argparse.Namespace,
    db_config: DatabaseConfig,
    endpoints: list[str],
    symbols: list[str],
    start_date: str,
    end_date: str,
    run_id: str,
    started_at: str,
    elapsed_seconds: float = 0.0,
    mapping: dict[str, object] | None = None,
) -> dict[str, object]:
    run_dir = processed_dir / "db_sync_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_frame = pd.DataFrame(summary)
    warnings_frame = pd.DataFrame(warnings_rows)
    latest_summary = processed_dir / "db_sync_summary.csv"
    latest_warnings = processed_dir / "db_sync_warnings.csv"
    run_summary = run_dir / "db_sync_summary.csv"
    run_warnings = run_dir / "db_sync_warnings.csv"
    write_dataframe_csv_with_diagnostics(
        summary_frame, run_summary, index=False, encoding="utf-8-sig"
    )
    write_dataframe_csv_with_diagnostics(
        summary_frame, latest_summary, index=False, encoding="utf-8-sig"
    )
    write_dataframe_csv_with_diagnostics(
        warnings_frame, run_warnings, index=False, encoding="utf-8-sig"
    )
    write_dataframe_csv_with_diagnostics(
        warnings_frame, latest_warnings, index=False, encoding="utf-8-sig"
    )
    status_counts = (
        summary_frame["status"].value_counts().to_dict() if "status" in summary_frame else {}
    )
    queried = int((summary_frame.get("query_windows", pd.Series(dtype=str)).fillna("") != "").sum())
    rows_fetched = int(
        pd.to_numeric(summary_frame.get("rows_fetched", pd.Series(dtype=int)), errors="coerce")
        .fillna(0)
        .sum()
    )
    ended_at = datetime.now().isoformat(timespec="seconds")
    manifest = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "db_host": mask_host(db_config.host),
        "db_port": db_config.port,
        "db_name": mask_optional_identifier(db_config.dbname),
        "db_user": mask_optional_identifier(db_config.user),
        "endpoints": endpoints,
        "symbols_count": len(symbols),
        "start_date": start_date,
        "end_date": end_date,
        "refresh_existing": bool(args.refresh_existing),
        "status_counts": status_counts,
        "queried_symbols": queried,
        "skipped_symbols": int(status_counts.get("skipped", 0)),
        "failed_symbols": int(status_counts.get("failed", 0)),
        "rows_fetched": rows_fetched,
        "average_ms_per_queried_symbol": average_ms_per_queried(summary_frame),
        "latest_summary_overwritten": str(latest_summary),
    }
    manifest.update(price_adjustment_manifest(mapping))
    manifest_path = run_dir / "db_sync_manifest.json"
    manifest_start = time.perf_counter()
    diag(
        "manifest_write_before",
        path=manifest_path,
        records=len(manifest),
        existing_size_bytes=cache_file_size(manifest_path),
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    diag(
        "manifest_write_after",
        path=manifest_path,
        records=len(manifest),
        elapsed_ms=int((time.perf_counter() - manifest_start) * 1000),
        size_bytes=cache_file_size(manifest_path),
    )
    return {"run_dir": run_dir, "manifest": manifest, "latest_summary": latest_summary}


def price_adjustment_manifest(mapping: dict[str, object] | None) -> dict[str, object]:
    if not mapping:
        return {}
    price = mapping.get("endpoints", {}).get("price", {})
    if not isinstance(price, dict):
        return {}
    probe = price.get("adjustment_probe", {})
    if not isinstance(probe, dict):
        return {}
    return {
        "price_adjustment": price.get("adjustment", "unknown"),
        "price_adjustment_probe_table": probe.get("table", ""),
        "price_adjustment_fields_checked": probe.get("fields_checked", []),
        "price_adjustment_fields_found": probe.get("fields_found", []),
        "price_adjustment_warning": probe.get("warning", ""),
    }


def average_ms_per_queried(summary_frame: pd.DataFrame) -> float:
    if (
        summary_frame.empty
        or "query_windows" not in summary_frame
        or "elapsed_ms" not in summary_frame
    ):
        return 0.0
    queried = summary_frame[summary_frame["query_windows"].fillna("") != ""]
    if queried.empty:
        return 0.0
    elapsed = pd.to_numeric(queried["elapsed_ms"], errors="coerce").dropna()
    return round(float(elapsed.mean()), 3) if not elapsed.empty else 0.0


def mask_host(host: str) -> str:
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return ".".join(parts[:3] + ["***"])
    if len(host) <= 4:
        return "***"
    return f"{host[:2]}***{host[-2:]}"


def print_sync_summary(
    output: dict[str, object], summary: list[dict[str, object]], processed_dir: Path
) -> None:
    manifest = output["manifest"]
    status_counts = manifest["status_counts"]
    print(f"Sync run directory: {output['run_dir']}")
    print(f"Latest summary overwritten: {processed_dir / 'db_sync_summary.csv'}")
    print(f"Status counts: {status_counts}")
    print(
        f"Queried symbols: {manifest['queried_symbols']}; "
        f"skipped: {manifest['skipped_symbols']}; "
        f"failed: {manifest['failed_symbols']}"
    )
    print(f"Fetched rows: {manifest['rows_fetched']}")
    print(f"Elapsed seconds: {manifest['elapsed_seconds']}")
    print(f"Average ms per queried symbol: {manifest['average_ms_per_queried_symbol']}")


if __name__ == "__main__":
    main()
