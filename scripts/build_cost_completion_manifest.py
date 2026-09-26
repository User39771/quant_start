"""Freeze the COST full-history completion manifest before any new RPC."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from audit_robinhood_chain_phase0 import NYSE_EARLY_CLOSES_2026, NYSE_HOLIDAYS_2026


NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
CUTOFF = date(2026, 9, 4)
POOL_START = "2026-07-22T23:51:49Z"
OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")


def is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS_2026


def eligible_dates() -> list[str]:
    pool_start = datetime.fromisoformat(POOL_START)
    days: list[date] = []
    day = date(2026, 7, 1)
    while day <= CUTOFF:
        if is_market_day(day):
            days.append(day)
        day += timedelta(days=1)
    result = []
    for previous_day, open_day in zip(days, days[1:]):
        close = time(13) if previous_day in NYSE_EARLY_CLOSES_2026 else time(16)
        start = datetime.combine(previous_day, close, NEW_YORK)
        if start.astimezone(UTC) >= pool_start:
            result.append(open_day.isoformat())
    return result


def main() -> None:
    eligible = eligible_dates()
    audit = json.loads((OUT / "cost_early_late_feasibility_audit.json").read_text(encoding="utf-8"))
    collected = list(audit["early_dates"]) + list(audit["late_dates"])
    missing = [d for d in eligible if d not in collected]
    assert len(eligible) == 31, len(eligible)
    assert len(collected) == 10, len(collected)
    assert len(missing) == 21, len(missing)
    assert len(set(missing)) == len(missing)
    assert all(d <= CUTOFF.isoformat() for d in missing)
    assert all(d not in collected for d in missing)

    manifest = {
        "approval_status": "HUMAN_SOL_APPROVED_COST_COMPLETION",
        "token_symbol": "COST",
        "eligibility_source": "build_robinhood_five_token_panel.all_sessions() with pool_start 2026-07-22T23:51:49Z",
        "cutoff": CUTOFF.isoformat(),
        "eligibility_start": eligible[0],
        "eligible_dates": eligible,
        "existing_collected_dates": sorted(collected),
        "missing_dates_to_collect": missing,
        "expected_total_after_completion": len(eligible),
        "frozen_before_rpc": True,
    }
    (OUT / "cost_full_history_completion_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "eligible": len(eligible),
        "collected": len(collected),
        "missing": len(missing),
        "missing_dates": missing,
    }, indent=2))


if __name__ == "__main__":
    main()
