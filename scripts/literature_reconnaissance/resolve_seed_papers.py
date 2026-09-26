"""Resolve a curated, project-relevant seed list against OpenAlex metadata."""

from __future__ import annotations

import csv
import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SEEDS = {
    "A": [
        "Risk, Return, and Equilibrium: Empirical Tests",
        "The Cross-Section of Expected Stock Returns",
        "Common risk factors in the returns on stocks and bonds",
        "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
        "Does the Stock Market Overreact?",
        "Evidence of Predictable Behavior of Security Returns",
        "What Has Worked in Investing",
        "Illiquidity and stock returns: cross-section and time-series effects",
        "Gross Profitability Premium",
        "Betting Against Beta",
        "Value and Momentum Everywhere",
        "Digesting Anomalies: An Investment Approach",
        "Replicating Anomalies",
        "Empirical Asset Pricing via Machine Learning",
        "Characteristics are covariances: A unified model of risk and return",
        "What Characteristics Provide Independent Information About Average U.S. Stock Returns?",
        "A Taxonomy of Anomalies and Their Trading Costs",
        "Does Academic Research Destroy Stock Return Predictability?",
    ],
    "B": [
        "A Reality Check for Data Snooping",
        "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap",
        "A Test for Superior Predictive Ability",
        "The Probability of Backtest Overfitting",
        "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality",
        "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance",
        "… and the Cross-Section of Expected Returns",
        "Lucky Factors",
        "Why Most Published Research Findings Are False",
        "The Statistics of Sharpe Ratios",
        "Taming the Factor Zoo: A Test of New Factors",
        "An Anatomy of Trading Strategies",
        "Open Source Cross-Sectional Asset Pricing",
        "Firm Characteristics and Expected Returns: A Model-Agnostic Approach",
        "Cross-Validation Pitfalls When Selecting and Assessing Regression and Classification Models",
        "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing",
        "The False Strategy Theorem: A Financial Application of Algorithmic Complexity Theory",
    ],
    "C": [
        "Distilling Free-Form Natural Laws from Experimental Data",
        "Deep symbolic regression: Recovering mathematical expressions from data via risk-seeking policy gradients",
        "A Unified Framework for Deep Symbolic Regression",
        "AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment",
        "AlphaEvolve: A Learning Framework to Discover Novel Alphas in Quantitative Investment",
        "Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning",
        "RiskMiner: Discovering Formulaic Alphas via Risk Seeking Monte Carlo Tree Search",
        "AlphaForge: A Framework to Mine and Dynamically Combine Formulaic Alpha Factors",
        "Alpha-GPT: Human-AI Interactive Alpha Mining for Quantitative Investment",
        "Can Large Language Models Mine Interpretable Financial Factors More Effectively? A Neural-Symbolic Factor Mining Agent Model",
        "AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay",
        "Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining",
        "Qlib: An AI-oriented Quantitative Investment Platform",
        "OpenFE: automated feature generation with expert-level performance",
        "FactorVAE: A Probabilistic Dynamic Factor Model Based on Variational Autoencoder for Predicting Cross-Sectional Stock Returns",
    ],
    "D": [
        "Continuous Auctions and Insider Trading",
        "Bid, Ask and Transaction Prices in a Specialist Market with Heterogeneously Informed Traders",
        "Price and Trade Size Anonymity and the Incorporation of Information into Security Prices",
        "A Theory of Intraday Patterns: Volume and Price Variability",
        "A Theory of Trading Volume",
        "The Relation between Price Changes and Trading Volume: A Survey",
        "Trading Volume and Serial Correlation in Stock Returns",
        "Trading Volume and Cross-Autocorrelations in Stock Returns",
        "Price Momentum and Trading Volume",
        "The High-Volume Return Premium",
        "Dynamic Volume-Return Relation of Individual Stocks",
        "Risk, Uncertainty, and Divergence of Opinion",
        "A Unified Theory of Underreaction, Momentum Trading, and Overreaction in Asset Markets",
        "All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors",
        "In Search of Attention",
        "Illiquidity and stock returns: cross-section and time-series effects",
        "Liquidity Risk and Expected Stock Returns",
        "Volume and Autocovariances in Short-Horizon Individual Security Returns",
        "Market Statistics and Technical Analysis: The Role of Volume",
    ],
    "E": [
        "Event Studies in Economics and Finance",
        "Using Daily Stock Returns: The Case of Event Studies",
        "The Adjustment of Stock Prices to New Information",
        "Detecting Long-Run Abnormal Stock Returns: The Empirical Power and Specification of Test Statistics",
        "The Econometrics of Event Studies",
        "The Event Study Methodology Since 1969",
        "Style Investing",
        "Investor Attention, Overconfidence and Category Learning",
        "Allocating to Thematic Investments",
        "Thematic Investing: A Risk-Based Perspective",
        "Joint News, Attention Spillover, and Stock Returns",
    ],
    "F": [
        "The Chinese Capital Market: An Empirical Overview",
        "Predictable Behavior, Profits, and Attention",
        "A Unique T+1 Trading Rule in China: Theory and Evidence",
        "Does the T+1 Rule Really Reduce Speculation? Evidence from Chinese Stock Index ETF",
        "T+1 Trading Mechanism Causes Negative Overnight Return",
        "Should Earnings Thresholds Be Used as Delisting Criteria in Stock Market?",
        "Statistical Properties and Pre-Hit Dynamics of Price Limit Hits in the Chinese Stock Markets",
        "How Price Limit Affects the Market Efficiency in a Short-Sale Constrained Market? Evidence from a Quasi-Natural Experiment",
        "Limits of Arbitrage and Idiosyncratic Volatility: Evidence from China Stock Market",
        "Survivorship Bias in Performance Studies",
        "Survivor Bias and Mutual Fund Performance",
        "The Effect of Suspensions on Liquidity of the Chinese Stock Market",
    ],
}

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "literature_reconnaissance" / "raw_metadata"


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "quant-start-literature-recon/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    return json.loads(value) if isinstance(value, str) else value


def main() -> None:
    rows: list[dict] = []
    for cluster, titles in SEEDS.items():
        for title in titles:
            params = urllib.parse.urlencode({"search": title, "per-page": 5})
            try:
                payload = get_json(f"https://api.openalex.org/works?{params}")
            except urllib.error.HTTPError as error:
                print(f"skip http={error.code} title={title}")
                payload = {"results": []}
            matches = payload.get("results", [])
            match = max(
                matches,
                key=lambda work: difflib.SequenceMatcher(
                    None, normalize(title), normalize(work["title"])
                ).ratio(),
                default=None,
            )
            ratio = (
                difflib.SequenceMatcher(
                    None, normalize(title), normalize(match["title"])
                ).ratio()
                if match
                else 0
            )
            location = (match or {}).get("primary_location") or {}
            source = location.get("source") or {}
            rows.append(
                {
                    "cluster": cluster,
                    "seed_title": title,
                    "match_score": f"{ratio:.3f}",
                    "openalex_id": (match or {}).get("id", ""),
                    "doi": (match or {}).get("doi", ""),
                    "title": (match or {}).get("title", ""),
                    "authors": "; ".join(
                        item["author"]["display_name"]
                        for item in (match or {}).get("authorships", [])
                    ),
                    "year": (match or {}).get("publication_year", ""),
                    "venue": source.get("display_name", ""),
                    "type": (match or {}).get("type", ""),
                    "cited_by_count": (match or {}).get("cited_by_count", 0),
                    "is_oa": ((match or {}).get("open_access") or {}).get(
                        "is_oa", False
                    ),
                    "landing_page_url": location.get("landing_page_url", ""),
                    "abstract_available": bool(
                        (match or {}).get("abstract_inverted_index")
                    ),
                }
            )
            time.sleep(0.1)

    output = OUT / "resolved_seed_papers.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    low = sum(float(row["match_score"]) < 0.9 for row in rows)
    print(f"seeds={len(rows)} low_confidence_matches={low}")


if __name__ == "__main__":
    main()
