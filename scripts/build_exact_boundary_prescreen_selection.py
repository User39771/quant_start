"""Freeze the three deterministic GOOGL/META exact-boundary prescreen dates.

This writes the selection artifacts before any boundary-window retrieval so the
dates are outcome-blind. It performs no RPC calls.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from audit_robinhood_chain_phase0 import NYSE_EARLY_CLOSES_2026, NYSE_HOLIDAYS_2026


NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
CUTOFF = date(2026, 9, 4)
OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")

TOKENS = {
    "GOOGL": {"pool_start": "2026-07-10T22:04:49Z"},
    "META": {"pool_start": "2026-07-11T12:18:48Z"},
}


def is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS_2026


def eligible_dates(pool_start_iso: str) -> list[str]:
    pool_start = datetime.fromisoformat(pool_start_iso.replace("Z", "+00:00"))
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
    for symbol, config in TOKENS.items():
        dates = eligible_dates(config["pool_start"])
        n = len(dates)
        mid_index = n // 2
        selected = [dates[0], dates[mid_index], dates[-1]]
        selection = {
            "token_symbol": symbol,
            "selection_status": "FROZEN_BEFORE_BOUNDARY_RETRIEVAL",
            "cutoff": CUTOFF.isoformat(),
            "eligible_history_anchor_utc": config["pool_start"],
            "nominal_eligible_session_count": n,
            "first_eligible_date": dates[0],
            "last_eligible_date": dates[-1],
            "selection_rule": (
                "EARLY = first eligible date; MIDDLE = date at index floor(n/2); "
                "LATE = final eligible date. No liquidity/return/boundary inputs used."
            ),
            "selected_dates": {
                "early": selected[0],
                "middle": selected[1],
                "late": selected[2],
            },
            "selection_inputs_excluded": [
                "swap counts", "boundary availability", "returns", "news",
                "volatility", "liquidity", "post-retrieval information",
            ],
        }
        path = OUT / f"{symbol.lower()}_exact_boundary_prescreen_selection.json"
        path.write_text(json.dumps(selection, indent=2), encoding="utf-8")
        print(symbol, json.dumps(selected))


if __name__ == "__main__":
    main()
