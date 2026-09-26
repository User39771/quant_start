from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import C0


def _hash_frame(series: pd.Series) -> str:
    hashed = pd.util.hash_pandas_object(series.sort_index(), index=True).values.tobytes()
    return hashlib.sha256(hashed).hexdigest()


def exact_signal_fingerprint(signal: pd.Series) -> str:
    return _hash_frame(signal.astype(float))


def rank_signal_fingerprint(signal: pd.Series) -> str:
    if not isinstance(signal.index, pd.MultiIndex):
        raise ValueError("rank fingerprint requires MultiIndex")
    ranks = signal.groupby(level=0).rank(method="average", pct=True)
    return _hash_frame(ranks.round(12))


def portfolio_ordering_fingerprint(signal: pd.Series) -> str:
    if not isinstance(signal.index, pd.MultiIndex):
        raise ValueError("portfolio fingerprint requires MultiIndex")
    ordered = signal.groupby(level=0, group_keys=False).apply(
        lambda x: pd.Series(np.arange(len(x)), index=x.sort_values(kind="mergesort").index)
    )
    return _hash_frame(ordered.sort_index())


def _assert_train_only(signal: pd.Series) -> None:
    if not isinstance(signal.index, pd.MultiIndex) or signal.index.nlevels != 2:
        raise ValueError("Alpha Zoo signal requires a (date, instrument) MultiIndex")
    dates = pd.to_datetime(signal.index.get_level_values(0), errors="raise")
    if len(dates) and (dates.min().date() < C0.train_start or dates.max().date() > C0.train_end):
        raise ValueError("Alpha Zoo accepts TRAIN_SEARCH dates only")


@dataclass
class AlphaZoo:
    canonical_formulas: set[str] = field(default_factory=set)
    exact_signals: set[str] = field(default_factory=set)
    rank_signals: set[str] = field(default_factory=set)
    portfolio_orderings: set[str] = field(default_factory=set)
    train_signals: list[pd.Series] = field(default_factory=list)
    formula_string_count: int = 0

    def max_abs_correlation(self, signal: pd.Series) -> float:
        _assert_train_only(signal)
        correlations = [abs(float(signal.corr(other))) for other in self.train_signals]
        finite = [value for value in correlations if np.isfinite(value)]
        return max(finite, default=0.0)

    def add(self, formula_string: str, canonical: str, signal: pd.Series) -> None:
        _assert_train_only(signal)
        self.formula_string_count += 1
        self.canonical_formulas.add(canonical)
        self.exact_signals.add(exact_signal_fingerprint(signal))
        self.rank_signals.add(rank_signal_fingerprint(signal))
        self.portfolio_orderings.add(portfolio_ordering_fingerprint(signal))
        self.train_signals.append(signal.copy())

    def counts(self) -> dict[str, int]:
        return {
            "formula_string_count": self.formula_string_count,
            "canonical_formula_count": len(self.canonical_formulas),
            "unique_exact_signal_count": len(self.exact_signals),
            "unique_rank_signal_count": len(self.rank_signals),
            "unique_portfolio_ordering_count": len(self.portfolio_orderings),
        }
