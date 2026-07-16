from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STOCK_POOL = DATA / "stockPool"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
CACHE = DATA / "cache"
PRICE_CACHE = CACHE / "price"

EXPANDED_POOL = STOCK_POOL / "expanded_pool_v1_2.csv"
DEFAULT_POOL = STOCK_POOL / "default_pool_v1_2.csv"
SUGGESTIONS = STOCK_POOL / "pool_decision_suggestions_v1_2.csv"
EXCLUDED_RULES = STOCK_POOL / "excluded_by_rules_v1_2.csv"

OUT_INVENTORY_CSV = REPORTS / "project_inventory_for_backtest.csv"
OUT_INVENTORY_MD = REPORTS / "project_inventory_for_backtest.md"
OUT_READINESS = REPORTS / "backtest_data_readiness_report.md"
OUT_REORG = REPORTS / "project_reorganization_proposal.md"
OUT_UNIVERSE_EXPANDED = PROCESSED / "backtest_universe_expanded_only_v1_2.csv"
OUT_UNIVERSE_RESEARCH = PROCESSED / "backtest_universe_research_v1_2.csv"
OUT_PRICE_PANEL_CSV = PROCESSED / "backtest_price_panel_v1_2.csv"
OUT_PRICE_PANEL_PARQUET = PROCESSED / "backtest_price_panel_v1_2.parquet"

SCAN_DIRS = [
    ROOT,
    DATA,
    STOCK_POOL,
    CACHE,
    PROCESSED,
    ROOT / "scripts",
    ROOT / "src",
    ROOT / "tests",
    REPORTS,
]

UNIVERSE_FIELDS = [
    "code",
    "name",
    "theme",
    "universe_name",
    "trading_pool_decision",
    "business_evidence_decision",
    "evidence_strength",
    "leverage_risk_flag",
    "financial_risk_level",
    "rule_exception_resolution",
    "default_pool_allowed",
    "v1_2_decision_reason",
    "evidence_url",
]

PRICE_PANEL_FIELDS = [
    "stock_code",
    "trade_date",
    "close",
    "high",
    "low",
    "amount",
    "turnover",
    "total_market_cap",
    "circulating_market_cap",
    "open",
    "volume",
    "pre_close",
    "adjusted_close",
    "adj_factor",
    "return_quality",
    "source_file",
]


@dataclass(frozen=True)
class PriceCoverage:
    universe_name: str
    row_count: int
    unique_codes: int
    missing_price_files: list[str]
    missing_required_fields: dict[str, list[str]]
    missing_execution_fields: dict[str, list[str]]
    missing_adjusted_fields: list[str]
    duplicate_code_dates: int
    non_weekday_rows: int
    abnormal_price_rows: int
    min_start_date: str
    max_start_date: str
    min_end_date: str
    max_end_date: str
    short_or_stale_codes: list[dict[str, str]]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def code6(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6)[-6:]


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def classify_path(path: Path) -> tuple[str, str, str]:
    relative = rel(path)
    name = path.name
    lower = relative.lower()
    version_tag = ""
    active_status = "unknown"

    if name in {
        "default_pool_v1_2.csv",
        "expanded_pool_v1_2.csv",
        "excluded_by_rules_v1_2.csv",
        "excluded_by_business_mismatch_v1_2.csv",
        "pool_decision_suggestions_v1_2.csv",
        "rule_exception_resolution_v1_2.csv",
        "stock_pool_rules_v1_2.csv",
        "stock_pool_v1_2_QA_report.md",
    }:
        return "active stock pool v1.2 outputs", "v1.2", "active"
    if "v1_1" in lower or name in {"affected_rows.csv", "implicit_rule_exceptions.csv", "manual_followup_true_required.csv"}:
        return "v1/v1.1 old stock pool outputs", "v1.1", "historical"
    if lower.endswith("_v1.csv") or "_v1." in lower or "full_119" in lower:
        return "v1/v1.1 old stock pool outputs", "v1", "historical"
    if "annual_report" in lower or name in {
        "core_stock_evidence_review.csv",
        "manual_stock_evidence_review.csv",
        "evidence_QA_report.md",
    }:
        return "annual report evidence files", version_tag, "evidence"
    if "scorecard" in lower or name == "theme_stock_research_scorecard.csv":
        return "scorecard files", version_tag, "input"
    if "data/cache/price" in lower or "price_cache" in lower:
        return "price/volume cache files", version_tag, "cache"
    if "moneyflow" in lower or "volume" in lower:
        return "price/volume cache files", version_tag, "cache"
    if "concept" in lower or "theme_stock" in lower or "thematic" in lower:
        return "concept collection files", version_tag, "research"
    if "backtest" in lower or name in {"run_research.py", "cli.py", "backtest_engine.py"}:
        return "backtest-related scripts", version_tag, "active_or_prior"
    if "__pycache__" in lower or lower.endswith(".pyc"):
        return "stale or unknown files", version_tag, "generated_cache"
    return "stale or unknown files", version_tag, active_status


def scan_inventory() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[Path] = set()
    for directory in SCAN_DIRS:
        if not directory.exists():
            rows.append(
                {
                    "path": rel(directory),
                    "directory": rel(directory.parent),
                    "file_name": directory.name,
                    "extension": "",
                    "size_bytes": "",
                    "last_modified": "",
                    "category": "stale or unknown files",
                    "version_tag": "",
                    "active_status": "missing_directory",
                    "notes": "Directory was requested for inventory but does not exist.",
                }
            )
            continue
        for path in directory.rglob("*") if directory not in {ROOT, DATA, CACHE} else directory.glob("*"):
            if path in seen:
                continue
            seen.add(path)
            if path.is_dir():
                if path in {PRICE_CACHE, CACHE / "cashflow", CACHE / "profit", CACHE / "moneyflow", STOCK_POOL / "annual_report_cache"}:
                    files = [item for item in path.rglob("*") if item.is_file()]
                    size = sum(item.stat().st_size for item in files)
                    newest = max((item.stat().st_mtime for item in files), default=0)
                    category = "price/volume cache files" if path == PRICE_CACHE else "stale or unknown files"
                    if path == STOCK_POOL / "annual_report_cache":
                        category = "annual report evidence files"
                    rows.append(
                        {
                            "path": rel(path),
                            "directory": rel(path.parent),
                            "file_name": path.name,
                            "extension": "<directory>",
                            "size_bytes": size,
                            "last_modified": datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else "",
                            "category": category,
                            "version_tag": "",
                            "active_status": "aggregate",
                            "notes": f"Aggregated directory; files={len(files)}.",
                        }
                    )
                continue
            category, version_tag, active_status = classify_path(path)
            stat = path.stat()
            rows.append(
                {
                    "path": rel(path),
                    "directory": rel(path.parent),
                    "file_name": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "category": category,
                    "version_tag": version_tag,
                    "active_status": active_status,
                    "notes": "",
                }
            )
    return sorted(rows, key=lambda item: str(item["path"]))


def build_universe(rows: Iterable[dict[str, str]], universe_name: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        item = {field: row.get(field, "") for field in UNIVERSE_FIELDS}
        item["code"] = code6(row.get("code", ""))
        item["universe_name"] = universe_name
        output.append(item)
    return output


def load_universes() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    expanded = build_universe(read_csv(EXPANDED_POOL), "expanded_only_v1_2")
    default = build_universe(read_csv(DEFAULT_POOL), "research_universe_v1_2")
    research_expanded = build_universe(read_csv(EXPANDED_POOL), "research_universe_v1_2")
    return expanded, [*default, *research_expanded]


def price_path(code: str) -> Path:
    return PRICE_CACHE / f"{code6(code)}.csv"


def parse_float(value: str) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except ValueError:
        return None


def analyze_price_coverage(universe: list[dict[str, str]], universe_name: str) -> PriceCoverage:
    codes = sorted({code6(row["code"]) for row in universe})
    missing_files: list[str] = []
    missing_required: dict[str, list[str]] = defaultdict(list)
    missing_execution: dict[str, list[str]] = defaultdict(list)
    duplicate_code_dates = 0
    non_weekday_rows = 0
    abnormal_price_rows = 0
    starts: list[str] = []
    ends: list[str] = []
    short_or_stale: list[dict[str, str]] = []

    for code in codes:
        path = price_path(code)
        if not path.exists():
            missing_files.append(code)
            continue
        rows = read_csv(path)
        if not rows:
            missing_files.append(code)
            continue
        columns = set(rows[0])
        for field in ["date", "close", "high", "low", "amount"]:
            if field not in columns:
                missing_required[field].append(code)
        for field in ["open", "volume", "pre_close"]:
            if field not in columns:
                missing_execution[field].append(code)
        if not ({"adjusted_close", "adj_factor"} & columns):
            missing_execution["adjusted_close_or_adj_factor"].append(code)
        seen_dates: set[str] = set()
        dates: list[str] = []
        for row in rows:
            date = row.get("date", "")
            if not date:
                continue
            key = f"{code}|{date}"
            if key in seen_dates:
                duplicate_code_dates += 1
            seen_dates.add(key)
            dates.append(date)
            try:
                weekday = datetime.strptime(date, "%Y-%m-%d").weekday()
                if weekday >= 5:
                    non_weekday_rows += 1
            except ValueError:
                non_weekday_rows += 1
            for field in ["close", "high", "low"]:
                if field in row:
                    value = parse_float(row.get(field, ""))
                    if value is not None and value <= 0:
                        abnormal_price_rows += 1
        if dates:
            start, end = min(dates), max(dates)
            starts.append(start)
            ends.append(end)
            if end < "2026-06-16" or code in set(missing_required.get("high", [])) | set(missing_required.get("low", [])):
                short_or_stale.append(
                    {
                        "code": code,
                        "rows": str(len(rows)),
                        "start_date": start,
                        "end_date": end,
                        "missing_required": ";".join(
                            field for field, values in missing_required.items() if code in values
                        )
                        or "none",
                    }
                )

    missing_adjusted = sorted(set(missing_execution.get("adjusted_close_or_adj_factor", [])))
    return PriceCoverage(
        universe_name=universe_name,
        row_count=len(universe),
        unique_codes=len(codes),
        missing_price_files=missing_files,
        missing_required_fields={key: sorted(values) for key, values in missing_required.items()},
        missing_execution_fields={key: sorted(values) for key, values in missing_execution.items()},
        missing_adjusted_fields=missing_adjusted,
        duplicate_code_dates=duplicate_code_dates,
        non_weekday_rows=non_weekday_rows,
        abnormal_price_rows=abnormal_price_rows,
        min_start_date=min(starts) if starts else "",
        max_start_date=max(starts) if starts else "",
        min_end_date=min(ends) if ends else "",
        max_end_date=max(ends) if ends else "",
        short_or_stale_codes=short_or_stale,
    )


def build_price_panel(universe: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    panel: list[dict[str, str]] = []
    for code in sorted({code6(row["code"]) for row in universe}):
        path = price_path(code)
        if not path.exists():
            continue
        for row in read_csv(path):
            panel.append(
                {
                    "stock_code": code,
                    "trade_date": row.get("date", ""),
                    "close": row.get("close", ""),
                    "high": row.get("high", ""),
                    "low": row.get("low", ""),
                    "amount": row.get("amount", ""),
                    "turnover": row.get("turnover", ""),
                    "total_market_cap": row.get("total_market_cap", ""),
                    "circulating_market_cap": row.get("circulating_market_cap", ""),
                    "open": row.get("open", ""),
                    "volume": row.get("volume", ""),
                    "pre_close": row.get("pre_close", ""),
                    "adjusted_close": row.get("adjusted_close", ""),
                    "adj_factor": row.get("adj_factor", ""),
                    "return_quality": "smoke_unadjusted_or_unverified",
                    "source_file": rel(path),
                }
            )
    if write_parquet_if_available(panel):
        return panel, rel(OUT_PRICE_PANEL_PARQUET)
    write_csv(OUT_PRICE_PANEL_CSV, panel, PRICE_PANEL_FIELDS)
    return panel, rel(OUT_PRICE_PANEL_CSV)


def write_parquet_if_available(panel: list[dict[str, str]]) -> bool:
    try:
        import pandas as pd  # type: ignore

        frame = pd.DataFrame(panel, columns=PRICE_PANEL_FIELDS)
        frame.to_parquet(OUT_PRICE_PANEL_PARQUET, index=False)
        return True
    except Exception:
        return False


def benchmark_candidates() -> list[dict[str, str]]:
    candidate_codes = ["000300", "399006", "000852", "000905", "000985"]
    rows: list[dict[str, str]] = []
    for code in candidate_codes:
        candidates = list(CACHE.rglob(f"*{code}*")) if CACHE.exists() else []
        rows.append(
            {
                "code": code,
                "candidate_files": "; ".join(rel(path) for path in candidates[:5]) if candidates else "",
                "status": "candidate_unverified" if candidates else "missing",
            }
        )
    return rows


def write_inventory_outputs(rows: list[dict[str, object]]) -> None:
    fields = [
        "path",
        "directory",
        "file_name",
        "extension",
        "size_bytes",
        "last_modified",
        "category",
        "version_tag",
        "active_status",
        "notes",
    ]
    write_csv(OUT_INVENTORY_CSV, rows, fields)
    counts = Counter(str(row["category"]) for row in rows)
    active = [row for row in rows if row["category"] == "active stock pool v1.2 outputs"]
    lines = [
        "# Project Inventory For Backtest",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        "- mode: non-destructive inventory",
        "- no files were deleted, moved, or overwritten outside the new output files.",
        "",
        "## Category Counts",
    ]
    lines.extend(f"- {category}: {count}" for category, count in sorted(counts.items()))
    lines.extend(["", "## Active Stock Pool v1.2 Outputs"])
    lines.extend(f"- {row['path']}" for row in active)
    lines.extend(
        [
            "",
            "## Notes",
            "- data/cache/price is represented as an aggregate directory row to avoid a noisy 5,000+ row listing.",
            "- v1 and v1.1 stock-pool outputs are classified as historical, not stale or disposable.",
            "- Unknown files require human review before any cleanup proposal is acted on.",
        ]
    )
    OUT_INVENTORY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def coverage_lines(coverage: PriceCoverage) -> list[str]:
    return [
        f"### {coverage.universe_name}",
        f"- rows: {coverage.row_count}",
        f"- unique_codes: {coverage.unique_codes}",
        f"- missing_price_files: {len(coverage.missing_price_files)} {coverage.missing_price_files[:20]}",
        f"- date_range_by_code: start {coverage.min_start_date}..{coverage.max_start_date}; end {coverage.min_end_date}..{coverage.max_end_date}",
        f"- duplicate_code_date_rows: {coverage.duplicate_code_dates}",
        f"- non_weekday_rows: {coverage.non_weekday_rows}",
        f"- abnormal_price_rows: {coverage.abnormal_price_rows}",
        f"- missing_required_fields: { {key: len(value) for key, value in coverage.missing_required_fields.items()} }",
        f"- missing_execution_fields: { {key: len(value) for key, value in coverage.missing_execution_fields.items()} }",
        f"- missing_adjusted_close_or_adj_factor_codes: {len(coverage.missing_adjusted_fields)}",
    ]


def write_readiness_report(
    expanded_cov: PriceCoverage,
    research_cov: PriceCoverage,
    price_panel_path: str,
    price_panel_rows: int,
) -> None:
    benchmark = benchmark_candidates()
    lines = [
        "# Backtest Data Readiness Report",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        "- baseline_type: current_universe_historical_performance",
        "- point_in_time_strategy_backtest: no",
        "- performance_conclusion_allowed: no",
        "- baseline_status: smoke_only",
        "- reason: qfq adjusted close / adjusted_close is missing or unverified in the reusable cache.",
        "",
        "## Generated Data Prep Outputs",
        f"- {rel(OUT_UNIVERSE_EXPANDED)}",
        f"- {rel(OUT_UNIVERSE_RESEARCH)}",
        f"- {price_panel_path}",
        "",
        "## Universe Coverage",
        *coverage_lines(expanded_cov),
        "",
        *coverage_lines(research_cov),
        "",
        "## Explicit Data Gaps",
        "- qfq adjusted close / adjusted_close / adj_factor: missing or unverified for reusable price cache.",
        "- open: missing from data/cache/price cache.",
        "- volume: missing from data/cache/price cache.",
        "- pre_close: missing from data/cache/price cache.",
        "- historical ST flags: not available in current price panel.",
        "- suspension/trading status: not available as explicit historical field.",
        "- limit-up/limit-down fields: not available; high/low/close/pre_close are insufficient because pre_close is missing.",
        "- benchmark: no verified full-window benchmark panel is available.",
        "- 300378: missing high/low and stale at 2026-06-12 in reusable price cache.",
        "",
        "## Benchmark Candidates",
    ]
    for row in benchmark:
        lines.append(f"- {row['code']}: {row['status']}; files={row['candidate_files'] or 'none'}")
    lines.extend(
        [
            "",
            "## Data Reuse Decision",
            "- Reuse data/stockPool/*_v1_2.csv as stock-pool source of truth.",
            "- Reuse data/cache/price/*.csv for smoke price coverage and unadjusted/unverified price panel only.",
            "- Reuse data/processed/pipeline_manifest.json and reports/market_data_realism_audit.md as prior QA evidence.",
            "- Do not use current cache for formal performance conclusions until adjusted prices and tradability fields are added.",
            "",
            "## Minimal Fetch Plan For A Later Turn",
            "- Fetch only active research universe codes, not all A-shares.",
            "- Fetch qfq OHLC or at least qfq adjusted close, volume, and pre_close for 56 unique active codes.",
            "- Patch 300378 high/low/date coverage first.",
            "- Fetch benchmark series for HS300 and at least one growth/small-cap comparator.",
            "- Use sleep/retry and write failures to CSV; do not silently skip failed symbols.",
            "",
            "## Smoke Baseline Rules",
            "- First smoke baseline may use expanded_only_v1_2 equal weight with 20 trading day rebalance.",
            "- The report title and metadata must state current_universe_historical_performance and not_point_in_time_backtest.",
            "- No official performance conclusion is allowed before adjusted returns and tradability fields are available.",
            f"- price_panel_rows: {price_panel_rows}",
        ]
    )
    OUT_READINESS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reorg_proposal() -> None:
    lines = [
        "# Project Reorganization Proposal",
        "",
        "- status: proposal_only",
        "- no files were moved, deleted, or renamed.",
        "",
        "## Proposed Shape",
        "- Keep `data/stockPool/` as the auditable stock-pool research ledger.",
        "- Keep active deliverables named with explicit versions, for example `*_v1_2.csv`.",
        "- Add a future `data/stockPool/archive/` only after manual approval; move v1/v1.1 there in one audited migration.",
        "- Keep raw/cache data under `data/cache/`, processed panels under `data/processed/`, and narrative QA under `reports/`.",
        "- Keep executable research scripts in `scripts/`; move reusable library logic into `src/aq_factor_lab/` only when it has tests.",
        "",
        "## Risks",
        "- Moving historical stock-pool files before backtest readiness is complete would break audit traceability.",
        "- Old files may encode manual decisions or QA context even when superseded by v1.2.",
        "- Cache directories are large; inventory should use aggregate rows unless a targeted audit needs file-level detail.",
        "",
        "## Suggested Future Cleanup Gate",
        "- Produce a manifest mapping every archived file to its successor or reason for retention.",
        "- Run tests and checksum active v1.2 files before and after any move.",
        "- Keep a rollback note in the cleanup PR/report.",
    ]
    OUT_REORG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(
    inventory: list[dict[str, object]],
    expanded: list[dict[str, str]],
    research: list[dict[str, str]],
    expanded_cov: PriceCoverage,
    research_cov: PriceCoverage,
) -> list[str]:
    errors: list[str] = []
    active_paths = {str(row["path"]) for row in inventory if row["category"] == "active stock pool v1.2 outputs"}
    for required in [
        "data/stockPool/default_pool_v1_2.csv",
        "data/stockPool/expanded_pool_v1_2.csv",
        "data/stockPool/excluded_by_rules_v1_2.csv",
        "data/stockPool/pool_decision_suggestions_v1_2.csv",
    ]:
        if required not in active_paths:
            errors.append(f"inventory missing active v1.2 classification for {required}")
    if len(expanded) != len(read_csv(EXPANDED_POOL)):
        errors.append("expanded_only_v1_2 row count mismatch")
    if len(research) != len(read_csv(EXPANDED_POOL)) + len(read_csv(DEFAULT_POOL)):
        errors.append("research_universe_v1_2 row count mismatch")
    for name, rows in [("expanded", expanded), ("research", research)]:
        bad_codes = [row["code"] for row in rows if len(row["code"]) != 6 or not row["code"].isdigit()]
        if bad_codes:
            errors.append(f"{name} bad six-digit codes: {bad_codes[:10]}")
    if "300378" not in expanded_cov.missing_required_fields.get("high", []):
        errors.append("300378 high-field gap was not detected")
    if not research_cov.missing_adjusted_fields:
        errors.append("missing adjusted close caveat was not detected")
    return errors


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    inventory = scan_inventory()
    write_inventory_outputs(inventory)

    expanded, research = load_universes()
    write_csv(OUT_UNIVERSE_EXPANDED, expanded, UNIVERSE_FIELDS)
    write_csv(OUT_UNIVERSE_RESEARCH, research, UNIVERSE_FIELDS)

    expanded_cov = analyze_price_coverage(expanded, "expanded_only_v1_2")
    research_cov = analyze_price_coverage(research, "research_universe_v1_2")
    panel, panel_path = build_price_panel(research)

    write_readiness_report(expanded_cov, research_cov, panel_path, len(panel))
    write_reorg_proposal()

    errors = validate_outputs(inventory, expanded, research, expanded_cov, research_cov)
    print(f"inventory_rows={len(inventory)}")
    print(f"expanded_rows={len(expanded)}")
    print(f"research_rows={len(research)}")
    print(f"price_panel_rows={len(panel)}")
    print(f"price_panel_path={panel_path}")
    print(f"validation_errors={len(errors)}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
