from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ADJUSTED_PATH = ROOT / "data" / "processed" / "adjusted_price_panel_v1_2.csv"
MANIFEST_PATH = ROOT / "data" / "processed" / "qfq_fetch_manifest_v1_2.csv"
RAW_BASE_PATH = ROOT / "data" / "processed" / "raw_base_price_panel_v1_2.csv"
UNIVERSE_PATH = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"

REPORT_OUT = ROOT / "reports" / "adjusted_price_panel_QA_v1_2.md"
ISSUES_OUT = ROOT / "reports" / "adjusted_price_panel_issues_v1_2.csv"
SUMMARY_OUT = ROOT / "reports" / "adjusted_price_panel_summary_v1_2.csv"

ISSUE_COLUMNS = [
    "severity",
    "issue_type",
    "stock_code",
    "trade_date",
    "field",
    "observed_value",
    "expected_rule",
    "row_count",
    "impact",
    "recommendation",
]

SUMMARY_COLUMNS = ["metric", "value", "pass_fail", "threshold", "notes"]
QFQ_COLS = ["qfq_open", "qfq_high", "qfq_low", "qfq_close"]


@dataclass
class QAResult:
    issues: pd.DataFrame
    summary: pd.DataFrame
    source_distribution: pd.DataFrame
    decisions: dict[str, bool]
    manifest_latest: pd.DataFrame


def code6(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else text


def parse_adjusted_flag(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def make_issue(
    severity: str,
    issue_type: str,
    stock_code: object = "",
    trade_date: object = "",
    field: str = "",
    observed_value: object = "",
    expected_rule: str = "",
    row_count: int = 1,
    impact: str = "",
    recommendation: str = "",
) -> dict[str, object]:
    return {
        "severity": severity,
        "issue_type": issue_type,
        "stock_code": stock_code,
        "trade_date": trade_date,
        "field": field,
        "observed_value": observed_value,
        "expected_rule": expected_rule,
        "row_count": int(row_count),
        "impact": impact,
        "recommendation": recommendation,
    }


def make_summary(metric: str, value: object, pass_fail: str = "", threshold: str = "", notes: str = "") -> dict[str, object]:
    return {
        "metric": metric,
        "value": value,
        "pass_fail": pass_fail,
        "threshold": threshold,
        "notes": notes,
    }


def latest_manifest_status(manifest: pd.DataFrame) -> pd.DataFrame:
    if manifest.empty:
        return pd.DataFrame()

    df = manifest.copy()
    code_col = "stock_code" if "stock_code" in df.columns else "symbol"
    if code_col not in df.columns:
        return pd.DataFrame()

    if "final_status" not in df.columns and "status" in df.columns:
        df["final_status"] = df["status"]
    if "final_status" not in df.columns:
        df["final_status"] = ""
    if "fetched_at" not in df.columns:
        df["fetched_at"] = ""
    if "run_id" not in df.columns:
        df["run_id"] = ""

    df["stock_code_norm"] = df[code_col].map(code6)
    df["_fetched_at_parsed"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    latest = (
        df.sort_values(["stock_code_norm", "_fetched_at_parsed", "run_id"], na_position="first")
        .groupby("stock_code_norm", as_index=False)
        .tail(1)
        .set_index("stock_code_norm")
    )
    return latest.drop(columns=["_fetched_at_parsed"], errors="ignore")


def source_distribution(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    if "stock_code_norm" not in df.columns:
        df["stock_code_norm"] = df["stock_code"].map(code6)
    source = df.get("source_qfq", pd.Series(index=df.index, dtype=object))
    df["source_qfq"] = source.fillna("").astype(str).str.strip().replace("", "missing")
    return (
        df.groupby("source_qfq", dropna=False)
        .agg(row_count=("source_qfq", "size"), stock_count=("stock_code_norm", "nunique"))
        .reset_index()
        .sort_values(["row_count", "source_qfq"], ascending=[False, True])
    )


def _normalize_universe_codes(universe_codes: Iterable[object]) -> set[str]:
    return {code6(code) for code in universe_codes if str(code).strip()}


def analyze(panel: pd.DataFrame, universe_codes: Iterable[object], manifest: pd.DataFrame) -> QAResult:
    df = panel.copy()
    issues: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []

    if "stock_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("panel must include stock_code and trade_date")

    df["stock_code_raw"] = df["stock_code"].astype(str).str.strip()
    df["stock_code_norm"] = df["stock_code_raw"].map(code6)
    df["trade_date_parsed"] = pd.to_datetime(df["trade_date"], errors="coerce")

    for col in ["close", "adjusted_close", *QFQ_COLS]:
        if col in df.columns:
            df[col] = to_num(df[col])
        else:
            df[col] = pd.NA

    df["is_adjusted"] = parse_adjusted_flag(df.get("adjusted_flag", pd.Series(False, index=df.index)))

    code_bad = ~df["stock_code_raw"].str.fullmatch(r"\d{6}", na=False)
    for raw_code, count in df.loc[code_bad].groupby("stock_code_raw", dropna=False).size().items():
        issues.append(
            make_issue(
                "High",
                "stock_code_not_6_digit",
                stock_code=code6(raw_code),
                field="stock_code",
                observed_value=raw_code,
                expected_rule="6-digit text preserving leading zeros",
                row_count=count,
                impact="Downstream joins/backtests can mismatch stock identity.",
                recommendation="Do not join/backtest until code6 normalize is applied downstream; do not edit source CSV in this QA step.",
            )
        )

    invalid_dates = df["trade_date_parsed"].isna()
    if invalid_dates.any():
        for value, count in df.loc[invalid_dates].groupby("trade_date", dropna=False).size().items():
            issues.append(
                make_issue(
                    "High",
                    "invalid_trade_date",
                    trade_date=value,
                    field="trade_date",
                    observed_value=value,
                    expected_rule="pd.to_datetime parseable trade date",
                    row_count=count,
                    impact="Date sorting and return calculations are unreliable.",
                    recommendation="Fix upstream date export before baseline calculations.",
                )
            )

    today = pd.Timestamp.today().normalize()
    future_dates = df["trade_date_parsed"].gt(today)
    if future_dates.any():
        issues.append(
            make_issue(
                "Medium",
                "future_trade_date",
                field="trade_date",
                observed_value=str(df.loc[future_dates, "trade_date_parsed"].max().date()),
                expected_rule=f"trade_date <= {today.date()}",
                row_count=int(future_dates.sum()),
                impact="Panel may include dates beyond the current run date.",
                recommendation="Verify source date range before using results.",
            )
        )

    key_valid = df["trade_date_parsed"].notna()
    dup_key = df.loc[key_valid].duplicated(["stock_code_norm", "trade_date_parsed"], keep=False)
    duplicate_key_rows = int(dup_key.sum())
    if duplicate_key_rows:
        dup_groups = (
            df.loc[key_valid & dup_key, ["stock_code_norm", "trade_date_parsed"]]
            .groupby(["stock_code_norm", "trade_date_parsed"])
            .size()
            .reset_index(name="row_count")
        )
        for _, row in dup_groups.iterrows():
            issues.append(
                make_issue(
                    "High",
                    "duplicate_stock_date",
                    stock_code=row["stock_code_norm"],
                    trade_date=row["trade_date_parsed"].date(),
                    field="stock_code_norm,trade_date",
                    observed_value=row["row_count"],
                    expected_rule="one row per stock_code/trade_date",
                    row_count=row["row_count"],
                    impact="Return and weight calculations would double-count rows.",
                    recommendation="Deduplicate upstream panel before any baseline run.",
                )
            )

    exact_dup_rows = int(df.duplicated(keep=False).sum())
    if exact_dup_rows:
        issues.append(
            make_issue(
                "Medium",
                "exact_duplicate_row",
                observed_value=exact_dup_rows,
                expected_rule="no exact duplicate rows",
                row_count=exact_dup_rows,
                impact="Panel contains repeated identical records.",
                recommendation="Inspect upstream merge/export step.",
            )
        )

    adjusted = df["is_adjusted"]
    bad_qfq_when_adjusted = adjusted & ~(df["qfq_close"] > 0)
    if bad_qfq_when_adjusted.any():
        for code, count in df.loc[bad_qfq_when_adjusted].groupby("stock_code_norm").size().items():
            issues.append(
                make_issue(
                    "High",
                    "invalid_qfq_close_when_adjusted",
                    stock_code=code,
                    field="qfq_close",
                    expected_rule="adjusted_flag=true requires qfq_close > 0",
                    row_count=count,
                    impact="Adjusted return source is invalid for these rows.",
                    recommendation="Refetch or exclude affected rows before adjusted baseline.",
                )
            )

    mismatch = adjusted & df["adjusted_close"].notna() & df["qfq_close"].notna() & ((df["adjusted_close"] - df["qfq_close"]).abs() > 1e-8)
    if mismatch.any():
        for code, count in df.loc[mismatch].groupby("stock_code_norm").size().items():
            issues.append(
                make_issue(
                    "High",
                    "adjusted_close_mismatch",
                    stock_code=code,
                    field="adjusted_close,qfq_close",
                    expected_rule="adjusted_close == qfq_close when adjusted_flag=true",
                    row_count=count,
                    impact="Return input is internally inconsistent.",
                    recommendation="Rebuild adjusted panel from qfq_close.",
                )
            )

    positive_adjusted_when_false = ~adjusted & (df["adjusted_close"] > 0)
    if positive_adjusted_when_false.any():
        for code, count in df.loc[positive_adjusted_when_false].groupby("stock_code_norm").size().items():
            issues.append(
                make_issue(
                    "High",
                    "adjusted_close_present_when_unadjusted",
                    stock_code=code,
                    field="adjusted_close",
                    expected_rule="adjusted_flag=false should not carry a positive adjusted_close",
                    row_count=count,
                    impact="Could indicate silent forward-fill or stale adjusted price.",
                    recommendation="Verify merge logic; do not forward-fill missing qfq.",
                )
            )

    for col in QFQ_COLS:
        bad = df[col].notna() & (df[col] <= 0)
        if bad.any():
            for code, count in df.loc[bad].groupby("stock_code_norm").size().items():
                issues.append(
                    make_issue(
                        "High",
                        "invalid_qfq_ohlc",
                        stock_code=code,
                        field=col,
                        expected_rule=f"{col} must be positive when present",
                        row_count=count,
                        impact="Adjusted OHLC field is not usable.",
                        recommendation="Refetch affected qfq cache or exclude rows.",
                    )
                )

    common = df[(df["trade_date_parsed"].notna()) & (df["qfq_close"] > 0) & (df["close"] > 0)].copy()
    if not common.empty:
        latest_idx = common.sort_values("trade_date_parsed").groupby("stock_code_norm").tail(1).index
        latest = common.loc[latest_idx]
        latest["qfq_raw_ratio"] = latest["qfq_close"] / latest["close"]
        warn = latest[~latest["qfq_raw_ratio"].between(0.95, 1.05)]
        for _, row in warn.iterrows():
            issues.append(
                make_issue(
                    "Medium",
                    "qfq_raw_alignment_warning",
                    stock_code=row["stock_code_norm"],
                    trade_date=row["trade_date_parsed"].date(),
                    field="qfq_close/close",
                    observed_value=round(float(row["qfq_raw_ratio"]), 6),
                    expected_rule="latest common-date qfq_close / raw close within 0.95..1.05",
                    row_count=1,
                    impact="May be a real adjustment gap or source mismatch; warning only.",
                    recommendation="Review corporate-action adjustment consistency before formal conclusions.",
                )
            )

    returns_df = df[(df["trade_date_parsed"].notna()) & (df["adjusted_close"] > 0)].sort_values(["stock_code_norm", "trade_date_parsed"]).copy()
    returns_df["adjusted_return"] = returns_df.groupby("stock_code_norm")["adjusted_close"].pct_change()
    outliers = returns_df[returns_df["adjusted_return"].abs() > 0.25]
    for _, row in outliers.iterrows():
        issues.append(
            make_issue(
                "Medium",
                "return_outlier",
                stock_code=row["stock_code_norm"],
                trade_date=row["trade_date_parsed"].date(),
                field="adjusted_close_return",
                observed_value=round(float(row["adjusted_return"]), 6),
                expected_rule="abs(simple adjusted return) <= 25% for routine review threshold",
                row_count=1,
                impact="Could be a legitimate limit regime/corporate action or bad adjustment.",
                recommendation="Manual review; do not treat as automatic failure.",
            )
        )

    universe = _normalize_universe_codes(universe_codes)
    adjusted_codes = set(df.loc[df["is_adjusted"], "stock_code_norm"].dropna())
    row_coverage_ratio = float(df["is_adjusted"].mean()) if len(df) else 0.0
    stock_coverage_ratio = (len(adjusted_codes & universe) / len(universe)) if universe else 0.0

    manifest_latest = latest_manifest_status(manifest)
    latest_status_counts = {}
    if not manifest_latest.empty and "final_status" in manifest_latest.columns:
        latest_status_counts = manifest_latest["final_status"].fillna("").value_counts().to_dict()
        for status in ("error", "partial_ok"):
            for code in manifest_latest.index[manifest_latest["final_status"].eq(status)].tolist():
                issues.append(
                    make_issue(
                        "Medium",
                        f"manifest_{status}_status",
                        stock_code=code,
                        field="final_status",
                        observed_value=status,
                        expected_rule="latest qfq manifest status should be ok or cached_ok",
                        row_count=1,
                        impact="Latest fetch status is a caveat even if panel coverage passes.",
                        recommendation="Review qfq_fetch_manifest_v1_2.csv for the latest source outcome.",
                    )
                )

    high_code_issue_count = sum(row["issue_type"] == "stock_code_not_6_digit" for row in issues)
    data_quality_pass = duplicate_key_rows == 0 and high_code_issue_count == 0
    coverage_pass = row_coverage_ratio >= 0.95 and stock_coverage_ratio >= 0.95
    adjusted_return_baseline_allowed = data_quality_pass and coverage_pass

    date_min = df["trade_date_parsed"].min()
    date_max = df["trade_date_parsed"].max()
    summaries.extend(
        [
            make_summary("total_rows", len(df), "info"),
            make_summary("stock_count", df["stock_code_norm"].nunique(), "info"),
            make_summary("universe_stock_count", len(universe), "info"),
            make_summary("date_min", "" if pd.isna(date_min) else date_min.date(), "info", "", "parsed with pd.to_datetime"),
            make_summary("date_max", "" if pd.isna(date_max) else date_max.date(), "info", "", "parsed with pd.to_datetime"),
            make_summary("invalid_date_count", int(invalid_dates.sum()), "pass" if not invalid_dates.any() else "fail", "0"),
            make_summary("future_date_count", int(future_dates.sum()), "pass" if not future_dates.any() else "warn", "0"),
            make_summary("duplicate_stock_date_rows", duplicate_key_rows, "pass" if duplicate_key_rows == 0 else "fail", "0"),
            make_summary("exact_duplicate_rows", exact_dup_rows, "pass" if exact_dup_rows == 0 else "warn", "0"),
            make_summary("row_coverage_ratio", round(row_coverage_ratio, 6), "pass" if row_coverage_ratio >= 0.95 else "fail", ">=0.95"),
            make_summary("stock_coverage_ratio", round(stock_coverage_ratio, 6), "pass" if stock_coverage_ratio >= 0.95 else "fail", ">=0.95"),
            make_summary("latest_manifest_error_count", int(latest_status_counts.get("error", 0)), "info"),
            make_summary("latest_manifest_partial_ok_count", int(latest_status_counts.get("partial_ok", 0)), "info"),
            make_summary("data_quality_pass", str(data_quality_pass).lower(), "pass" if data_quality_pass else "fail"),
            make_summary(
                "adjusted_return_baseline_allowed",
                str(adjusted_return_baseline_allowed).lower(),
                "pass" if adjusted_return_baseline_allowed else "fail",
                "data_quality_pass=true and both coverage ratios >=0.95",
            ),
            make_summary("formal_performance_conclusion_allowed", "false", "fail", "always false for this QA stage"),
            make_summary("execution_sim_ready", "false", "fail", "requires historical ST/suspension/limit-up-down state"),
        ]
    )

    issues_df = pd.DataFrame(issues, columns=ISSUE_COLUMNS)
    summary_df = pd.DataFrame(summaries, columns=SUMMARY_COLUMNS)
    decisions = {
        "data_quality_pass": data_quality_pass,
        "adjusted_return_baseline_allowed": adjusted_return_baseline_allowed,
        "formal_performance_conclusion_allowed": False,
        "execution_sim_ready": False,
    }
    return QAResult(
        issues=issues_df,
        summary=summary_df,
        source_distribution=source_distribution(df),
        decisions=decisions,
        manifest_latest=manifest_latest,
    )


def render_report(result: QAResult) -> str:
    def metric(name: str, default: object = "") -> object:
        rows = result.summary[result.summary["metric"].eq(name)]
        return default if rows.empty else rows.iloc[0]["value"]

    severity_counts = result.issues["severity"].value_counts().to_dict() if not result.issues.empty else {}
    issue_counts = result.issues["issue_type"].value_counts().to_dict() if not result.issues.empty else {}

    lines = [
        "# Adjusted Price Panel QA v1.2",
        "",
        "This report checks data quality only. It does not run a strategy, does not produce an investment conclusion, and does not modify source CSV files.",
        "",
        "## Decisions",
        f"- data_quality_pass: {str(result.decisions['data_quality_pass']).lower()}",
        f"- adjusted_return_baseline_allowed: {str(result.decisions['adjusted_return_baseline_allowed']).lower()}",
        "- formal_performance_conclusion_allowed: false",
        "- execution_sim_ready: false",
        "",
        "Downstream join/backtest code must apply `code6` normalization before using this panel, because CSV readers can drop leading zeros from `stock_code`.",
        "",
        "## Core Metrics",
        f"- rows: {metric('total_rows')}",
        f"- stocks: {metric('stock_count')}",
        f"- universe stocks: {metric('universe_stock_count')}",
        f"- parsed date range: {metric('date_min')} to {metric('date_max')}",
        f"- row_coverage_ratio: {metric('row_coverage_ratio')}",
        f"- stock_coverage_ratio: {metric('stock_coverage_ratio')}",
        f"- duplicate stock/date rows: {metric('duplicate_stock_date_rows')}",
        f"- exact duplicate rows: {metric('exact_duplicate_rows')}",
        "",
        "## Issue Counts",
    ]

    if issue_counts:
        lines.append(f"- by severity: {severity_counts}")
        for issue_type, count in issue_counts.items():
            lines.append(f"- {issue_type}: {count}")
    else:
        lines.append("- no issues recorded")

    lines.extend(["", "## Latest Manifest Status"])
    if result.manifest_latest.empty or "final_status" not in result.manifest_latest.columns:
        lines.append("- no manifest rows available")
    else:
        for status, count in result.manifest_latest["final_status"].fillna("").value_counts().items():
            lines.append(f"- {status or 'blank'}: {count}")
        for status in ("error", "partial_ok"):
            codes = result.manifest_latest.index[result.manifest_latest["final_status"].eq(status)].tolist()
            if codes:
                lines.append(f"- latest {status} stocks: {', '.join(codes)}")

    lines.extend(["", "## Source Distribution"])
    for _, row in result.source_distribution.iterrows():
        lines.append(f"- {row['source_qfq']}: rows={row['row_count']}, stocks={row['stock_count']}")

    lines.extend(
        [
            "",
            "## Caveats",
            "- `formal_performance_conclusion_allowed` remains false even if adjusted-return baseline is allowed.",
            "- `execution_sim_ready` remains false because historical ST, suspension, and limit-up/down states are still missing.",
            "- Return outliers and qfq/raw alignment warnings are review flags, not automatic investment conclusions.",
        ]
    )
    return "\n".join(lines) + "\n"


def read_universe_codes(path: Path) -> list[str]:
    df = pd.read_csv(path, dtype=str)
    for col in ("stock_code", "code"):
        if col in df.columns:
            return [code6(value) for value in df[col].dropna().tolist()]
    raise ValueError(f"No stock_code/code column in {path}")


def run() -> QAResult:
    panel = pd.read_csv(ADJUSTED_PATH, dtype=str, low_memory=False)
    manifest = pd.read_csv(MANIFEST_PATH, dtype=str) if MANIFEST_PATH.exists() else pd.DataFrame()
    # Existence check keeps the QA tied to the expected v1.2 input set.
    if not RAW_BASE_PATH.exists():
        raise FileNotFoundError(RAW_BASE_PATH)
    universe_codes = read_universe_codes(UNIVERSE_PATH)

    result = analyze(panel, universe_codes, manifest)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.issues.to_csv(ISSUES_OUT, index=False, encoding="utf-8-sig")
    result.summary.to_csv(SUMMARY_OUT, index=False, encoding="utf-8-sig")
    REPORT_OUT.write_text(render_report(result), encoding="utf-8")

    print(f"wrote {REPORT_OUT}")
    print(f"wrote {ISSUES_OUT}")
    print(f"wrote {SUMMARY_OUT}")
    for key, value in result.decisions.items():
        print(f"{key}={str(value).lower()}")
    return result


if __name__ == "__main__":
    run()
