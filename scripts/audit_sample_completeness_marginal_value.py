"""Local-only sample completeness + marginal collection value audit.

Recovers eligibility / collection / robust-30m state for the nine existing
tokens and assigns a descriptive marginal collection value. No RPC, no returns,
no prediction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
ROBUST_CSV = OUT / "robust_30m_deep_coverage_by_token.csv"
SESSIONS = OUT / "sessions"


# Verified from existing artifacts (panel self_check, coverage CSV, selection
# files, and the GOOGL/META exact-boundary prescreen selection).
TOKENS = {
    "NVDA": {
        "eligible": 33,
        "design": "FULL_HISTORY",
        "eligibility_start": "2026-07-22",
        "corrected_note": None,
    },
    "GME": {
        "eligible": 30,
        "design": "FULL_HISTORY",
        "eligibility_start": "2026-07-27",
        "corrected_note": None,
    },
    "TSLA": {
        "eligible": 34,  # research-eligible; 41 pool-eligible, 7 pre-activity retained-but-ineligible
        "design": "FULL_HISTORY_WITH_ELIGIBILITY_CORRECTION",
        "eligibility_start": "2026-07-21",
        "corrected_note": "7 pre-activity sessions (2026-07-10..07-20) retained on disk but excluded from research-eligible sample",
    },
    "COST": {
        "eligible": 31,
        "design": "BOUNDED_EARLY_LATE_SCREEN",
        "eligibility_start": "2026-07-24",
        "corrected_note": None,
    },
    "USO": {
        "eligible": 35,
        "design": "BOUNDED_EARLY_LATE_SCREEN",
        "eligibility_start": "2026-07-20",
        "corrected_note": None,
    },
    "AMZN": {
        "eligible": 33,
        "design": "BOUNDED_REPLACEMENT_SCREEN",
        "eligibility_start": "2026-07-22",
        "corrected_note": "rejected for primary (AMZN_NOT_USEFUL_FOR_PRIMARY_DEEP_ANALYSIS)",
    },
    "UPS": {
        "eligible": 46,
        "design": "BOUNDED_REPLACEMENT_SCREEN",
        "eligibility_start": "2026-07-02",
        "corrected_note": "rejected for primary (UPS_NOT_USEFUL_FOR_PRIMARY_DEEP_ANALYSIS)",
    },
    "GOOGL": {
        "eligible": 39,
        "design": "THREE_DATE_PRESCREEN",
        "eligibility_start": "2026-07-14",
        "corrected_note": None,
    },
    "META": {
        "eligible": 39,
        "design": "THREE_DATE_PRESCREEN",
        "eligibility_start": "2026-07-14",
        "corrected_note": "V4 price reconstruction not implemented for production",
    },
}


def collected_count(token: str) -> int:
    if token in ("GOOGL", "META"):
        # Three prescreen dates were checked via minimal RPC (boundary windows
        # only), not full sessions.
        return 3
    path = SESSIONS / token
    if not path.exists():
        return 0
    return sum(1 for p in path.iterdir() if p.is_dir())


def research_sample_count(token: str) -> int:
    collected = collected_count(token)
    if token == "TSLA":
        # research-eligible only (exclude 7 retained pre-activity sessions)
        return collected - 7
    return collected


def engineering_ready(token: str) -> bool:
    return token != "META"


def collection_value(token: str, robust_rate: float, remaining: int) -> str:
    if token in ("NVDA", "GME", "TSLA"):
        return "COLLECTION_COMPLETE"
    if token in ("AMZN", "UPS"):
        return "COLLECTION_VALUE_NONE"
    if token == "META":
        return "COLLECTION_VALUE_NONE"
    if token == "COST":
        return "COLLECTION_VALUE_HIGH"
    if token == "GOOGL":
        return "COLLECTION_VALUE_LOW"
    if token == "USO":
        return "COLLECTION_VALUE_LOW"
    return "COLLECTION_VALUE_NONE"


def reason(token: str, robust_rate: float, robust_share: float, remaining: int, late_note: str = "") -> str:
    if token == "COST":
        return "Strongest incomplete candidate: 50% robust in bounded sample, 100% robust in late five, clean V3, multiplier already resolved."
    if token == "USO":
        return "Late-period observability improved but robust rate is only 20%; ETF role is a secondary diversification consideration."
    if token == "AMZN":
        return "Rejected for primary; 20% robust rate does not justify resuming a rejected asset."
    if token == "UPS":
        return "Effectively dormant (0 robust observations); no measurement-value justification."
    if token == "GOOGL":
        return "Robust rate is 33% but based on only 3 prescreen dates; COST offers a cleaner path to a third asset."
    if token == "META":
        return "Zero robust observations and V4 price reconstruction is not implemented."
    return "Full history already collected."


def main() -> None:
    robust = pd.read_csv(ROBUST_CSV).set_index("token")
    rows = []
    for token, cfg in TOKENS.items():
        eligible = cfg["eligible"]
        collected = collected_count(token)
        research = research_sample_count(token)
        remaining = max(0, eligible - research)
        completion = round(research / eligible, 4) if eligible else None
        rr = robust.loc[token]
        robust_count = int(rr["30m_robust_count"])
        robust_rate = float(rr["30m_robust_rate"])
        robust_share = rr["robust_share_among_available"]
        robust_share = float(robust_share) if pd.notna(robust_share) else None
        rate_status = "FULL_HISTORY_ESTIMATE" if cfg["design"].startswith("FULL_HISTORY") else "PROVISIONAL_BOUNDED_SAMPLE"
        value = collection_value(token, robust_rate, remaining)
        rough = None
        if remaining > 0 and cfg["design"] not in ("FULL_HISTORY",):
            rough = round(remaining * robust_rate, 1)
        rows.append({
            "token": token,
            "eligible_sessions": eligible,
            "collected_sessions": collected,
            "research_sample_sessions": research,
            "remaining_sessions": remaining,
            "completion_rate": completion,
            "sampling_design": cfg["design"],
            "robust_rate_30m": robust_rate,
            "robust_count": robust_count,
            "robust_rate_status": rate_status,
            "20:00_non_thin_rate": float(rr["20:00_non_thin_rate"]),
            "04:00_non_thin_rate": float(rr["04:00_non_thin_rate"]),
            "engineering_ready": engineering_ready(token),
            "rough_expected_additional_robust_rows": rough,
            "collection_value": value,
            "collection_reason": reason(token, robust_rate, robust_share, remaining),
            "eligibility_start": cfg["eligibility_start"],
            "cutoff_date": "2026-09-04",
            "corrected_note": cfg["corrected_note"],
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "sample_completeness_marginal_value_by_token.csv", index=False)

    # Ranked by measurement-value-per-effort, not raw expected-row count.
    # COST leads because its late five are 5/5 robust and its N is reliable;
    # GOOGL is deliberately not promoted on its small 3-date sample alone.
    priority_order = ["COST", "USO", "GOOGL"]
    ranking = {}
    for index, token in enumerate(priority_order, start=1):
        row = next(r for r in rows if r["token"] == token)
        if row["collection_value"] != "COLLECTION_VALUE_NONE" and row["remaining_sessions"] > 0:
            ranking[f"PRIORITY_{index}"] = token

    summary = {
        "cutoff": "2026-09-04",
        "per_token": {r["token"]: r for r in rows},
        "priority_ranking": ranking,
        "recommended_completion_target": ranking.get("PRIORITY_1"),
        "proposed_stop_rule": (
            f"Complete {ranking.get('PRIORITY_1')} only; then freeze the "
            "data-acquisition / feasibility stage regardless of outcome."
        ) if ranking else "No further collection is justified; freeze now.",
        "no_rpc": True,
        "no_predictive_analysis": True,
    }
    (OUT / "sample_completeness_marginal_value_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    lines = [
        "# Sample completeness and marginal collection value",
        "",
        "Local-only audit. No new collection, no returns, no prediction.",
        "",
        "| Token | Eligible | Collected | Research sample | Remaining | Completion | Design | Robust 30m | Robust count | Rate status | Value |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for r in rows:
        completion_text = f"{r['completion_rate']:.0%}" if r["completion_rate"] is not None else "n/a"
        lines.append(
            f"| {r['token']} | {r['eligible_sessions']} | {r['collected_sessions']} | "
            f"{r['research_sample_sessions']} | {r['remaining_sessions']} | "
            f"{completion_text} | {r['sampling_design']} | {r['robust_rate_30m']:.0%} | "
            f"{r['robust_count']} | {r['robust_rate_status']} | {r['collection_value']} |"
        )
    lines += [
        "",
        "## Priority ranking (remaining-history tokens only)",
        "",
    ]
    for rank, token in ranking.items():
        lines.append(f"- {rank}: {token}")
    if not ranking:
        lines.append("- (none)")
    lines += [
        "",
        "## Recommended stop rule",
        "",
        summary["proposed_stop_rule"],
        "",
        "## Freeze-now vs complete-highest-value",
        "",
        "- Freeze now: full-history core candidates remain NVDA and GME (TSLA full but secondary); robust breadth stays NVDA/GME-dominated; COST/USO/AMZN/UPS remain bounded-only.",
        "- Complete COST only: COST becomes a fuller third asset candidate (its late five sessions are 5/5 robust); bounded assets remain USO/AMZN/UPS; robust breadth likely improves but stays secondary-heavy.",
        "",
        "NO NEW RPC COLLECTION WAS PERFORMED. NO NEXT-OPEN OUTCOME WAS INSPECTED. NO PREDICTIVE ANALYSIS WAS RUN.",
        "",
    ]
    (OUT / "sample_completeness_marginal_value_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "ranking": ranking,
        "recommended": summary["recommended_completion_target"],
        "stop_rule": summary["proposed_stop_rule"],
    }, indent=2))


if __name__ == "__main__":
    main()
