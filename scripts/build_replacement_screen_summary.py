"""Build the combined AMZN + UPS replacement-screen summary artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")


def is_primary(classification: str) -> bool:
    return classification.endswith("_PRIMARY_USABLE") or classification.endswith(
        "_PRIMARY_USABLE_WITH_MATURATION_START"
    )


def load_audit(symbol: str) -> dict:
    path = ROOT / f"{symbol.lower()}_early_late_feasibility_audit.json"
    return json.loads(path.read_text(encoding="utf-8"))


def summary_row(audit: dict) -> dict:
    combined = audit["combined"]
    return {
        "token_symbol": audit["token_symbol"],
        "early_dates": audit["early_dates"],
        "late_dates": audit["late_dates"],
        "early_deep_availability": audit["early"]["return_available"]["deep"],
        "late_deep_availability": audit["late"]["return_available"]["deep"],
        "combined_deep_availability": audit["combined"]["return_available"]["deep"],
        "observability_pattern": audit["observability_pattern"],
        "eligibility_start_assessment": audit["eligibility_start_assessment"],
        "final_one_time_classification": audit["final_one_time_classification"],
        "technical_quality": audit["technical_quality"],
        "early": audit["early"],
        "late": audit["late"],
        "combined": combined,
    }


def build_summary() -> dict:
    amzn = load_audit("AMZN")
    ups = load_audit("UPS")
    amzn_primary = is_primary(amzn["final_one_time_classification"])
    ups_primary = is_primary(ups["final_one_time_classification"])

    if amzn_primary and ups_primary:
        decision = "CASE_A_BOTH_PRIMARY"
        recommendation = (
            "Recommend full-history collection for both AMZN and UPS "
            "(pending human/Sol approval)."
        )
    elif amzn_primary or ups_primary:
        decision = "CASE_B_ONE_PRIMARY"
        passing = "AMZN" if amzn_primary else "UPS"
        recommendation = (
            f"Recommend full-history collection only for {passing} "
            "(pending human/Sol approval). Report whether primary breadth "
            "still appears insufficient."
        )
    else:
        decision = "CASE_C_NEITHER_PRIMARY"
        recommendation = (
            "Do not automatically search another token. Recommend a bounded "
            "second-wave replacement-candidate search for human/Sol review."
        )

    return {
        "screen_design": "FROZEN_EARLY_5_PLUS_LATE_5_PER_CANDIDATE",
        "cutoff_date": "2026-09-04",
        "candidates": {
            "AMZN": summary_row(amzn),
            "UPS": summary_row(ups),
        },
        "combined_replacement_decision": decision,
        "recommendation": recommendation,
        "next_action_scope": (
            "No full-history collection is authorized in this screen. "
            "Full-history collection remains recommended/pending approval."
        ),
    }


def render_markdown(summary: dict) -> str:
    lines = ["# AMZN + UPS replacement feasibility screen"]
    lines.append("")
    lines.append(
        "This is a bounded measurement-feasibility screen using the frozen five-minute "
        "executed-trade VWAP contract. No predictive or profitability analysis is performed."
    )
    lines.append("")
    lines.append("## Candidate results")
    lines.append("")
    for symbol in ("AMZN", "UPS"):
        row = summary["candidates"][symbol]
        lines.append(f"### {symbol}")
        lines.append("")
        lines.append(f"- Early deep availability: {row['early_deep_availability']}/5.")
        lines.append(f"- Late deep availability: {row['late_deep_availability']}/5.")
        lines.append(f"- Combined deep availability: {row['combined_deep_availability']}/10.")
        lines.append(f"- Observability pattern: {row['observability_pattern']}.")
        lines.append(f"- Eligibility assessment: {row['eligibility_start_assessment']}.")
        lines.append(f"- Final classification: **{row['final_one_time_classification']}**.")
        lines.append("")
    lines.append("## Combined replacement decision")
    lines.append("")
    lines.append(f"**{summary['combined_replacement_decision']}**")
    lines.append("")
    lines.append(summary["recommendation"])
    lines.append("")
    lines.append(summary["next_action_scope"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    summary = build_summary()
    json_path = ROOT / "replacement_screen_amzn_ups_summary.json"
    md_path = ROOT / "replacement_screen_amzn_ups_summary.md"
    json_path.write_text(
        json.dumps(summary, indent=2, allow_nan=False, default=str), encoding="utf-8"
    )
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(
        {
            "amzn_classification": summary["candidates"]["AMZN"]["final_one_time_classification"],
            "ups_classification": summary["candidates"]["UPS"]["final_one_time_classification"],
            "combined_replacement_decision": summary["combined_replacement_decision"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
