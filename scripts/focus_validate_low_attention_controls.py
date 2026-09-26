"""Focused, bounded validation of four non-tech control candidates."""

from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime
from pathlib import Path

from build_robinhood_eligible_token_inventory import overnight_summary, recent_rpc_logs, verify_underlying


SOURCE = Path("reports/robinhood_chain_pilot/eligible_token_inventory/eligible_token_inventory.csv")
OUTPUT = Path("reports/robinhood_chain_pilot/eligible_token_inventory/low_attention_control_candidates.csv")
AS_OF = date(2026, 9, 10)

CANDIDATES = {
    "COST": {
        "sector": "Consumer Staples",
        "attention_characteristic": "Mature defensive retailer outside the technology/meme cluster",
        "complexity": "V3-compatible; historical multiplier path must be resolved before measurement",
        "confounds": "Membership retail exposure; earnings and consumer-spending sensitivity; unexplained non-unit multiplier",
        "suitability": "CONDITIONAL_CONTROL",
    },
    "UPS": {
        "sector": "Industrials",
        "attention_characteristic": "Mature transport/logistics issuer with a clean sector contrast",
        "complexity": "V3-compatible; documented 2026-09-03 dividend requires date-aware multiplier handling",
        "confounds": "Macro/trade sensitivity; recent dividend multiplier change; moderate token liquidity",
        "suitability": "USABLE_CONTROL",
    },
    "MRNA": {
        "sector": "Health Care",
        "attention_characteristic": "Non-tech health-care issuer outside the current meme/mega-cap cluster",
        "complexity": "V3-compatible; only a narrow margin above the 20-session floor",
        "confounds": "Biotech and clinical/regulatory event risk; short pool history; lower token liquidity",
        "suitability": "USABLE_CONTROL",
    },
    "CCL": {
        "sector": "Consumer Discretionary",
        "attention_characteristic": "Mature travel operator outside technology, though not a pristine low-attention name",
        "complexity": "V3-compatible; documented 2026-08-28 dividend requires date-aware multiplier handling",
        "confounds": "Very low token activity; cyclical travel/news exposure; dividend multiplier change",
        "suitability": "REJECT",
    },
}


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        inventory = {row["token_symbol"]: row for row in csv.DictReader(handle)}

    rows = []
    for symbol, labels in CANDIDATES.items():
        source = inventory[symbol]
        underlying_ok, underlying_url = verify_underlying(symbol)
        overnight = overnight_summary(source["pool_or_market_id"])
        rpc_logs = recent_rpc_logs(source["pool_or_market_id"], source["venue_version"])
        start = datetime.fromisoformat(source["first_verified_spot_date"].replace("Z", "+00:00")).date()
        rows.append(
            {
                "symbol": symbol,
                "company_or_underlying": source["token_name"].replace(" • Robinhood Token", ""),
                "broad_sector": labels["sector"],
                "underlying_attention_characteristic": labels["attention_characteristic"],
                "canonical_contract": source["canonical_contract"],
                "quote_asset": source["quote_asset"],
                "spot_venue": source["spot_venue"],
                "venue_version": source["venue_version"],
                "pool_or_market_id": source["pool_or_market_id"],
                "first_verified_spot_date": source["first_verified_spot_date"],
                "pool_age_days_as_of_2026_09_10": (AS_OF - start).days,
                "eligible_session_count_estimate_as_of_2026_09_09": int(source["eligible_session_count_estimate"]),
                "has_20_sessions": source["has_20_sessions"],
                "rolling_24h_swap_count_observed_2026_09_09": int(source["recent_swap_count_or_rate"]),
                "rolling_24h_notional_usd_observed_2026_09_09": float(source["recent_notional_if_available"]),
                "deep_overnight_continuity": overnight,
                "latest_500_block_official_rpc_swap_count": rpc_logs,
                "underlying_open_close_available": underlying_ok,
                "underlying_source": underlying_url,
                "current_multiplier_observed_2026_09_09": source["current_multiplier"],
                "historical_multiplier_risk": source["historical_multiplier_risk"],
                "corporate_action_warning": source["corporate_action_warning"],
                "measurement_complexity": labels["complexity"],
                "major_confounds": labels["confounds"],
                "overall_suitability": labels["suitability"],
            }
        )
        time.sleep(10)

    assert len(rows) == 4 and all(row["venue_version"] == "Uniswap V3" for row in rows)
    assert all(row["has_20_sessions"] == "True" and row["underlying_open_close_available"] for row in rows)
    assert all(row["latest_500_block_official_rpc_swap_count"] >= 0 for row in rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
