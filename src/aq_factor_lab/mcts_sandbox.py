"""Minimal historical-seen expression search sandbox; not an Alpha research platform."""

from __future__ import annotations

import ast
import hashlib
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PRIMITIVES = ("RETURN_60", "VOL_20", "AMOUNT_MEAN_20")
UNARY = ("NEG", "RANK")
BINARY = ("ADD", "SUB", "MUL")
MAX_DEPTH = 4
MIN_STOCKS = 25
MIN_COVERAGE = 0.80
MIN_PERIODS = 24
FAILED_TREE_REWARD = -1.0

Expr = tuple


def parse_formula(text: str) -> Expr:
    """Parse a deliberately tiny, safe expression language."""

    aliases = {"MOM60": "RETURN_60", "REV60": "NEG(RETURN_60)"}
    text = aliases.get(text.strip(), text.strip()).replace("-MOM60", "NEG(RETURN_60)")
    node = ast.parse(text, mode="eval").body

    def convert(item: ast.AST) -> Expr:
        if isinstance(item, ast.Name):
            if item.id in PRIMITIVES:
                return (item.id,)
            if item.id == "MOM60":
                return ("RETURN_60",)
            if item.id == "REV60":
                return ("NEG", ("RETURN_60",))
        if isinstance(item, ast.Constant) and item.value == 2:
            return ("CONST", 2.0)
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, ast.USub):
            return ("NEG", convert(item.operand))
        if isinstance(item, ast.BinOp):
            op = {ast.Add: "ADD", ast.Sub: "SUB", ast.Mult: "MUL"}.get(type(item.op))
            if op:
                return (op, convert(item.left), convert(item.right))
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
            op = item.func.id.upper()
            if op in UNARY and len(item.args) == 1:
                return (op, convert(item.args[0]))
            if op in BINARY and len(item.args) == 2:
                return (op, convert(item.args[0]), convert(item.args[1]))
        raise ValueError(f"invalid_formula={text}")

    expression = convert(node)
    if depth(expression) > MAX_DEPTH:
        raise ValueError("expression_depth_exceeds_4")
    return expression


def depth(expr: Expr) -> int:
    if expr[0] == "CONST" or len(expr) == 1:
        return 1
    return 1 + max(depth(child) for child in expr[1:])


def formula(expr: Expr) -> str:
    if expr[0] == "CONST":
        return "2"
    if len(expr) == 1:
        return expr[0]
    return f"{expr[0]}({','.join(formula(child) for child in expr[1:])})"


def canonical(expr: Expr) -> str:
    """Small algebraic normalization; rank/portfolio hashes handle the rest."""

    op = expr[0]
    if op == "CONST":
        return "2"
    if len(expr) == 1:
        return op
    children = [canonical(child) for child in expr[1:]]
    if op == "NEG" and expr[1][0] == "NEG":
        return canonical(expr[1][1])
    if op == "MUL":
        nonconstants = [child for child in expr[1:] if child[0] != "CONST"]
        constants = [child for child in expr[1:] if child[0] == "CONST"]
        if len(nonconstants) == 1 and constants and all(child[1] > 0 for child in constants):
            return canonical(nonconstants[0])
    if op in {"ADD", "MUL"}:
        children.sort()
    return f"{op}({','.join(children)})"


def primitive_set(expr: Expr) -> tuple[str, ...]:
    found = {expr[0]} if expr[0] in PRIMITIVES else set()
    for child in expr[1:]:
        if isinstance(child, tuple):
            found.update(primitive_set(child))
    return tuple(sorted(found))


def evaluate_expression(expr: Expr, panel: pd.DataFrame) -> pd.Series:
    op = expr[0]
    if op == "CONST":
        return pd.Series(float(expr[1]), index=panel.index)
    if len(expr) == 1:
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
    else:  # pragma: no cover - parser prevents this
        raise ValueError(f"unknown_operator={op}")
    return result.where(np.isfinite(result))


def _hash_rows(rows: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def quantile_members(target: pd.DataFrame, signal_column: str) -> dict[int, pd.Index]:
    """Match Phase A oriented grouping: highest scores enter Q5, including split remainder."""

    ordered = target.sort_values([signal_column, "stock_code"], ascending=[False, True])
    chunks = np.array_split(ordered.index.to_numpy(), 5)
    return {5 - index: pd.Index(chunk) for index, chunk in enumerate(chunks)}


def score_candidate(expr: Expr, panel: pd.DataFrame) -> dict[str, object]:
    signal = evaluate_expression(expr, panel)
    if not np.isfinite(signal).any():
        return _failure("non_finite_signal")
    # A signal-time missing value fails the candidate; labels may never redefine its universe.
    signal_members = panel["signal_sample_member"]
    if not np.isfinite(signal.loc[signal_members]).all():
        return _failure("non_finite_signal_on_frozen_target")
    rank_rows: list[str] = []
    signal_rows: list[str] = []
    portfolio_rows: list[str] = []
    rankics: list[float] = []
    invalid_periods = 0
    for period, group in panel.assign(_signal=signal).groupby("period_index", sort=True):
        target = group.loc[group["signal_sample_member"] & np.isfinite(group["_signal"])]
        valid = target.loc[np.isfinite(target["forward_return"])]
        coverage = len(valid) / len(target) if len(target) else 0.0
        if len(valid) < MIN_STOCKS or coverage < MIN_COVERAGE:
            invalid_periods += 1
            continue
        if valid["_signal"].nunique() < 2 or valid["forward_return"].nunique() < 2:
            invalid_periods += 1
            continue
        rho = valid["_signal"].corr(valid["forward_return"], method="spearman")
        if not np.isfinite(rho):
            invalid_periods += 1
            continue
        rankics.append(float(rho))
        ranks = target["_signal"].rank(method="average")
        signal_rows.extend(
            f"{period}|{code}|{value:.12g}"
            for code, value in zip(target.stock_code, target._signal, strict=True)
        )
        rank_rows.extend(
            f"{period}|{code}|{rank:.12g}"
            for code, rank in zip(target.stock_code, ranks, strict=True)
        )
        q5 = quantile_members(target, "_signal")[5]
        portfolio_rows.append(f"{period}|{','.join(sorted(target.loc[q5, 'stock_code']))}")
    if len(rankics) < MIN_PERIODS:
        return _failure("insufficient_valid_periods", len(rankics), invalid_periods)
    array = np.asarray(rankics)
    return {
        "evaluation_status": "ok",
        "failure_reason": "",
        "reward": float(array.mean()),
        "mean_rankic": float(array.mean()),
        "median_rankic": float(np.median(array)),
        "positive_rankic_ratio": float((array > 0).mean()),
        "valid_periods": len(array),
        "invalid_periods": invalid_periods,
        "signal_hash": _hash_rows(signal_rows),
        "rank_signature_hash": _hash_rows(rank_rows),
        "portfolio_signature_hash": _hash_rows(portfolio_rows),
    }


def _failure(reason: str, valid: int = 0, invalid: int = 0) -> dict[str, object]:
    return {
        "evaluation_status": "failed",
        "failure_reason": reason,
        "reward": math.nan,
        "mean_rankic": math.nan,
        "median_rankic": math.nan,
        "positive_rankic_ratio": math.nan,
        "valid_periods": valid,
        "invalid_periods": invalid,
        "signal_hash": "",
        "rank_signature_hash": "",
        "portfolio_signature_hash": "",
    }


def random_expression(rng: random.Random, max_depth: int = MAX_DEPTH, current: int = 1) -> Expr:
    if current >= max_depth or rng.random() < 0.28:
        return (rng.choice(PRIMITIVES),)
    if rng.random() < 0.35:
        return (rng.choice(UNARY), random_expression(rng, max_depth, current + 1))
    return (
        rng.choice(BINARY),
        random_expression(rng, max_depth, current + 1),
        random_expression(rng, max_depth, current + 1),
    )


def _leaf_paths(expr: Expr, path: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
    if len(expr) == 1:
        return [path]
    return [
        leaf
        for index, child in enumerate(expr[1:], 1)
        for leaf in _leaf_paths(child, path + (index,))
    ]


def _replace(expr: Expr, path: tuple[int, ...], replacement: Expr) -> Expr:
    if not path:
        return replacement
    parts = list(expr)
    parts[path[0]] = _replace(parts[path[0]], path[1:], replacement)
    return tuple(parts)


def expansions(expr: Expr, rng: random.Random) -> list[Expr]:
    result: list[Expr] = []
    for path in _leaf_paths(expr):
        for op in UNARY:
            for primitive in PRIMITIVES:
                result.append(_replace(expr, path, (op, (primitive,))))
        for op in BINARY:
            for left in PRIMITIVES:
                for right in PRIMITIVES:
                    result.append(_replace(expr, path, (op, (left,), (right,))))
    result = [candidate for candidate in result if depth(candidate) <= MAX_DEPTH]
    rng.shuffle(result)
    return result


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


def run_mcts(seed: int, budget: int, evaluator) -> list[tuple[Expr, str, dict[str, object]]]:
    """Run minimal UCT with one observed candidate evaluation per iteration."""

    rng = random.Random(seed)
    root = Node(None)
    yielded: list[tuple[Expr, str, dict[str, object]]] = []
    for _ in range(budget):
        node = root
        while not node.choices(rng) and node.children:
            log_parent = math.log(max(node.visits, 1))
            node = max(
                node.children,
                key=lambda child: child.value / child.visits
                + math.sqrt(2) * math.sqrt(log_parent / child.visits),
            )
        if node.choices(rng):
            expr = node.choices(rng).pop()
            child = Node(expr, parent=node)
            node.children.append(child)
            node = child
        else:
            expr = node.expr
        result = evaluator(expr)
        observed = result["reward"] if np.isfinite(result["reward"]) else FAILED_TREE_REWARD
        yielded.append(
            (expr, formula(node.parent.expr) if node.parent and node.parent.expr else "", result)
        )
        backpropagate(node, float(observed))
    return yielded


def backpropagate(node: Node, reward: float) -> None:
    while node:
        node.visits += 1
        node.value += reward
        node = node.parent
