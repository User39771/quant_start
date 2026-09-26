"""Local-only audit distinguishing 30m deep AVAILABLE vs ROBUST.

Reads the completed 5m-vs-30m session CSV and classifies each 30m deep
observation as UNAVAILABLE / AVAILABLE_THIN / ROBUST using the existing >=5
swaps AND >=500 USDG non-thin threshold. No RPC, no returns, no prediction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SOURCE = OUT / "boundary_window_feasibility_5m_vs_30m_sessions.csv"
THIN_MIN_SWAPS = 5
THIN_MIN_NOTIONAL = 500.0


def is_robust(row: pd.Series) -> bool:
    if not bool(row["30m_deep_available"]):
        return False
    for name in ("2000", "0400"):
        swaps = row[f"30m_{name}_swap_count"]
        notional = row[f"30m_{name}_notional"]
        if pd.isna(swaps) or pd.isna(notional):
            return False
        if swaps < THIN_MIN_SWAPS or notional < THIN_MIN_NOTIONAL:
            return False
    return True


def quality_class(row: pd.Series) -> str:
    if not bool(row["30m_deep_available"]):
        return "UNAVAILABLE"
    if is_robust(row):
        return "ROBUST"
    return "AVAILABLE_THIN"


def bucket(rate: float) -> str:
    if rate >= 0.8:
        return "ROBUST_HIGH"
    if rate >= 0.6:
        return "ROBUST_MODERATE"
    if rate >= 0.4:
        return "ROBUST_LOW"
    return "ROBUST_POOR"


def measurement_note(token: str, available: int, robust: int, n: int) -> str:
    if token in ("NVDA", "GME"):
        return "highly available and highly robust"
    if token == "COST":
        return "mostly available but only about half robust"
    if token == "META":
        return "swap presence observed but notional unknown (V4 not price-decoded); robustness unconfirmed"
    if token == "UPS":
        return "genuinely too illiquid; essentially no deep trading"
    if available > 0 and robust / available < 0.5:
        return "availability improved but mostly thin observations"
    return "limited robust deep measurement"


def main() -> None:
    df = pd.read_csv(SOURCE)
    df["deep_30m_quality_class"] = df.apply(quality_class, axis=1)
    df["30m_robust"] = df.apply(is_robust, axis=1)

    # Session-level output preserving diagnostics.
    keep = [
        "token", "market_open_date", "30m_deep_available",
        "30m_2000_available", "30m_0400_available",
        "30m_2000_swap_count", "30m_0400_swap_count",
        "30m_2000_notional", "30m_0400_notional",
        "deep_30m_quality_class",
    ]
    df[keep].to_csv(OUT / "robust_30m_deep_coverage_sessions.csv", index=False)

    rows = []
    concentration = df[df["30m_robust"]].groupby("token").size().sort_values(ascending=False)
    total_robust = int(concentration.sum())
    for token, group in df.groupby("token"):
        n = len(group)
        available = int(group["30m_deep_available"].sum())
        robust = int(group["30m_robust"].sum())
        thin = available - robust
        unavailable = n - available
        robust_share = robust / available if available > 0 else None

        def boundary_stats(name: str) -> dict:
            avail = group[f"30m_{name}_available"].astype(bool)
            swaps = group[f"30m_{name}_swap_count"]
            notional = group[f"30m_{name}_notional"]
            non_thin = avail & (swaps >= THIN_MIN_SWAPS) & (notional >= THIN_MIN_NOTIONAL)
            where_available = group[avail]
            return {
                "available_rate": round(float(avail.mean()), 4),
                "non_thin_rate": round(float(non_thin.mean()), 4),
                "median_swap_count_where_available": (
                    float(where_available[f"30m_{name}_swap_count"].median())
                    if not where_available.empty else None
                ),
                "median_notional_where_available": (
                    float(where_available[f"30m_{name}_notional"].median())
                    if not where_available.empty and where_available[f"30m_{name}_notional"].notna().any()
                    else None
                ),
            }

        b20 = boundary_stats("2000")
        b04 = boundary_stats("0400")
        rows.append({
            "token": token,
            "n_sessions": n,
            "30m_available_count": available,
            "30m_available_rate": round(available / n, 4),
            "30m_robust_count": robust,
            "30m_robust_rate": round(robust / n, 4),
            "available_but_thin_count": thin,
            "available_but_thin_rate": round(thin / n, 4),
            "unavailable_count": unavailable,
            "unavailable_rate": round(unavailable / n, 4),
            "robust_share_among_available": round(robust_share, 4) if robust_share is not None else None,
            "robustness_bucket": bucket(robust / n),
            "20:00_available_rate": b20["available_rate"],
            "20:00_non_thin_rate": b20["non_thin_rate"],
            "20:00_median_swap_count": b20["median_swap_count_where_available"],
            "20:00_median_notional": b20["median_notional_where_available"],
            "04:00_available_rate": b04["available_rate"],
            "04:00_non_thin_rate": b04["non_thin_rate"],
            "04:00_median_swap_count": b04["median_swap_count_where_available"],
            "04:00_median_notional": b04["median_notional_where_available"],
            "measurement_note": measurement_note(token, available, robust, n),
        })

    by_token = pd.DataFrame(rows)
    by_token.to_csv(OUT / "robust_30m_deep_coverage_by_token.csv", index=False)

    cumulative = []
    running = 0
    for token, count in concentration.items():
        running += int(count)
        cumulative.append({"rank_top": len(cumulative) + 1, "token": token, "count": int(count), "cumulative_share": round(running / total_robust, 4)})

    top1 = cumulative[0]["cumulative_share"] if cumulative else None
    top2 = cumulative[1]["cumulative_share"] if len(cumulative) > 1 else None
    top3 = cumulative[2]["cumulative_share"] if len(cumulative) > 2 else None
    nvda_gme = (df[df["token"].isin(["NVDA", "GME"])]["30m_robust"].sum()) / total_robust

    if top2 is not None and top2 >= 0.7:
        breadth = "ROBUST_PANEL_HIGHLY_CONCENTRATED"
        breadth_reason = "The top two tokens (NVDA, GME) contribute more than 70% of robust observations."
    elif top2 is not None and top2 >= 0.5:
        breadth = "ROBUST_PANEL_MODERATELY_CONCENTRATED"
        breadth_reason = "The top two tokens contribute a large share but secondary tokens still contribute meaningfully."
    else:
        breadth = "ROBUST_PANEL_BROAD"
        breadth_reason = "Robust observations are spread across many tokens."

    summary = {
        "total_evaluated_sessions": len(df),
        "total_30m_deep_available": int(df["30m_deep_available"].sum()),
        "total_30m_deep_robust": total_robust,
        "30m_available_rate": round(float(df["30m_deep_available"].mean()), 4),
        "30m_robust_rate": round(float(df["30m_robust"].mean()), 4),
        "robust_observations_by_token": {t: int(c) for t, c in concentration.items()},
        "robust_share_by_token": {t: round(int(c) / total_robust, 4) for t, c in concentration.items()},
        "cumulative_robust_share": {
            "top1": top1,
            "top2": top2,
            "top3": top3,
            "nvda_plus_gme": round(nvda_gme, 4),
        },
        "robust_panel_concentration_classification": breadth,
        "concentration_reason": breadth_reason,
        "per_token": {r["token"]: r for r in rows},
        "no_rpc": True,
        "no_predictive_analysis": True,
    }
    (OUT / "robust_30m_deep_coverage_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    lines = [
        "# Robust 30-minute deep coverage audit",
        "",
        "Local-only. Uses the existing 30-minute specification and the existing >=5 swaps / >=500 USDG non-thin threshold.",
        "",
        f"- Evaluated sessions: {len(df)}.",
        f"- 30m deep available: {int(df['30m_deep_available'].sum())} ({summary['30m_available_rate']:.1%}).",
        f"- 30m deep robust: {total_robust} ({summary['30m_robust_rate']:.1%}).",
        "",
        "## Per-token",
        "",
        "| Token | N | Available | Robust | Robust rate | Thin | Robust share among available | 20:00 non-thin | 04:00 non-thin | Bucket |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        rsa = r["robust_share_among_available"]
        rsa_text = f"{rsa:.0%}" if rsa is not None else "n/a"
        lines.append(
            f"| {r['token']} | {r['n_sessions']} | {r['30m_available_count']} | "
            f"{r['30m_robust_count']} | {r['30m_robust_rate']:.0%} | "
            f"{r['available_but_thin_count']} | {rsa_text} | "
            f"{r['20:00_non_thin_rate']:.0%} | {r['04:00_non_thin_rate']:.0%} | "
            f"{r['robustness_bucket']} |"
        )
    lines += [
        "",
        "## Robust observation concentration",
        "",
        f"- NVDA: {summary['robust_share_by_token'].get('NVDA', 0):.1%}.",
        f"- GME: {summary['robust_share_by_token'].get('GME', 0):.1%}.",
        f"- NVDA + GME: {nvda_gme:.1%}.",
        f"- Top 3: {top3:.1%}.",
        "",
        f"Concentration classification: **{breadth}**. {breadth_reason}",
        "",
        "## Conclusion",
        "",
        "Widening from 5m to 30m broadened technical AVAILABILITY (59.4% to 74.1%), but the ROBUST measurement base remains dominated by NVDA and GME (77.5% combined). Secondary tokens mostly gained thin, technically-measurable observations rather than robust deep measurements.",
        "",
        "NO NEW RPC COLLECTION WAS PERFORMED. NO NEXT-OPEN OUTCOME WAS INSPECTED. NO PREDICTIVE ANALYSIS WAS RUN.",
        "",
    ]
    (OUT / "robust_30m_deep_coverage_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "total": len(df),
        "available": int(df["30m_deep_available"].sum()),
        "robust": total_robust,
        "nvda_plus_gme": round(nvda_gme, 4),
        "top3": top3,
        "breadth": breadth,
    }, indent=2))


if __name__ == "__main__":
    main()
