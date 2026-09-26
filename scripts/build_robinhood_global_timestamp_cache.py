"""Import trusted NVDA/GME timestamps and validate the exact global cache locally."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import build_robinhood_five_token_panel as collector
from robinhood_timestamp_cache import insert_exact_timestamps, lookup_timestamps


ROOT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = ROOT / "sessions"
LEDGER = ROOT / "session_checkpoint.csv"
PANEL = ROOT / "five_token_unbalanced_session_panel.csv"
DATABASE = ROOT / "global_exact_block_timestamps.sqlite3"
REPORT = ROOT / "global_timestamp_cache_validation.json"
OVERLAP = ROOT / "nvda_gme_execution_block_overlap_summary.json"
TOKENS = ("NVDA", "GME")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def completed_rows() -> list[dict[str, str]]:
    with LEDGER.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return [
        row
        for row in rows
        if row["token_symbol"] in TOKENS and row["completion_status"].startswith("complete")
    ]


def session_sources(row: dict[str, str]) -> list[Path]:
    local = SESSIONS / row["token_symbol"] / row["market_open_date"]
    sources = [local]
    manifest_path = local / "reuse_manifest.json"
    if manifest_path.exists():
        sources.append(Path(read_json(manifest_path)["source_session_directory"]))
    return list(dict.fromkeys(path.resolve() for path in sources))


def timestamp_artifacts(rows: list[dict[str, str]]) -> list[Path]:
    paths: list[Path] = []
    for row in rows:
        for directory in session_sources(row):
            for name in ("block_timestamps.json", "last_trade_1600_timestamps.json"):
                candidate = directory / name
                if candidate.exists():
                    paths.append(candidate)
    return list(dict.fromkeys(path.resolve() for path in paths))


def import_mapping(paths: list[Path]) -> tuple[dict[int, int], dict]:
    canonical: dict[int, int] = {}
    record_count = 0
    identical_duplicates = 0
    for path in paths:
        mapping = read_json(path)
        for raw_block, raw_timestamp in mapping.items():
            block, timestamp = int(raw_block), int(raw_timestamp)
            record_count += 1
            if block in canonical:
                if canonical[block] != timestamp:
                    raise RuntimeError(
                        f"historical timestamp conflict at block {block}: "
                        f"{canonical[block]} != {timestamp} in {path}"
                    )
                identical_duplicates += 1
            else:
                canonical[block] = timestamp
    return canonical, {
        "source_artifacts_scanned": len(paths),
        "mapping_records_scanned": record_count,
        "unique_exact_mappings": len(canonical),
        "identical_duplicate_records": identical_duplicates,
        "conflicting_records": 0,
    }


def evenly_spaced(values: list[int], count: int) -> list[int]:
    if len(values) <= count:
        return values
    return [values[index * (len(values) - 1) // (count - 1)] for index in range(count)]


def decoded_path(row: dict[str, str]) -> Path:
    local = SESSIONS / row["token_symbol"] / row["market_open_date"]
    direct = local / "decoded_swaps.csv"
    if direct.exists():
        return direct
    manifest = read_json(local / "reuse_manifest.json")
    return Path(manifest["source_decoded_swaps"])


def execution_blocks(row: dict[str, str]) -> set[int]:
    with decoded_path(row).open(newline="", encoding="utf-8-sig") as handle:
        return {int(item["block_number"]) for item in csv.DictReader(handle)}


class FakeResponse:
    status_code = 200

    def __init__(self, payload: list[dict]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return [
            {
                "jsonrpc": "2.0",
                "id": item["id"],
                "result": {"timestamp": hex(1_700_000_000 + int(item["params"][0], 16))},
            }
            for item in self.payload
        ]


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def post(self, _url, *, json, **_kwargs) -> FakeResponse:
        self.calls.append(json)
        return FakeResponse(json)


class NoPostSession:
    def post(self, *_args, **_kwargs):
        raise AssertionError("unexpected RPC")


class RateLimitedResponse:
    status_code = 429


class RetrySession:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, _url, *, json, **_kwargs):
        self.calls += 1
        return RateLimitedResponse() if self.calls == 1 else FakeResponse(json)


def validate_mocked_fallback() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        database = base / "cache.sqlite3"
        session_one = base / "session_one.json"
        session_two = base / "session_two.json"
        required = list(range(10_000, 10_205))
        fake = FakeSession()
        with (
            patch.object(collector, "GLOBAL_TIMESTAMP_CACHE", database),
            patch.object(collector.requests, "Session", return_value=fake),
            patch.object(collector.time, "sleep", side_effect=AssertionError("unexpected pacing")),
        ):
            first, first_stats = collector.batch_timestamps(required, session_one)
        with (
            patch.object(collector, "GLOBAL_TIMESTAMP_CACHE", database),
            patch.object(collector.requests, "Session", return_value=NoPostSession()),
        ):
            second, second_stats = collector.batch_timestamps(required, session_two)
        retry_session = RetrySession()
        sleeps: list[int] = []
        with (
            patch.object(collector, "GLOBAL_TIMESTAMP_CACHE", database),
            patch.object(collector.requests, "Session", return_value=retry_session),
            patch.object(collector.time, "sleep", side_effect=sleeps.append),
        ):
            _, retry_stats = collector.batch_timestamps([999_999_999], base / "retry.json")
        expected = {block: 1_700_000_000 + block for block in required}
        passed = (
            first == expected
            and second == expected
            and [len(payload) for payload in fake.calls] == [100, 100, 5]
            and all(item["method"] == "eth_getBlockByNumber" for payload in fake.calls for item in payload)
            and first_stats["timestamp_rpc_batch_requests"] == 3
            and second_stats["timestamp_rpc_batch_requests"] == 0
            and second_stats["timestamps_reused_from_global_cache"] == len(required)
            and retry_session.calls == 2
            and retry_stats["timestamp_retry_events"] == 1
            and retry_stats["timestamp_rate_limit_events"] == 1
            and sleeps == [2]
        )
        return {
            "passed": passed,
            "rpc_method": "eth_getBlockByNumber",
            "serial_batch_sizes": [len(payload) for payload in fake.calls],
            "proactive_sleep_calls": 0,
            "cold_rpc_batch_requests": first_stats["timestamp_rpc_batch_requests"],
            "warm_rpc_batch_requests": second_stats["timestamp_rpc_batch_requests"],
            "warm_global_cache_hits": second_stats["timestamps_reused_from_global_cache"],
            "bounded_retry_validation": {
                "passed": retry_session.calls == 2 and sleeps == [2],
                "requests_after_one_429": retry_session.calls,
                "rate_limit_events": retry_stats["timestamp_rate_limit_events"],
                "backoff_seconds": sleeps,
            },
        }


def main() -> None:
    rows = completed_rows()
    if len(rows) != 63:
        raise RuntimeError(f"expected 63 completed NVDA/GME sessions, found {len(rows)}")
    before = {"ledger_sha256": file_hash(LEDGER), "panel_sha256": file_hash(PANEL)}
    paths = timestamp_artifacts(rows)
    canonical, import_stats = import_mapping(paths)
    inserted, already_identical = insert_exact_timestamps(DATABASE, canonical)

    with sqlite3.connect(DATABASE) as connection:
        database_rows = int(connection.execute("SELECT COUNT(*) FROM block_timestamps").fetchone()[0])
        schema = [list(row) for row in connection.execute("PRAGMA table_info(block_timestamps)")]

    ordered = sorted(canonical)
    sample_blocks = evenly_spaced(ordered, 5_000)
    sample_found = lookup_timestamps(DATABASE, sample_blocks)
    exact_matches = sum(sample_found.get(block) == canonical[block] for block in sample_blocks)

    token_blocks = {token: set() for token in TOKENS}
    dated_blocks = {token: {} for token in TOKENS}
    warm_missing = 0
    warm_mismatches = 0
    for row in rows:
        blocks = execution_blocks(row)
        token_blocks[row["token_symbol"]].update(blocks)
        dated_blocks[row["token_symbol"]][row["market_open_date"]] = blocks
        found = lookup_timestamps(DATABASE, blocks)
        warm_missing += len(blocks - found.keys())
        warm_mismatches += sum(found.get(block) != canonical.get(block) for block in blocks)

    nvda, gme = token_blocks["NVDA"], token_blocks["GME"]
    intersection = nvda & gme
    common_dates = set(dated_blocks["NVDA"]) & set(dated_blocks["GME"])
    common_nvda = set().union(*(dated_blocks["NVDA"][date] for date in common_dates))
    common_gme = set().union(*(dated_blocks["GME"][date] for date in common_dates))
    common_intersection = common_nvda & common_gme
    audited_overlap = read_json(OVERLAP)["aggregate"]
    overlap_matches_audit = (
        len(common_nvda) == audited_overlap["nvda_unique_execution_blocks"]
        and len(common_gme) == audited_overlap["gme_unique_execution_blocks"]
        and len(common_intersection) == audited_overlap["intersection_count"]
    )

    performance_blocks = evenly_spaced(ordered, min(50_000, len(ordered)))
    started = time.perf_counter()
    performance_found = lookup_timestamps(DATABASE, performance_blocks)
    elapsed = time.perf_counter() - started

    fallback = validate_mocked_fallback()
    after = {"ledger_sha256": file_hash(LEDGER), "panel_sha256": file_hash(PANEL)}
    checks = {
        "no_historical_conflicts": import_stats["conflicting_records"] == 0,
        "database_covers_all_imported_mappings": len(lookup_timestamps(DATABASE, ordered)) == len(canonical),
        "deterministic_sample_exact": exact_matches == len(sample_blocks) and len(sample_blocks) >= 5_000,
        "warm_nvda_gme_replay_zero_rpc": warm_missing == 0 and warm_mismatches == 0,
        "overlap_reproduction_matches_existing_audit": overlap_matches_audit,
        "collector_mocked_miss_fallback": fallback["passed"],
        "ledger_and_panel_unchanged": before == after,
        "tsla_collection_not_started": not (SESSIONS / "TSLA").exists(),
    }
    classification = "GLOBAL_CACHE_READY" if all(checks.values()) else "GLOBAL_CACHE_NOT_READY"
    report = {
        "classification": classification,
        "checks": checks,
        "database": {
            "path": str(DATABASE.resolve()),
            "table": "block_timestamps",
            "schema": schema,
            "row_count": database_rows,
            "rows_inserted_this_run": inserted,
            "rows_already_present_identically": already_identical,
        },
        "historical_import": {
            **import_stats,
            "completed_sessions_scanned": len(rows),
            "completed_sessions_by_token": {
                token: sum(row["token_symbol"] == token for row in rows) for token in TOKENS
            },
            "source_artifacts": [str(path) for path in paths],
        },
        "deterministic_exact_sample": {
            "sample_size": len(sample_blocks),
            "exact_matches": exact_matches,
            "mismatches": len(sample_blocks) - exact_matches,
            "selection": "equally spaced over sorted imported block numbers",
        },
        "warm_replay": {
            "sessions": len(rows),
            "unique_execution_blocks_by_token": {token: len(blocks) for token, blocks in token_blocks.items()},
            "missing_cache_rows": warm_missing,
            "timestamp_mismatches": warm_mismatches,
            "rpc_calls": 0,
        },
        "nvda_first_then_gme": {
            "nvda_prior_execution_blocks_all_33_sessions": len(nvda),
            "gme_execution_blocks": len(gme),
            "cache_hits_from_prior_nvda_blocks": len(intersection),
            "cache_misses": len(gme - nvda),
            "hit_rate": len(intersection) / len(gme),
            "matches_existing_overlap_audit": overlap_matches_audit,
            "common_date_audit_counts": {
                "dates": len(common_dates),
                "nvda_unique_execution_blocks": len(common_nvda),
                "gme_unique_execution_blocks": len(common_gme),
                "intersection": len(common_intersection),
            },
        },
        "collector_mock_validation": fallback,
        "local_lookup_performance": {
            "lookup_count": len(performance_blocks),
            "rows_found": len(performance_found),
            "elapsed_seconds": elapsed,
            "lookups_per_second": len(performance_blocks) / elapsed,
        },
        "artifact_integrity": {"before": before, "after": after},
        "collection_state": {
            "completed_token_sessions": 63,
            "eligible_token_sessions": 170,
            "completed_by_token": {"NVDA": 33, "GME": 30},
            "tsla_started": (SESSIONS / "TSLA").exists(),
        },
        "network_calls": 0,
    }
    atomic_json(REPORT, report)
    print(json.dumps({key: report[key] for key in ("classification", "checks", "database", "historical_import", "deterministic_exact_sample", "warm_replay", "nvda_first_then_gme", "collector_mock_validation", "local_lookup_performance", "collection_state", "network_calls")}, indent=2))
    if classification != "GLOBAL_CACHE_READY":
        sys.exit(1)


if __name__ == "__main__":
    main()
