"""Minimal v1 historical-seen expression search mechanics."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from aq_factor_lab.mcts_sandbox import Expr, _hash_rows

RAW_PRIMITIVES = ("RETURN_60", "VOL_20", "AMOUNT_MEAN_20")
PRIMITIVES = tuple(f"P_{name}" for name in RAW_PRIMITIVES)
UNARY = ("NEG", "RANK")
BINARY = ("ADD", "SUB", "MUL")
MAX_DEPTH = 4
MIN_PERIOD_COVERAGE = 0.95
MIN_STOCKS = 25
MIN_LABEL_COVERAGE = 0.80
MIN_PERIODS = 24
FAILED_TREE_REWARD = -1.0


def depth(expr: Expr) -> int:
    return 1 if len(expr) == 1 else 1 + max(depth(child) for child in expr[1:])


def formula(expr: Expr) -> str:
    return expr[0] if len(expr) == 1 else f"{expr[0]}({','.join(map(formula, expr[1:]))})"


def canonical(expr: Expr) -> str:
    """Only the preregistered small symbolic reductions."""

    op = expr[0]
    if len(expr) == 1:
        return op
    if op == "NEG" and expr[1][0] == "NEG":
        return canonical(expr[1][1])
    if op == "RANK" and expr[1][0] == "RANK":
        return canonical(expr[1])
    children = [canonical(child) for child in expr[1:]]
    if op in {"ADD", "MUL"}:
        children.sort()
    return f"{op}({','.join(children)})"


def primitive_set(expr: Expr) -> tuple[str, ...]:
    found = {expr[0]} if expr[0] in PRIMITIVES else set()
    for child in expr[1:]:
        found.update(primitive_set(child))
    return tuple(sorted(found))


def percentile_rank(values: pd.Series) -> pd.Series:
    """Average-tie percentile rank; deterministic and in (0, 1]."""

    return values.rank(method="average", pct=True)


def build_common_signal_panel(signal_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    forbidden = {"forward_return", "label_available", "evaluation_sample_member"}
    if forbidden.intersection(signal_panel.columns):
        raise ValueError("future_label_column_not_allowed_in_common_mask")
    required = {"period_index", "stock_code", "signal_sample_member", *RAW_PRIMITIVES}
    missing = required.difference(signal_panel.columns)
    if missing:
        raise ValueError(f"missing_signal_columns={sorted(missing)}")
    result = signal_panel.copy()
    target = result["signal_sample_member"].astype(bool)
    finite = np.logical_and.reduce(
        [np.isfinite(pd.to_numeric(result[name], errors="coerce")) for name in RAW_PRIMITIVES]
    )
    result["common_signal_member"] = target & finite
    rows = []
    for period, group in result.groupby("period_index", sort=True):
        target_count = int(group["signal_sample_member"].sum())
        common_count = int(group["common_signal_member"].sum())
        coverage = common_count / target_count if target_count else 0.0
        valid = coverage >= MIN_PERIOD_COVERAGE and common_count >= MIN_STOCKS
        rows.append(
            {
                "period_index": period,
                "signal_target_count": target_count,
                "common_count": common_count,
                "common_coverage": coverage,
                "period_valid": valid,
            }
        )
        result.loc[group.index, "common_period_valid"] = valid
        common_index = group.index[group["common_signal_member"]]
        for raw, normalized in zip(RAW_PRIMITIVES, PRIMITIVES, strict=True):
            result.loc[common_index, normalized] = percentile_rank(
                pd.to_numeric(result.loc[common_index, raw], errors="coerce")
            )
    result["common_period_valid"] = result["common_period_valid"].astype(bool)
    return result, pd.DataFrame(rows)


def evaluate_expression(expr: Expr, panel: pd.DataFrame) -> pd.Series:
    op = expr[0]
    if len(expr) == 1:
        if op not in PRIMITIVES:
            raise ValueError(f"invalid_primitive={op}")
        return pd.to_numeric(panel[op], errors="coerce")
    values = [evaluate_expression(child, panel) for child in expr[1:]]
    if op == "NEG":
        result = -values[0]
    elif op == "RANK":
        result = values[0].groupby(panel["period_index"]).rank(method="average", pct=True)
    elif op == "ADD":
        result = values[0] + values[1]
    elif op == "SUB":
        result = values[0] - values[1]
    elif op == "MUL":
        result = values[0] * values[1]
    else:
        raise ValueError(f"invalid_operator={op}")
    return result.where(np.isfinite(result))


def _period_slices(panel: pd.DataFrame) -> list[slice]:
    counts = panel.groupby("period_index", sort=False).size().to_numpy()
    ends = np.cumsum(counts)
    return [slice(start, end) for start, end in zip(np.r_[0, ends[:-1]], ends, strict=True)]


def evaluate_array(expr: Expr, panel: pd.DataFrame, periods: list[slice]) -> np.ndarray:
    """NumPy equivalent of expression evaluation on the sorted common panel."""

    op = expr[0]
    if len(expr) == 1:
        return panel[op].to_numpy(dtype=float, copy=False)
    values = [evaluate_array(child, panel, periods) for child in expr[1:]]
    if op == "NEG":
        return -values[0]
    if op == "RANK":
        result = np.empty(len(panel), dtype=float)
        for period in periods:
            result[period] = rankdata(values[0][period], method="average") / len(values[0][period])
        return result
    if op == "ADD":
        return values[0] + values[1]
    if op == "SUB":
        return values[0] - values[1]
    if op == "MUL":
        return values[0] * values[1]
    raise ValueError(f"invalid_operator={op}")


def signal_identity(expr: Expr, panel: pd.DataFrame) -> dict[str, object]:
    """Build the signal-only rank identity before any label evaluation."""

    mask = panel["common_period_valid"] & panel["common_signal_member"]
    signal_panel = panel.loc[mask].sort_values(["period_index", "stock_code"])
    periods = _period_slices(signal_panel)
    signal = evaluate_array(expr, signal_panel, periods)
    if not np.isfinite(signal).all():
        return {"valid": False, "failure_reason": "invalid_signal"}
    ranks = np.empty(len(signal), dtype=float)
    for period in periods:
        ranks[period] = rankdata(signal[period], method="average")
        if np.unique(ranks[period]).size < 2:
            return {"valid": False, "failure_reason": "constant_signal"}
    rank_hash = hashlib.sha256(np.asarray(ranks, dtype="<f8").tobytes()).hexdigest()
    return {
        "valid": True,
        "failure_reason": "",
        "signal_rank_signature": rank_hash,
        "_ranks": ranks,
        "_period_slices": periods,
        "_signal_panel": signal_panel,
    }


def q5_signature(identity: dict[str, object]) -> str:
    """Signal-derived Q5 identity, calculated once per new rank class."""

    selected_rows = []
    panel = identity["_signal_panel"]
    ranks = identity["_ranks"]
    for period in identity["_period_slices"]:
        count = period.stop - period.start
        q5_size = len(np.array_split(np.arange(count), 5)[0])
        local = np.lexsort((panel["stock_code"].iloc[period].to_numpy(), -ranks[period]))
        codes = panel["stock_code"].iloc[period].to_numpy()[local[:q5_size]]
        period_index = panel["period_index"].iloc[period.start]
        selected_rows.append(f"{period_index}|{','.join(sorted(codes))}")
    return _hash_rows(selected_rows)


def reward_from_identity(identity: dict[str, object]) -> dict[str, object]:
    """Evaluate labels only after the signal-only rank signature is known to be new."""

    panel = identity["_signal_panel"]
    ranks = identity["_ranks"]
    rankics = []
    for period in identity["_period_slices"]:
        labels = panel["forward_return"].iloc[period].to_numpy(dtype=float)
        finite = np.isfinite(labels)
        if finite.sum() < MIN_STOCKS or finite.mean() < MIN_LABEL_COVERAGE:
            continue
        label_ranks = rankdata(labels[finite], method="average")
        rho = np.corrcoef(ranks[period][finite], label_ranks)[0, 1]
        if np.isfinite(rho):
            rankics.append(float(rho))
    if len(rankics) < MIN_PERIODS:
        return {"evaluation_status": "failed", "failure_reason": "insufficient_valid_periods"}
    values = np.asarray(rankics)
    return {
        "evaluation_status": "ok",
        "failure_reason": "",
        "reward": float(values.mean()),
        "mean_rankic": float(values.mean()),
        "median_rankic": float(np.median(values)),
        "positive_rankic_ratio": float((values > 0).mean()),
        "valid_periods": len(values),
    }


def evaluate_reward(expr: Expr, panel: pd.DataFrame) -> dict[str, object]:
    signal = evaluate_expression(expr, panel)
    rankics = []
    for _, group in panel.assign(_signal=signal).groupby("period_index", sort=True):
        target = group.loc[group["common_period_valid"] & group["common_signal_member"]]
        valid = target.loc[np.isfinite(target["forward_return"])]
        coverage = len(valid) / len(target) if len(target) else 0.0
        if len(valid) < MIN_STOCKS or coverage < MIN_LABEL_COVERAGE:
            continue
        rho = valid["_signal"].corr(valid["forward_return"], method="spearman")
        if np.isfinite(rho):
            rankics.append(float(rho))
    if len(rankics) < MIN_PERIODS:
        return {"evaluation_status": "failed", "failure_reason": "insufficient_valid_periods"}
    values = np.asarray(rankics)
    return {
        "evaluation_status": "ok",
        "failure_reason": "",
        "reward": float(values.mean()),
        "mean_rankic": float(values.mean()),
        "median_rankic": float(np.median(values)),
        "positive_rankic_ratio": float((values > 0).mean()),
        "valid_periods": len(values),
    }


def random_expression(rng: random.Random, current: int = 1) -> Expr:
    if current >= MAX_DEPTH or rng.random() < 0.28:
        return (rng.choice(PRIMITIVES),)
    if rng.random() < 0.35:
        return (rng.choice(UNARY), random_expression(rng, current + 1))
    return (
        rng.choice(BINARY),
        random_expression(rng, current + 1),
        random_expression(rng, current + 1),
    )


def _leaf_paths(expr: Expr, path: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
    if len(expr) == 1:
        return [path]
    return [p for i, child in enumerate(expr[1:], 1) for p in _leaf_paths(child, path + (i,))]


def _replace(expr: Expr, path: tuple[int, ...], replacement: Expr) -> Expr:
    if not path:
        return replacement
    parts = list(expr)
    parts[path[0]] = _replace(parts[path[0]], path[1:], replacement)
    return tuple(parts)


def expansions(expr: Expr, rng: random.Random) -> list[Expr]:
    candidates = []
    for path in _leaf_paths(expr):
        for op in UNARY:
            for primitive in PRIMITIVES:
                candidates.append(_replace(expr, path, (op, (primitive,))))
        for op in BINARY:
            for left in PRIMITIVES:
                for right in PRIMITIVES:
                    candidates.append(_replace(expr, path, (op, (left,), (right,))))
    candidates = [item for item in candidates if depth(item) <= MAX_DEPTH]
    rng.shuffle(candidates)
    return candidates


@dataclass
class Node:
    expr: Expr | None
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    untried: list[Expr] | None = None
    visits: int = 0
    value: float = 0.0

    def choices(self, rng: random.Random) -> list[Expr]:
        if self.untried is None:
            self.untried = (
                [(primitive,) for primitive in PRIMITIVES]
                if self.expr is None
                else expansions(self.expr, rng)
            )
        return self.untried


def mcts_proposal(root: Node, rng: random.Random) -> Node:
    node = root
    while not node.choices(rng) and node.children:
        log_parent = math.log(max(node.visits, 1))
        node = max(
            node.children,
            key=lambda child: (
                child.value / child.visits + math.sqrt(2) * math.sqrt(log_parent / child.visits)
            ),
        )
    if node.choices(rng):
        node = Node(node.choices(rng).pop(), parent=node)
        node.parent.children.append(node)
    return node


def backpropagate(node: Node, reward: float) -> None:
    while node:
        node.visits += 1
        node.value += reward
        node = node.parent


def stable_hash(frame: pd.DataFrame, columns: list[str]) -> str:
    values = frame[columns].astype(str).agg("|".join, axis=1)
    return hashlib.sha256("\n".join(values).encode()).hexdigest()
