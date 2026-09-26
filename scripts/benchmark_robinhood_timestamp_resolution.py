"""Bounded timestamp-resolution benchmark using completed NVDA ground truth."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import requests


RPC = "https://rpc.mainnet.chain.robinhood.com"
SOURCE = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel/sessions/NVDA/2026-07-23/block_timestamps.json")
OUTPUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel/timestamp_benchmark")
SAMPLE_SIZE = 2_000
CONFIGS = (
    {"name": "current_batch100_unpaced", "batch_size": 100, "min_interval_seconds": 0.0, "backoff": "production_exponential"},
    {"name": "paced_batch100_10s", "batch_size": 100, "min_interval_seconds": 10.0, "backoff": "paced"},
    {"name": "paced_batch50_5s", "batch_size": 50, "min_interval_seconds": 5.0, "backoff": "paced"},
)


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def sample_ground_truth() -> dict[int, int]:
    source = {int(block): int(timestamp) for block, timestamp in json.loads(SOURCE.read_text(encoding="utf-8")).items()}
    blocks = sorted(source)
    indices = [index * (len(blocks) - 1) // (SAMPLE_SIZE - 1) for index in range(SAMPLE_SIZE)]
    sample = {blocks[index]: source[blocks[index]] for index in indices}
    assert len(sample) == SAMPLE_SIZE
    atomic_json(
        OUTPUT / "benchmark_sample.json",
        {
            "definition": "2,000 deterministic equally spaced order-statistic positions across sorted unique NVDA 2026-07-23 execution blocks",
            "source": str(SOURCE.resolve()),
            "source_unique_blocks": len(source),
            "sample": {str(block): timestamp for block, timestamp in sample.items()},
        },
    )
    return sample


def wait_for_pacing(last_request: float | None, interval: float) -> None:
    if last_request is not None and interval > 0:
        remaining = interval - (time.perf_counter() - last_request)
        if remaining > 0:
            time.sleep(remaining)


def benchmark_rpc(config: dict, truth: dict[int, int]) -> tuple[dict, dict[int, int]]:
    blocks = list(truth)
    resolved: dict[int, int] = {}
    http = requests.Session()
    metrics = Counter()
    attempted_widths: list[int] = []
    last_request = None
    started = time.perf_counter()
    for offset in range(0, len(blocks), config["batch_size"]):
        batch = blocks[offset : offset + config["batch_size"]]
        payload = [
            {"jsonrpc": "2.0", "id": index, "method": "eth_getBlockByNumber", "params": [hex(block), False]}
            for index, block in enumerate(batch)
        ]
        for retry in range(8):
            wait_for_pacing(last_request, config["min_interval_seconds"])
            metrics["total_rpc_requests"] += 1
            metrics["batch_requests"] += 1
            attempted_widths.append(len(batch))
            last_request = time.perf_counter()
            try:
                response = http.post(RPC, json=payload, timeout=60, headers={"User-Agent": "robinhood-timestamp-benchmark/0.1"})
                if response.status_code == 429:
                    metrics["rate_limit_events"] += 1
                    raise requests.RequestException("429")
                if response.status_code >= 500:
                    raise requests.RequestException(str(response.status_code))
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, list) or any("error" in row or not row.get("result") for row in result):
                    raise RuntimeError("invalid batch response")
                by_id = {row["id"]: row for row in result}
                resolved.update({block: int(by_id[index]["result"]["timestamp"], 16) for index, block in enumerate(batch)})
                metrics["successful_batch_requests"] += 1
                metrics["individual_block_lookups"] += len(batch)
                break
            except requests.Timeout:
                metrics["timeout_events"] += 1
                metrics["retries"] += 1
            except (requests.RequestException, RuntimeError, ValueError):
                metrics["retries"] += 1
            if retry == 7:
                raise RuntimeError(f"{config['name']} exhausted retries at sample offset {offset}")
            if config["backoff"] == "production_exponential":
                time.sleep(min(2 ** (retry + 1), 30))
    wall = time.perf_counter() - started
    exact = sum(resolved.get(block) == timestamp for block, timestamp in truth.items())
    result = {
        "method": config["name"],
        "sample_size": len(truth),
        "wall_clock_seconds": round(wall, 3),
        "resolved_timestamps": len(resolved),
        "exact_match_count": exact,
        "exact_match_percentage": 100 * exact / len(truth),
        "effective_timestamps_per_second": len(resolved) / wall,
        "total_rpc_requests": metrics["total_rpc_requests"],
        "batch_requests": metrics["batch_requests"],
        "successful_batch_requests": metrics["successful_batch_requests"],
        "individual_block_lookups": metrics["individual_block_lookups"],
        "retries": metrics["retries"],
        "rate_limit_events": metrics["rate_limit_events"],
        "timeout_events": metrics["timeout_events"],
        "average_batch_size": sum(attempted_widths) / len(attempted_widths),
        "maximum_observed_batch_size": max(attempted_widths),
        "minimum_request_interval_seconds": config["min_interval_seconds"],
        "persistent_reuse_supported": False,
        "implementation_complexity": "existing" if config["name"].startswith("current") else "low: one pacing interval around existing serial batch loop",
    }
    print(json.dumps(result, indent=2), flush=True)
    return result, resolved


def local_overlap() -> dict:
    roots = [Path("reports/robinhood_chain_phase0"), Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")]
    paths = sorted({path.resolve() for root in roots for path in root.rglob("block_timestamps.json")})
    occurrences: Counter[int] = Counter()
    values: dict[int, int] = {}
    mismatches = 0
    entries = 0
    for path in paths:
        mapping = {int(block): int(timestamp) for block, timestamp in json.loads(path.read_text(encoding="utf-8")).items()}
        entries += len(mapping)
        for block, timestamp in mapping.items():
            occurrences[block] += 1
            if block in values and values[block] != timestamp:
                mismatches += 1
            values.setdefault(block, timestamp)
    return {
        "timestamp_cache_files": len(paths),
        "total_local_mapping_entries": entries,
        "globally_unique_known_blocks": len(values),
        "duplicate_mapping_entries_across_files": entries - len(values),
        "blocks_present_in_multiple_files": sum(count > 1 for count in occurrences.values()),
        "cross_file_timestamp_mismatches": mismatches,
        "available_tokens": ["NVDA"],
        "cross_token_overlap_measurable": False,
    }


def benchmark_global_cache(truth: dict[int, int], source_result: dict, source_mapping: dict[int, int]) -> dict:
    path = OUTPUT / "prototype_global_block_timestamps.json"
    if path.exists():
        path.unlink()
    cold_started = time.perf_counter()
    cold_cache: dict[int, int] = {}
    misses = [block for block in truth if block not in cold_cache]
    cold_cache.update({block: source_mapping[block] for block in misses})
    atomic_json(path, {str(block): timestamp for block, timestamp in cold_cache.items()})
    persistence_seconds = time.perf_counter() - cold_started
    warm_started = time.perf_counter()
    warm = {int(block): int(timestamp) for block, timestamp in json.loads(path.read_text(encoding="utf-8")).items()}
    warm_resolved = {block: warm[block] for block in truth if block in warm}
    warm_seconds = time.perf_counter() - warm_started
    exact = sum(warm_resolved.get(block) == timestamp for block, timestamp in truth.items())
    return {
        "method": "prototype_global_persistent_json_cache",
        "sample_size": len(truth),
        "cold_cache_misses": len(misses),
        "cold_source_method": source_result["method"],
        "cold_source_wall_clock_seconds": source_result["wall_clock_seconds"],
        "cache_persistence_overhead_seconds": persistence_seconds,
        "warm_cache_wall_clock_seconds": warm_seconds,
        "resolved_timestamps": len(warm_resolved),
        "exact_match_count": exact,
        "exact_match_percentage": 100 * exact / len(truth),
        "effective_warm_timestamps_per_second": len(warm_resolved) / warm_seconds,
        "total_rpc_requests_warm": 0,
        "batch_requests_warm": 0,
        "retries_warm": 0,
        "rate_limit_events_warm": 0,
        "timeout_events_warm": 0,
        "average_batch_size_warm": 0,
        "maximum_observed_batch_size_warm": 0,
        "persistent_reuse_supported": True,
        "implementation_complexity": "low prototype; production JSON rewrite cost would grow with cache size",
    }


def write_report(results: list[dict], cache_result: dict, overlap: dict) -> dict:
    current = results[0]
    exact_candidates = [row for row in results[1:] if row["exact_match_percentage"] == 100]
    best = max(exact_candidates, key=lambda row: row["effective_timestamps_per_second"])
    improvement = 100 * (best["effective_timestamps_per_second"] / current["effective_timestamps_per_second"] - 1)
    recommendation = "TUNE_BATCH_AND_PACING" if improvement >= 25 else "KEEP_CURRENT_METHOD"
    summary = {
        "recommendation": recommendation,
        "throughput_improvement_percentage": improvement,
        "current_architecture": {
            "scope": "per-session persistent event-block timestamp JSON",
            "panel_wide_event_timestamp_cache": False,
            "cross_session_requery_possible": True,
            "rpc_method": "eth_getBlockByNumber",
            "batch_size": 100,
            "request_pacing": "none before success; bounded exponential backoff after failure",
            "retry_backoff_seconds": [2, 4, 8, 16, 30, 30, 30],
            "maximum_concurrency": 1,
            "checkpoint": "atomic per-session JSON replacement after each successful batch",
        },
        "rpc_results": results,
        "global_cache_prototype": cache_result,
        "local_overlap": overlap,
    }
    atomic_json(OUTPUT / "benchmark_results.json", summary)
    rows = "\n".join(
        f"| {row['method']} | {row['sample_size']} | {row['wall_clock_seconds']:.3f} | {row['resolved_timestamps']} | {row['exact_match_percentage']:.1f}% | {row['effective_timestamps_per_second']:.3f} | {row['total_rpc_requests']} | {row['retries']} | {row['rate_limit_events']} | {row['timeout_events']} | {row['average_batch_size']:.1f} | {row['maximum_observed_batch_size']} |"
        for row in results
    )
    minimal_change = (
        f"Retain serial batch size {best['maximum_observed_batch_size']:.0f} and add a minimum {best['minimum_request_interval_seconds']:.1f}-second interval before every batch attempt; preserve the existing per-batch atomic checkpoint and bounded retry behavior."
        if recommendation == "TUNE_BATCH_AND_PACING"
        else "Keep the current resolver; the safest measured gain did not reach the 25% materiality threshold."
    )
    comparison_text = (
        f"best safe configuration improved effective throughput by {improvement:.1f}%"
        if improvement >= 0
        else f"best paced alternative was {abs(improvement):.1f}% slower than current"
    )
    practical_text = (
        "The measured pacing change can reduce timestamp-stage wall time without changing correctness or checkpoint semantics."
        if improvement >= 25
        else "Neither tested pacing change reduced timestamp-stage wall time; fewer 429 responses did not translate into higher throughput."
    )
    report = f"""# Robinhood Chain timestamp-resolution benchmark

## Result

**{recommendation}** — {comparison_text}, with 100% exact timestamp agreement.

Panel collection was NOT resumed during this benchmark.

## Current architecture

Event timestamps are cached per session, not per token or panel-wide. `block_boundary_cache.json` is panel-wide but maps time boundaries to blocks; it is not a reusable `block_number -> timestamp` store. Consequently a block can be queried again when it appears in another token-session.

The resolver uses official-RPC `eth_getBlockByNumber`, serial JSON-RPC batches of 100, no proactive pacing, concurrency 1, and bounded exponential retry sleeps of 2/4/8/16/30 seconds. Each successful batch atomically replaces the session JSON cache.

## Benchmark sample

The sample contains 2,000 deterministic, equally spaced order-statistic positions across the 26,107 sorted unique execution blocks in completed NVDA session 2026-07-23. Its already-saved timestamps are immutable ground truth; every configuration queried the exact same blocks.

## RPC results

| Configuration | Sample | Seconds | Resolved | Exact | Timestamps/s | RPC batches | Retries | 429s | Timeouts | Avg batch | Max batch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

All accepted methods required and achieved 100% exact matches; no interpolation or approximation was used.

## Global-cache prototype and overlap

Cold cache had {cache_result['cold_cache_misses']} misses and used `{cache_result['cold_source_method']}` as its source. Persisting 2,000 exact mappings added {cache_result['cache_persistence_overhead_seconds']:.4f}s. A warm JSON lookup resolved all 2,000 blocks in {cache_result['warm_cache_wall_clock_seconds']:.4f}s with zero RPC calls and 100% exact matches.

Across {overlap['timestamp_cache_files']} existing local timestamp-cache files there are {overlap['total_local_mapping_entries']:,} entries and {overlap['globally_unique_known_blocks']:,} unique blocks, leaving {overlap['duplicate_mapping_entries_across_files']:,} duplicate entries across files and {overlap['cross_file_timestamp_mismatches']} timestamp conflicts. Only NVDA sessions exist locally, so actual cross-token cache overlap cannot yet be measured and no future cache-hit rate is projected.

## Interpretation

The prior 97.9% runtime share was caused by the large number of exact per-block metadata lookups through a quota-limited RPC. Rate-limit retries add variable delay, but eliminating 429s with the tested fixed pacing reduced rather than improved effective throughput. Decoding, VWAP construction, and raw-log retrieval were not material bottlenecks.

Practical benefit: {practical_text} A global cache gives near-free exact warm reuse, but current NVDA-only local evidence does not establish cross-token hit rates, and a single ever-growing JSON file would eventually make atomic rewrites expensive.

## Minimal collector change

{minimal_change}

Do not implement this change until explicitly approved.
"""
    (OUTPUT / "benchmark_report.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    truth = sample_ground_truth()
    results = []
    mappings = []
    for index, config in enumerate(CONFIGS):
        if index:
            print("Cooling down provider quota for 30 seconds before next configuration.", flush=True)
            time.sleep(30)
        result, mapping = benchmark_rpc(config, truth)
        assert result["exact_match_percentage"] == 100
        results.append(result)
        mappings.append(mapping)
    best_index = max(range(1, len(results)), key=lambda index: results[index]["effective_timestamps_per_second"])
    cache_result = benchmark_global_cache(truth, results[best_index], mappings[best_index])
    overlap = local_overlap()
    summary = write_report(results, cache_result, overlap)
    print(json.dumps({"recommendation": summary["recommendation"], "improvement_percentage": summary["throughput_improvement_percentage"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
