"""Recover the Robinhood Chain token/pool inventory and build a second-wave
candidate table + shortlist for human/Sol review.

This is repository forensics only. It makes no RPC calls, performs no new
collection, and does not select the final replacement tokens.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path("reports/robinhood_chain_pilot/eligible_token_inventory")
OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
INVENTORY_CSV = ROOT / "eligible_token_inventory.csv"
LOW_ATTENTION_CSV = ROOT / "low_attention_control_candidates.csv"

# Frozen research state: assets already decided by prior work.
CORE_PRIMARY = {"NVDA", "GME"}
SECONDARY = {"TSLA", "COST", "USO"}
REJECTED = {"AMZN", "UPS"}
NOT_SECOND_WAVE = CORE_PRIMARY | SECONDARY | REJECTED

# Structural rejections established by the inventory builder.
STRUCTURAL_REJECT = {"SPCX", "XNDU"}

# CCL was classified REJECT by the focused low-attention control validation.
CONTROL_REJECT = {"CCL"}


def num(value: str | None) -> float | None:
    s = (value or "").replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_deep_hours(evidence: str | None) -> tuple[int | None, int | None, float | None]:
    if not evidence or evidence.strip().upper() == "UNKNOWN":
        return None, None, None
    match = re.search(r"(\d+)\s+deep-overnight hours with volume", evidence)
    hours = int(match.group(1)) if match else None
    money = re.search(r"\$\s?([\d,]+\.?\d*)\s+aggregate", evidence)
    notional = float(money.group(1).replace(",", "")) if money else None
    return hours, 16, notional


def parse_rpc_count(evidence: str | None) -> int | None:
    if not evidence or evidence.strip().upper() == "UNKNOWN":
        return None
    match = re.search(r"(\d+)\s+Swap logs", evidence)
    return int(match.group(1)) if match else None


def parse_control_rpc(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def action_date(row: dict) -> tuple[int, int, int] | None:
    raw = row.get("corporate_action_warning") or ""
    if not raw:
        return None
    try:
        actions = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not actions:
        return None
    date = actions[0].get("processDate") or {}
    if {"year", "month", "day"}.issubset(date):
        return int(date["year"]), int(date["month"]), int(date["day"])
    return None


def role_hint(symbol: str) -> str:
    hints = {
        "META": "large-cap technology / social",
        "AAPL": "large-cap consumer technology",
        "GOOGL": "large-cap technology / search-advertising",
        "MSFT": "large-cap enterprise technology",
        "RDDT": "consumer internet / social",
        "SGOV": "short-term treasury bond ETF",
        "MU": "semiconductor / memory",
        "AMD": "semiconductor",
        "PLTR": "data analytics / software",
        "DELL": "technology hardware",
        "RIVN": "electric vehicle / automotive",
        "NFLX": "streaming / media",
        "USAR": "financial / ETF",
        "SNDK": "semiconductor / storage",
        "MRNA": "healthcare / biotech",
        "ON": "semiconductor",
        "PENG": "financial / diversified",
        "MRVL": "semiconductor",
        "CCL": "travel / consumer discretionary",
        "ASML": "semiconductor equipment",
        "ORCL": "enterprise software",
        "LITE": "optical / communications",
        "IREN": "data center / bitcoin mining",
    }
    return hints.get(symbol, "UNKNOWN")


def multiplier_status(row: dict) -> str:
    risk = row.get("historical_multiplier_risk", "")
    if risk == "CLEAR_CURRENT_NO_RECORDED_ACTION":
        return "MULTIPLIER_SIMPLE"
    if risk == "DOCUMENTED_ACTION_DATE_AWARE_REVIEW":
        date = action_date(row)
        if date and (date[0], date[1], date[2]) > (2026, 9, 4):
            return "MULTIPLIER_SIMPLE"
        return "MULTIPLIER_RESOLVED_COMPLEX"
    if risk == "UNRESOLVED_NONUNIT_MULTIPLIER":
        return "MULTIPLIER_UNRESOLVED"
    return "MULTIPLIER_UNKNOWN"


def history_flag(sessions: int | None) -> str:
    if sessions is None:
        return "HISTORY_UNKNOWN"
    return "HISTORY_OK" if sessions >= 20 else "HISTORY_SHORT"


def activity_flag(swaps: float | None) -> str:
    if swaps is None:
        return "ACTIVITY_UNKNOWN"
    if swaps >= 1000:
        return "ACTIVITY_STRONG"
    if swaps >= 100:
        return "ACTIVITY_MODERATE"
    return "ACTIVITY_WEAK"


def deep_flag(hours: int | None) -> str:
    if hours is None:
        return "DEEP_ACTIVITY_UNKNOWN"
    if hours >= 12:
        return "DEEP_ACTIVITY_STRONG"
    if hours >= 6:
        return "DEEP_ACTIVITY_MODERATE"
    return "DEEP_ACTIVITY_WEAK"


def rpc_flag(count: int | None) -> str:
    if count is None:
        return "RECENT_RPC_UNKNOWN"
    return "RECENT_RPC_ACTIVE" if count > 0 else "RECENT_RPC_INACTIVE"


def protocol_flag(version: str) -> str:
    return "V3_SIMPLE" if version == "Uniswap V3" else "V4_PROTOCOL_DIFFERENCE"


def build_candidates() -> list[dict]:
    inv = {r["token_symbol"]: r for r in csv.DictReader(INVENTORY_CSV.open(encoding="utf-8-sig"))}
    low = {r["symbol"]: r for r in csv.DictReader(LOW_ATTENTION_CSV.open(encoding="utf-8-sig"))}

    rows: list[dict] = []
    for symbol, r in sorted(inv.items()):
        if r.get("has_20_sessions") != "True":
            continue
        version = r.get("venue_version", "UNKNOWN")
        sessions = int(r["eligible_session_count_estimate"]) if r.get("eligible_session_count_estimate", "").strip().isdigit() else None
        swaps = num(r.get("recent_swap_count_or_rate"))
        notional = num(r.get("recent_notional_if_available"))

        # Prefer the newer focused-control row for deep/RPC evidence where present.
        control = low.get(symbol)
        if control:
            deep_hours, deep_possible, deep_notional = parse_deep_hours(control.get("deep_overnight_continuity"))
            rpc = parse_control_rpc(control.get("latest_500_block_official_rpc_swap_count"))
        else:
            deep_hours, deep_possible, deep_notional = parse_deep_hours(r.get("overnight_activity_evidence"))
            rpc = parse_rpc_count(r.get("recent_rpc_execution_evidence"))

        if symbol in CORE_PRIMARY:
            prior = "CORE_PRIMARY"
            eligible = False
        elif symbol in SECONDARY:
            prior = "SECONDARY_SENSITIVITY"
            eligible = False
        elif symbol in REJECTED:
            prior = "REJECTED_FOR_PRIMARY"
            eligible = False
        elif symbol in STRUCTURAL_REJECT:
            prior = "STRUCTURALLY_REJECTED"
            eligible = False
        elif symbol in CONTROL_REJECT:
            prior = "REJECTED_LOW_ATTENTION_CONTROL"
            eligible = False
        else:
            prior = "NEVER_SCREENED"
            eligible = True

        deep_rate = (deep_hours / deep_possible) if deep_hours is not None and deep_possible else None
        rows.append({
            "symbol": symbol,
            "role_hint": role_hint(symbol),
            "pool_version": version,
            "estimated_sessions": sessions,
            "rolling_swaps": swaps,
            "rolling_usdg_notional": notional,
            "deep_hours_active": deep_hours,
            "deep_hours_possible": deep_possible,
            "deep_hour_activity_rate": round(deep_rate, 3) if deep_rate is not None else None,
            "recent_rpc_activity": rpc,
            "multiplier_status": multiplier_status(r),
            "corporate_action_complexity": (r.get("corporate_action_warning") or "")[:200] or None,
            "structural_risk": "V4 venue requires a new decode + pool-order branch" if version == "Uniswap V4" else "V3 compatible with existing collector",
            "prior_screen_status": prior,
            "second_wave_eligible": eligible,
            "history_flag": history_flag(sessions),
            "activity_flag": activity_flag(swaps),
            "deep_activity_flag": deep_flag(deep_hours),
            "rpc_flag": rpc_flag(rpc),
            "protocol_flag": protocol_flag(version),
            "canonical_contract": r.get("canonical_contract"),
            "pool_or_market_id": r.get("pool_or_market_id"),
            "first_verified_spot_date": r.get("first_verified_spot_date"),
            "current_multiplier": r.get("current_multiplier"),
        })
    return rows


SHORTLIST = [
    {
        "symbol": "META",
        "priority": "SECOND_WAVE_HIGH_PRIORITY",
        "why_survived": "Strongest recovered unscreened activity (38,155 rolling swaps, $6.12m notional) with confirmed 16/16 deep-overnight hours in the first-wave 48-hour probe and a clean unit multiplier.",
        "strongest_evidence": "Only unscreened candidate with already-observed deep-hour continuity (16/16, $248k deep notional) plus 4 official-RPC swaps in the latest 500 blocks.",
        "largest_risk": "Uniswap V4 venue is not supported by the current V3-only session collector; a new Swap-event decode and pool-order branch is required, and V3/V4 comparability is an open research question.",
    },
    {
        "symbol": "AAPL",
        "priority": "SECOND_WAVE_HIGH_PRIORITY",
        "why_survived": "Highest V3 swap count among unscreened candidates (13,656 rolling swaps, $1.95m notional) and 32 estimated sessions.",
        "strongest_evidence": "Large aggregate token activity on a structurally simple V3 pool.",
        "largest_risk": "Documented 2026-08-13 cash dividend creates an in-window multiplier transition; the exact transition timestamp is not yet forensically established in local artifacts.",
    },
    {
        "symbol": "GOOGL",
        "priority": "SECOND_WAVE_HIGH_PRIORITY",
        "why_survived": "Strong V3 activity (10,196 rolling swaps, $1.94m notional) with 43 estimated sessions.",
        "strongest_evidence": "Multiplier is 1.0 through the 2026-09-04 cutoff because its dividend is dated 2026-09-14 (after the window), so no in-window corporate-action adjustment is needed.",
        "largest_risk": "Deep-hour boundary observability is unknown locally; mega-cap high-attention profile resembles AMZN, which failed the frozen deep boundary screen.",
    },
    {
        "symbol": "MSFT",
        "priority": "SECOND_WAVE_MEDIUM_PRIORITY",
        "why_survived": "Strong V3 activity (9,792 rolling swaps, $940k notional) and 36 estimated sessions.",
        "strongest_evidence": "Multiplier is 1.0 through the cutoff (dividend dated 2026-09-10 is outside the window).",
        "largest_risk": "Deep-hour activity is unknown locally; mega-cap profile again resembles the failed AMZN cluster.",
    },
    {
        "symbol": "RDDT",
        "priority": "SECOND_WAVE_MEDIUM_PRIORITY",
        "why_survived": "Clean unit multiplier with no recorded action and the longest eligible history (53 sessions), providing a consumer-internet role outside the mega-cap tech cluster.",
        "strongest_evidence": "3,624 rolling swaps / $974k notional on a simple V3 pool with no multiplier complexity.",
        "largest_risk": "Deep-hour observability is unknown and aggregate activity is moderate rather than high.",
    },
    {
        "symbol": "SGOV",
        "priority": "SECOND_WAVE_MEDIUM_PRIORITY",
        "why_survived": "Highest unscreened swap count (17,219 rolling swaps, $2.09m notional) and a non-equity treasury-ETF role for structural diversification.",
        "strongest_evidence": "Very large aggregate activity on a simple V3 pool.",
        "largest_risk": "It is an ETF rather than a Stock Token, its 2026-09-04 dividend sits exactly at the cutoff, and deep-hour observability is unknown.",
    },
]


def shortlist_priority_map() -> dict[str, str]:
    return {item["symbol"]: item["priority"] for item in SHORTLIST}


def build_recovery(candidates: list[dict]) -> dict:
    active_assets = 194
    mapped_pools = 123
    v3 = 42
    v4 = 81
    ge15 = 32
    ge20 = 31
    unscreened = [c for c in candidates if c["second_wave_eligible"]]
    return {
        "recovery_mode": "REPOSITORY_FORENSICS_ONLY",
        "as_of_notes": "Inventory snapshot dated 2026-09-09; low-attention focused validation dated 2026-09-10.",
        "recovered_counts": {
            "active_mainnet_stock_tokens": active_assets,
            "canonical_usdg_pool_mappings": mapped_pools,
            "uniswap_v3_pools": v3,
            "uniswap_v4_pools": v4,
            "with_at_least_15_estimated_sessions": ge15,
            "with_at_least_20_estimated_sessions": ge20,
            "unscreened_with_adequate_history": len(unscreened),
        },
        "excluded_from_second_wave": {
            "core_primary": sorted(CORE_PRIMARY),
            "secondary_sensitivity": sorted(SECONDARY),
            "rejected_for_primary": sorted(REJECTED),
            "structural_reject": sorted(STRUCTURAL_REJECT),
            "low_attention_control_reject": sorted(CONTROL_REJECT),
        },
        "shortlist": SHORTLIST,
        "v4_classification": {
            "META": "V4_IMPLEMENTATION_SMALL_EXTENSION",
            "reason": "The frozen 5-minute VWAP price formula is venue-agnostic; the inventory builder already recovered the V4 Swap topic and PoolManager address. A V4 Swap-event decode branch (int128 amounts plus fee field) and pool-order resolution from the PoolId are required but were not implemented in the V3 session collector.",
            "comparability_caveat": "V3/V4 cross-venue liquidity comparability remains an open research question for human/Sol review.",
        },
        "aapl_multiplier_classification": "AAPL_MULTIPLIER_LIKELY_RESOLVABLE",
        "aapl_multiplier_reason": "AAPL has a documented, completed 2026-08-13 cash dividend and a non-unit current multiplier (1.000566). The project already resolved timestamp-effective multipliers for COST and UPS, but no AAPL-specific transition-timestamp forensic artifact was recovered, so exact adjustment is not yet established.",
    }


def candidate_table_csv(candidates: list[dict]) -> None:
    fields = [
        "symbol", "role_hint", "pool_version", "estimated_sessions", "rolling_swaps",
        "rolling_usdg_notional", "deep_hours_active", "deep_hours_possible",
        "deep_hour_activity_rate", "recent_rpc_activity", "activity_continuity_note",
        "multiplier_status", "corporate_action_complexity", "structural_risk",
        "prior_screen_status", "measurement_feasibility_evidence", "candidate_notes",
        "history_flag", "activity_flag", "deep_activity_flag", "rpc_flag",
        "protocol_flag", "canonical_contract", "pool_or_market_id",
        "first_verified_spot_date", "current_multiplier", "second_wave_eligible",
    ]
    priority = shortlist_priority_map()
    rows = []
    for c in candidates:
        short = next((s for s in SHORTLIST if s["symbol"] == c["symbol"]), None)
        notes = []
        if short:
            notes.append(f"SHORTLIST {short['priority']}")
        if c["symbol"] in STRUCTURAL_REJECT:
            notes.append("no valid US regular-session underlying target")
        if c["symbol"] in CONTROL_REJECT:
            notes.append("0 RPC swaps in latest 500 blocks; very sparse")
        rows.append({
            "symbol": c["symbol"],
            "role_hint": c["role_hint"],
            "pool_version": c["pool_version"],
            "estimated_sessions": c["estimated_sessions"],
            "rolling_swaps": c["rolling_swaps"],
            "rolling_usdg_notional": c["rolling_usdg_notional"],
            "deep_hours_active": c["deep_hours_active"],
            "deep_hours_possible": c["deep_hours_possible"],
            "deep_hour_activity_rate": c["deep_hour_activity_rate"],
            "recent_rpc_activity": c["recent_rpc_activity"],
            "activity_continuity_note": (
                "confirmed deep-hour continuity (48h probe)" if c["deep_hours_active"] is not None
                else "deep-hour activity unknown; needs bounded 48h GeckoTerminal probe"
            ),
            "multiplier_status": c["multiplier_status"],
            "corporate_action_complexity": c["corporate_action_complexity"],
            "structural_risk": c["structural_risk"],
            "prior_screen_status": c["prior_screen_status"],
            "measurement_feasibility_evidence": (
                short["strongest_evidence"] if short else "aggregate activity only; deep-hour observability not yet verified"
            ),
            "candidate_notes": "; ".join(notes) or None,
            "history_flag": c["history_flag"],
            "activity_flag": c["activity_flag"],
            "deep_activity_flag": c["deep_activity_flag"],
            "rpc_flag": c["rpc_flag"],
            "protocol_flag": c["protocol_flag"],
            "canonical_contract": c["canonical_contract"],
            "pool_or_market_id": c["pool_or_market_id"],
            "first_verified_spot_date": c["first_verified_spot_date"],
            "current_multiplier": c["current_multiplier"],
            "second_wave_eligible": c["second_wave_eligible"],
        })
    with (OUT / "second_wave_candidate_table.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_recovery_md(recovery: dict, candidates: list[dict]) -> str:
    c = recovery["recovered_counts"]
    lines = [
        "# Second-wave inventory recovery",
        "",
        "Repository-forensics only. No RPC calls, no collection, no predictive analysis.",
        "",
        "## Recovered universe",
        "",
        f"- Active mainnet Stock Tokens: {c['active_mainnet_stock_tokens']}.",
        f"- Canonical-token/USDG pools mapped: {c['canonical_usdg_pool_mappings']} "
        f"({c['uniswap_v3_pools']} V3, {c['uniswap_v4_pools']} V4).",
        f"- With >=15 estimated sessions: {c['with_at_least_15_estimated_sessions']}.",
        f"- With >=20 estimated sessions: {c['with_at_least_20_estimated_sessions']}.",
        f"- Unscreened with adequate history: {c['unscreened_with_adequate_history']}.",
        "",
        "## Excluded (already decided)",
        "",
        f"- Core primary: {', '.join(sorted(CORE_PRIMARY))}.",
        f"- Secondary/sensitivity: {', '.join(sorted(SECONDARY))}.",
        f"- Rejected for primary: {', '.join(sorted(REJECTED))}.",
        f"- Structural reject: {', '.join(sorted(STRUCTURAL_REJECT))}.",
        f"- Low-attention control reject: {', '.join(sorted(CONTROL_REJECT))}.",
        "",
        "## Must-cover historical candidates",
        "",
    ]
    for symbol in ("META", "AAPL", "MRNA", "CCL"):
        row = next(cd for cd in candidates if cd["symbol"] == symbol)
        lines.append(
            f"- **{symbol}** ({row['pool_version']}, {row['estimated_sessions']} sessions): "
            f"{row['rolling_swaps']} rolling swaps / ${row['rolling_usdg_notional'] or 0:.0f} notional; "
            f"deep hours {row['deep_hours_active'] if row['deep_hours_active'] is not None else 'UNKNOWN'}/16; "
            f"RPC {row['recent_rpc_activity'] if row['recent_rpc_activity'] is not None else 'UNKNOWN'}; "
            f"{row['multiplier_status']}."
        )
    lines += [
        "",
        "## Shortlist for human review",
        "",
        "| Symbol | Priority | Pool | Sessions | Rolling swaps | Rolling notional | Deep hours | RPC | Multiplier |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for s in SHORTLIST:
        row = next(cd for cd in candidates if cd["symbol"] == s["symbol"])
        lines.append(
            f"| {s['symbol']} | {s['priority'].replace('SECOND_WAVE_', '')} | {row['pool_version'].replace('Uniswap ', '')} | "
            f"{row['estimated_sessions']} | {row['rolling_swaps']} | {row['rolling_usdg_notional']:.0f} | "
            f"{row['deep_hours_active'] if row['deep_hours_active'] is not None else 'UNK'} | "
            f"{row['recent_rpc_activity'] if row['recent_rpc_activity'] is not None else 'UNK'} | "
            f"{row['multiplier_status'].replace('MULTIPLIER_', '')} |"
        )
    lines += [
        "",
        "## Structural notes",
        "",
        f"- META V4: {recovery['v4_classification']['META']}. {recovery['v4_classification']['reason']}",
        f"- AAPL multiplier: {recovery['aapl_multiplier_classification']}. {recovery['aapl_multiplier_reason']}",
        "",
        "NO SECOND-WAVE COLLECTION AUTHORIZED YET. Final selection belongs to human/Sol review.",
        "",
    ]
    return "\n".join(lines)


def render_shortlist_md(recovery: dict) -> str:
    lines = [
        "# Second-wave candidate shortlist (for human/Sol review)",
        "",
        "This is a recommendation only. It does not authorize collection and does not select a final panel member.",
        "",
    ]
    for s in SHORTLIST:
        lines.append(f"## {s['symbol']} — {s['priority']}")
        lines.append("")
        lines.append(f"- Why it survived: {s['why_survived']}")
        lines.append(f"- Strongest evidence: {s['strongest_evidence']}")
        lines.append(f"- Largest remaining risk: {s['largest_risk']}")
        lines.append("")
    lines.append("## Explicit non-selection")
    lines.append("")
    lines.append("MRNA and CCL are not shortlisted: MRNA is only two sessions above the eligibility floor with thin rolling activity and unknown deep-hour coverage; CCL was rejected in the focused control validation (32 rolling swaps, 0 recent RPC swaps).")
    lines.append("")
    lines.append("NO SECOND-WAVE COLLECTION AUTHORIZED YET.")
    return "\n".join(lines)


def main() -> None:
    candidates = build_candidates()
    recovery = build_recovery(candidates)
    candidate_table_csv(candidates)

    (OUT / "second_wave_inventory_recovery.json").write_text(
        json.dumps(recovery, indent=2, allow_nan=False, default=str), encoding="utf-8"
    )
    (OUT / "second_wave_inventory_recovery.md").write_text(
        render_recovery_md(recovery, candidates), encoding="utf-8"
    )
    (OUT / "second_wave_candidate_shortlist.json").write_text(
        json.dumps({"shortlist": SHORTLIST}, indent=2, allow_nan=False, default=str), encoding="utf-8"
    )
    (OUT / "second_wave_candidate_shortlist.md").write_text(
        render_shortlist_md(recovery), encoding="utf-8"
    )
    print(json.dumps(recovery["recovered_counts"], indent=2))
    print("shortlist:", [s["symbol"] for s in SHORTLIST])


if __name__ == "__main__":
    main()
