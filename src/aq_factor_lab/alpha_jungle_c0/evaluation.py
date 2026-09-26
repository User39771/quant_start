from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .contract import (
    MIN_DAILY_ACTIVE_CONSTITUENT_FRACTION,
    MIN_DAILY_VALID_INSTRUMENTS,
    MIN_FORMULA_SESSION_COVERAGE,
    assert_period_allowed,
)


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _assert_dates_allowed(series: pd.Series) -> None:
    if not isinstance(series.index, pd.MultiIndex) or series.index.nlevels != 2:
        raise ValueError("series requires a (date, instrument) MultiIndex")
    dates = pd.to_datetime(series.index.get_level_values(0), errors="raise")
    if len(dates):
        assert_period_allowed(dates.min().date(), dates.max().date())


def daily_coverage_required(active_n: int) -> int:
    return max(
        MIN_DAILY_VALID_INSTRUMENTS,
        math.ceil(MIN_DAILY_ACTIVE_CONSTITUENT_FRACTION * active_n),
    )


def daily_coverage_passes(active_n: int, valid_n: int) -> bool:
    return valid_n >= daily_coverage_required(active_n)


def formula_session_coverage(usable_sessions: int, eligible_sessions: int) -> tuple[float, bool]:
    if eligible_sessions <= 0:
        return 0.0, False
    ratio = usable_sessions / eligible_sessions
    return ratio, ratio >= MIN_FORMULA_SESSION_COVERAGE


@dataclass(frozen=True)
class TrainMetrics:
    mean_rank_ic: float
    rank_ir: float
    positive_ratio: float
    subperiod_direction_ratio: float
    daily_turnover: float
    max_abs_zoo_corr: float
    operator_count: int
    tree_depth: int
    parameter_count: int
    repeated_parameter_tuning: int = 0

    def scores(self) -> dict[str, float]:
        effectiveness = _clip((self.mean_rank_ic + 0.015) / 0.06)
        stability = (
            0.50 * _clip(self.rank_ir / 0.60)
            + 0.25 * _clip(self.positive_ratio)
            + 0.25 * _clip(self.subperiod_direction_ratio)
        )
        turnover = 1.0 - _clip(self.daily_turnover / 1.60)
        diversity = 1.0 - _clip(self.max_abs_zoo_corr)
        complexity_penalty = np.mean(
            [
                self.operator_count / 8,
                self.tree_depth / 5,
                self.parameter_count / 3,
                min(self.repeated_parameter_tuning, 3) / 3,
                1.0 - _clip(self.subperiod_direction_ratio),
            ]
        )
        return {
            "effectiveness": effectiveness,
            "stability": float(stability),
            "turnover": turnover,
            "diversity": diversity,
            "overfitting_risk_proxy": 1.0 - _clip(float(complexity_penalty)),
        }

    @property
    def reward(self) -> float:
        return float(np.mean(list(self.scores().values())))


def daily_rank_ic(signal: pd.Series, label: pd.Series) -> pd.Series:
    _assert_dates_allowed(signal)
    _assert_dates_allowed(label)
    frame = (
        pd.concat({"signal": signal, "label": label}, axis=1)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if not isinstance(frame.index, pd.MultiIndex) or frame.index.nlevels != 2:
        raise ValueError("signal and label require a (date, instrument) MultiIndex")
    return (
        frame.groupby(level=0)
        .apply(
            lambda x: x["signal"].corr(x["label"], method="spearman") if len(x) >= 20 else np.nan
        )
        .dropna()
    )


def rank_ic_summary(rank_ic: pd.Series, subperiods: int = 4) -> tuple[float, float, float, float]:
    if len(rank_ic) < subperiods:
        raise ValueError("insufficient RankIC observations")
    mean = float(rank_ic.mean())
    std = float(rank_ic.std(ddof=1))
    rank_ir = mean / std if std > 0 else 0.0
    positive = float((rank_ic > 0).mean())
    chunks = np.array_split(rank_ic.to_numpy(), subperiods)
    direction = float(np.mean([np.sign(np.mean(chunk)) == np.sign(mean) for chunk in chunks]))
    return mean, rank_ir, positive, direction


def top_decile_turnover(signal: pd.Series) -> float:
    _assert_dates_allowed(signal)
    weights: list[pd.Series] = []
    for _, cross_section in signal.replace([np.inf, -np.inf], np.nan).dropna().groupby(level=0):
        values = cross_section.droplevel(0).sort_values(ascending=False, kind="mergesort")
        count = max(1, int(np.ceil(len(values) * 0.10)))
        weights.append(pd.Series(1.0 / count, index=values.index[:count]))
    changes = [
        prev.subtract(cur, fill_value=0).abs().sum()
        for prev, cur in zip(weights, weights[1:], strict=False)
    ]
    return float(np.mean(changes)) if changes else 0.0
