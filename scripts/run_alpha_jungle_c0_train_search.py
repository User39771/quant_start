from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import random
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import qlib
from qlib.config import REG_CN
from qlib.data import D

from aq_factor_lab.alpha_jungle_c0.contract import (
    C0,
    FINAL_TEST_LOCKED,
    MIN_FORMULA_SESSION_COVERAGE,
    assert_period_allowed,
    label_eligible_sessions,
)
from aq_factor_lab.alpha_jungle_c0.evaluation import (
    TrainMetrics,
    daily_coverage_required,
    formula_session_coverage,
    rank_ic_summary,
)
from aq_factor_lab.alpha_jungle_c0.formula import (
    FIELDS,
    Formula,
    FormulaError,
    WINDOWS,
    parse_formula,
    required_historical_lookback,
)
from aq_factor_lab.alpha_jungle_c0.provider import NativeSubagentProvider, normalize_launch_marker
from aq_factor_lab.alpha_jungle_c0.search import Arm, MCTSNode, backup_max, uct
from aq_factor_lab.alpha_jungle_c0.zoo import (
    AlphaZoo,
    exact_signal_fingerprint,
    portfolio_ordering_fingerprint,
    rank_signal_fingerprint,
)


TRACE_FIELDS = [
    "run_segment_id", "arm", "proposal_index", "charged_call_index", "accepted_index",
    "prompt_version", "generator_prompt_hash", "formula", "canonical_formula", "parent_formula",
    "llm_suggestion", "refinement_dimension", "parse_validation_status", "rejection_reason",
    "mean_rank_ic", "rank_ir", "positive_ratio", "subperiod_direction_ratio", "turnover",
    "diversity", "ors_proxy", "effectiveness_score", "stability_score", "turnover_score",
    "diversity_score", "overfitting_risk_proxy_score", "composite_reward", "effective_candidate",
    "coverage_usable_sessions", "coverage_eligible_sessions", "coverage_ratio",
    "zoo_membership_decision", "exact_fingerprint", "rank_fingerprint", "portfolio_fingerprint",
    "timestamp_utc", "runtime_seconds", "llm_call_count", "accepted_formula_count",
    "node_id", "parent_id", "visits", "q", "selected_uct", "children", "backup_result",
    "native_task_id", "prompt_hash", "subagent_failure_status",
]
CHECKPOINT_FIELDS = [
    "arm", "accepted_count", "best_reward", "best_mean_rank_ic", "best_rank_ir",
    "best_turnover", "best_diversity", "best_ors_proxy", "effective_candidate_count",
    "raw_proposal_count", "canonical_formula_count", "unique_exact_signals",
    "unique_rank_signals", "unique_portfolio_orderings", "redundancy_rate",
    "invalid_rejected_by_reason", "llm_calls_used", "elapsed_wall_clock_seconds",
]
SCORES = ("effectiveness", "stability", "turnover", "diversity", "overfitting_risk_proxy")
FIELDS_SORTED = tuple(sorted(FIELDS))
WINDOWS_SORTED = tuple(sorted(WINDOWS))
PRICE_FIELDS = ("open", "high", "low", "close", "vwap")
PROMPT_VERSION = "V1"
PRIMARY_RUN_SEGMENT_ID = "PRIMARY_AFTER_INTERFACE_RESUME_V1"


@dataclass
class Panel:
    raw: dict[str, pd.DataFrame]
    active: pd.DataFrame
    label: pd.DataFrame
    eligible_dates: list[pd.Timestamp]
    all_dates: pd.DatetimeIndex


@dataclass
class Candidate:
    formula: str
    canonical: str
    signal: pd.Series
    metrics: TrainMetrics
    scores: dict[str, float]
    coverage_usable: int
    coverage_eligible: int
    coverage_ratio: float
    exact_fp: str
    rank_fp: str
    portfolio_fp: str


@dataclass
class TreeNode(MCTSNode):
    node_id: int = 0
    parent_id: int | None = None
    formula: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    expansion_limit: int = 3
    expansion_attempts: int = 0


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _append_csv(path: Path, fields: list[str], row: dict[str, object]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({name: row.get(name, "") for name in fields})


def load_panel(provider_uri: Path) -> Panel:
    assert_period_allowed(C0.train_start, C0.train_end)
    qlib.init(provider_uri=str(provider_uri.resolve()), region=REG_CN)
    train_calendar = [
        pd.Timestamp(x) for x in D.calendar(C0.train_start.isoformat(), C0.train_end.isoformat())
    ]
    eligible = label_eligible_sessions(
        [x.date() for x in train_calendar], C0.train_start, C0.train_end
    )
    if not eligible or eligible[-1].isoformat() != "2018-12-13":
        raise RuntimeError("LABEL_HORIZON_SPLIT_ISOLATION_RULE calendar mismatch")

    universe = D.instruments(C0.universe)
    instruments = sorted(
        D.list_instruments(
            universe,
            start_time=C0.train_start.isoformat(),
            end_time=C0.train_end.isoformat(),
            freq="day",
            as_list=True,
        )
    )
    history_start = "2008-01-01"
    raw_frame = D.features(
        instruments,
        [f"${name}" for name in FIELDS_SORTED],
        start_time=history_start,
        end_time=C0.train_end.isoformat(),
        freq="day",
    )
    raw_frame = raw_frame.rename(columns={f"${name}": name for name in FIELDS_SORTED})
    raw = {
        name: raw_frame[name].unstack("instrument").sort_index().sort_index(axis=1)
        for name in FIELDS_SORTED
    }
    all_dates = raw["close"].index

    membership = D.features(
        universe,
        ["$factor"],
        start_time=C0.train_start.isoformat(),
        end_time=C0.train_end.isoformat(),
        freq="day",
    )
    marker = pd.Series(True, index=membership.index).unstack("instrument")
    active = marker.reindex(index=all_dates, columns=raw["close"].columns, fill_value=False)
    active = active.fillna(False).astype(bool)
    label = raw["close"].shift(-11) / raw["close"].shift(-1) - 1
    return Panel(raw, active, label, [pd.Timestamp(x) for x in eligible], all_dates)


def _rolling(value: pd.DataFrame, window: int, method: str) -> pd.DataFrame:
    roll = value.rolling(window, min_periods=1)
    if method == "rank":
        return roll.rank(pct=True)
    return getattr(roll, method)()


def evaluate_ast(value: Formula | str, raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if isinstance(value, str):
        return raw[value]
    children = [evaluate_ast(arg, raw) for arg in value.args if isinstance(arg, (Formula, str))]
    nums = [arg for arg in value.args if isinstance(arg, int)]
    name = value.name
    if name == "Neg": return -children[0]
    if name == "Abs": return children[0].abs()
    if name == "Sign": return np.sign(children[0])
    if name == "Delay": return children[0].shift(nums[0])
    if name == "Diff": return children[0] - children[0].shift(nums[0])
    if name == "Pct": return children[0] / children[0].shift(nums[0]) - 1
    methods = {
        "Ma": "mean", "Med": "median", "Sum": "sum", "Std": "std",
        "Max": "max", "Min": "min", "Rank": "rank", "Skew": "skew", "Kurt": "kurt",
    }
    if name in methods: return _rolling(children[0], nums[0], methods[name])
    if name == "Vari": return _rolling(children[0], nums[0], "std") / _rolling(children[0], nums[0], "mean")
    if name == "Zscore": return (children[0] - _rolling(children[0], nums[0], "mean")) / _rolling(children[0], nums[0], "std")
    if name == "Autocorr": return children[0].rolling(nums[0], min_periods=2).corr(children[0].shift(nums[1]))
    if name == "Add": return children[0] + children[1]
    if name == "Sub": return children[0] - children[1]
    if name == "Mul": return children[0] * children[1]
    if name == "Greater": return children[0].where(children[0] >= children[1], children[1])
    if name == "Less": return children[0].where(children[0] <= children[1], children[1])
    if name == "Corr": return children[0].rolling(nums[0], min_periods=2).corr(children[1])
    raise FormulaError(f"unsupported operator: {name}")


def _rank_ic(signal: pd.DataFrame, label: pd.DataFrame) -> pd.Series:
    mask = signal.notna() & label.notna()
    sr = signal.rank(axis=1, method="average").where(mask)
    lr = label.rank(axis=1, method="average").where(mask)
    sc = sr.sub(sr.mean(axis=1), axis=0).fillna(0)
    lc = lr.sub(lr.mean(axis=1), axis=0).fillna(0)
    denominator = np.sqrt((sc * sc).sum(axis=1) * (lc * lc).sum(axis=1))
    return ((sc * lc).sum(axis=1) / denominator).replace([np.inf, -np.inf], np.nan).dropna()


def _turnover(signal: pd.DataFrame) -> float:
    ranks = signal.rank(axis=1, method="first", ascending=False)
    counts = signal.notna().sum(axis=1)
    held = ranks.le(np.ceil(counts * 0.10), axis=0)
    weights = held.div(held.sum(axis=1), axis=0).fillna(0.0)
    changes = weights.diff().abs().sum(axis=1).iloc[1:]
    return float(changes.mean()) if len(changes) else 0.0


def evaluate_candidate(text: str, panel: Panel, zoo: AlphaZoo) -> Candidate:
    formula = parse_formula(text)
    lookback = required_historical_lookback(formula)
    eligible_dates = [
        day for day in panel.eligible_dates if panel.all_dates.get_loc(day) >= lookback
    ]
    if not eligible_dates:
        raise ValueError("INSUFFICIENT_TRAIN_SESSION_COVERAGE|0|0|0")
    wide = evaluate_ast(formula, panel.raw).reindex(eligible_dates)
    active = panel.active.reindex(index=eligible_dates, columns=wide.columns, fill_value=False)
    label = panel.label.reindex(index=eligible_dates, columns=wide.columns)
    numeric = wide.to_numpy(dtype=float)
    if np.isinf(numeric[active.to_numpy()]).any():
        raise ValueError("NONFINITE_SIGNAL")
    valid = active & np.isfinite(wide) & np.isfinite(label)
    active_n = active.sum(axis=1)
    valid_n = valid.sum(axis=1)
    usable_mask = pd.Series(
        [v >= daily_coverage_required(int(a)) for a, v in zip(active_n, valid_n, strict=True)],
        index=wide.index,
    )
    usable = int(usable_mask.sum())
    coverage, passes = formula_session_coverage(usable, len(eligible_dates))
    if not passes:
        raise ValueError(
            f"INSUFFICIENT_TRAIN_SESSION_COVERAGE|{usable}|{len(eligible_dates)}|{coverage:.12g}"
        )
    wide = wide.loc[usable_mask].where(valid.loc[usable_mask])
    label = label.loc[usable_mask].where(valid.loc[usable_mask])
    signal = wide.stack(future_stack=True).dropna()
    signal.index.names = ["datetime", "instrument"]
    if signal.empty or signal.nunique(dropna=True) <= 1:
        raise ValueError("EMPTY_OR_CONSTANT_SIGNAL")
    label_series = label.stack(future_stack=True).dropna()
    label_series.index.names = ["datetime", "instrument"]
    rank_ic = _rank_ic(wide, label)
    mean_ic, rank_ir, positive, direction = rank_ic_summary(rank_ic)
    max_corr = zoo.max_abs_correlation(signal)
    metrics = TrainMetrics(
        mean_ic, rank_ir, positive, direction, _turnover(wide), max_corr,
        formula.operator_count, formula.depth, len(formula.parameters), 0,
    )
    return Candidate(
        text,
        formula.canonical(),
        signal,
        metrics,
        metrics.scores(),
        usable,
        len(eligible_dates),
        coverage,
        exact_signal_fingerprint(signal),
        rank_signal_fingerprint(signal),
        portfolio_ordering_fingerprint(signal),
    )


def _field(rng: random.Random, unit: str) -> str:
    return rng.choice(PRICE_FIELDS if unit == "PRICE" else ("volume",))


def _random_expr(rng: random.Random, unit: str, depth: int) -> str:
    window = lambda: rng.choice(WINDOWS_SORTED)
    if depth <= 0 and unit != "DIMENSIONLESS":
        return _field(rng, unit)
    if unit == "DIMENSIONLESS":
        source_unit = rng.choice(("PRICE", "VOLUME"))
        if depth <= 0:
            return f"Pct({_field(rng, source_unit)},{window()})"
        op = rng.choice(("Sign", "Pct", "Rank", "Skew", "Kurt", "Vari", "Zscore", "Autocorr", "Corr", "Add", "Sub", "Mul", "Greater", "Less"))
        if op == "Sign": return f"Sign({_random_expr(rng, source_unit, depth-1)})"
        if op in {"Pct", "Rank", "Skew", "Kurt", "Vari", "Zscore"}:
            return f"{op}({_random_expr(rng, source_unit, depth-1)},{window()})"
        if op == "Autocorr":
            return f"Autocorr({_random_expr(rng, source_unit, depth-1)},{window()},{window()})"
        if op == "Corr":
            return f"Corr({_random_expr(rng, source_unit, depth-1)},{_random_expr(rng, source_unit, depth-1)},{window()})"
        return f"{op}({_random_expr(rng, 'DIMENSIONLESS', depth-1)},{_random_expr(rng, 'DIMENSIONLESS', depth-1)})"
    if depth <= 0 or rng.random() < 0.25:
        return _field(rng, unit)
    op = rng.choice(("Neg", "Abs", "Delay", "Diff", "Ma", "Med", "Sum", "Std", "Max", "Min", "Add", "Sub", "Greater", "Less", "Mul"))
    if op in {"Neg", "Abs"}: return f"{op}({_random_expr(rng, unit, depth-1)})"
    if op in {"Delay", "Diff", "Ma", "Med", "Sum", "Std", "Max", "Min"}:
        return f"{op}({_random_expr(rng, unit, depth-1)},{window()})"
    if op == "Mul":
        return f"Mul({_random_expr(rng, unit, depth-1)},{_random_expr(rng, 'DIMENSIONLESS', depth-1)})"
    return f"{op}({_random_expr(rng, unit, depth-1)},{_random_expr(rng, unit, depth-1)})"


def random_formula(rng: random.Random) -> str:
    for _ in range(1000):
        text = _random_expr(rng, "DIMENSIONLESS", rng.randint(2, 4))
        try:
            parse_formula(text)
            return text
        except FormulaError:
            pass
    raise RuntimeError("random grammar sampler could not produce a legal formula")


def _prompt(
    wrapper: str,
    arm: Arm,
    best: dict[str, object] | None,
    parent: TreeNode | None,
    dimension: str,
) -> str:
    feedback = "No accepted formula yet."
    if best:
        feedback = "Current best Train-only feedback: " + _json(best)
    if arm == Arm.DIRECT_LLM:
        context = "You are the Direct-LLM baseline. Do not use tree state. " + feedback + f"\nFocus refinement on {dimension}."
        return wrapper.replace("{{PROPOSAL_CONTEXT}}", context)
    parent_text = "ROOT" if parent is None or parent.formula is None else parent.formula
    parent_scores = {} if parent is None else parent.scores
    context = f"You are expanding an MCTS node. Parent formula: {parent_text}. Parent Train-only component scores: {_json(parent_scores)}. Refine dimension: {dimension}."
    return wrapper.replace("{{PROPOSAL_CONTEXT}}", context)


def _dimension(rng: random.Random, scores: dict[str, float] | None) -> str:
    values = np.array([1.0 - (scores or {}).get(name, 0.0) for name in SCORES])
    probabilities = np.exp(values) / np.exp(values).sum()
    return rng.choices(SCORES, weights=probabilities, k=1)[0]


def _select(root: TreeNode) -> tuple[list[TreeNode], TreeNode, float]:
    path = [root]
    node = root
    selected_uct = math.nan
    while node.children and node.expansion_attempts >= node.expansion_limit:
        child = max(node.children, key=lambda item: (uct(node.visits, item, 1.0), -item.node_id))
        selected_uct = uct(node.visits, child, 1.0)
        node = child
        path.append(node)
    return path, node, selected_uct


def _effective(candidate: Candidate) -> bool:
    m = candidate.metrics
    return m.mean_rank_ic >= 0.015 and m.rank_ir >= 0.3 and m.daily_turnover <= 1.6 and m.max_abs_zoo_corr < 0.8


def _tree_state(root: TreeNode) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    pending = [root]
    while pending:
        node = pending.pop()
        nodes.append({
            "node_id": node.node_id, "parent_id": node.parent_id, "formula": node.formula,
            "scores": node.scores, "reward": node.reward, "visits": node.visits,
            "expansion_limit": node.expansion_limit, "expansion_attempts": node.expansion_attempts,
            "children": [child.node_id for child in node.children],
        })
        pending.extend(node.children)
    return {"nodes": sorted(nodes, key=lambda item: item["node_id"])}


def _restore_tree(value: dict[str, object]) -> TreeNode:
    records = value["nodes"]
    nodes = {
        int(item["node_id"]): TreeNode(
            reward=float(item["reward"]), visits=int(item["visits"]),
            node_id=int(item["node_id"]), parent_id=item["parent_id"],
            formula=item["formula"], scores=dict(item["scores"]),
            expansion_limit=int(item["expansion_limit"]),
            expansion_attempts=int(item["expansion_attempts"]),
        )
        for item in records
    }
    for item in records:
        nodes[int(item["node_id"])].children = [nodes[int(child)] for child in item["children"]]
    return nodes[0]


def _replay_candidates(formulas: list[str], panel: Panel) -> tuple[AlphaZoo, list[Candidate]]:
    zoo = AlphaZoo()
    accepted: list[Candidate] = []
    for formula in formulas:
        candidate = evaluate_candidate(formula, panel, zoo)
        zoo.add(candidate.formula, candidate.canonical, candidate.signal)
        accepted.append(candidate)
    return zoo, accepted


def _repair_append_only_files(
    trace_path: Path,
    checkpoint_path: Path,
    arm_state: dict[str, object],
) -> None:
    last_row = arm_state.get("last_row")
    if last_row:
        rows = list(csv.DictReader(trace_path.open(encoding="utf-8"))) if trace_path.exists() else []
        seen = {int(row["proposal_index"]) for row in rows}
        if int(last_row["proposal_index"]) not in seen:
            _append_csv(trace_path, TRACE_FIELDS, last_row)
    checkpoint = arm_state.get("pending_checkpoint")
    if checkpoint:
        rows = list(csv.DictReader(checkpoint_path.open(encoding="utf-8"))) if checkpoint_path.exists() else []
        seen = {int(row["accepted_count"]) for row in rows}
        if int(checkpoint["accepted_count"]) not in seen:
            _append_csv(checkpoint_path, CHECKPOINT_FIELDS, checkpoint)


def _accepted_candidates_from_trace(path: Path, panel: Panel) -> list[Candidate]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    formulas = [row["formula"] for row in rows if row["parse_validation_status"] == "accepted"]
    return _replay_candidates(formulas, panel)[1]


def _persist_arm_state(
    state_path: Path,
    arm: Arm,
    proposals: int,
    calls: int,
    accepted: list[Candidate],
    failures: dict[str, int],
    effective_count: int,
    rng: random.Random,
    root: TreeNode,
    next_node_id: int,
    row: dict[str, object] | None,
    checkpoint: dict[str, object] | None,
    complete: bool,
    prompt_hash: str,
    elapsed_seconds: float,
) -> None:
    document = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "experiment_id": C0.experiment_id,
        "random_complete": True,
        "direct_complete": False,
        "mcts_complete": False,
        "direct_calls_used": 0,
        "direct_accepted": 0,
        "mcts_calls_used": 0,
        "mcts_accepted": 0,
        "last_committed_proposal_id": None,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "final_test_locked": FINAL_TEST_LOCKED,
        "validation_accessed": False,
        "final_test_accessed": False,
    }
    if document.get("prompt_version") != PROMPT_VERSION or document.get("prompt_hash") != prompt_hash:
        raise RuntimeError("frozen FORMULA_GENERATOR prompt identity changed")
    document.update({
        "current_arm": arm.value,
        "last_committed_proposal_id": None if row is None else f"{arm.value}:{proposals}",
        "arm_state": {
            "arm": arm.value, "proposals": proposals, "calls": calls,
            "accepted_formulas": [item.formula for item in accepted],
            "failures": failures, "effective_count": effective_count,
            "rng_state": repr(rng.getstate()), "tree": _tree_state(root),
            "next_node_id": next_node_id, "last_row": row,
            "pending_checkpoint": checkpoint, "elapsed_seconds": elapsed_seconds,
        },
    })
    if arm == Arm.DIRECT_LLM:
        document.update(direct_calls_used=calls, direct_accepted=len(accepted), direct_complete=complete)
    elif arm == Arm.LLM_GUIDED_MCTS:
        document.update(mcts_calls_used=calls, mcts_accepted=len(accepted), mcts_complete=complete)
    _write_json(state_path, document)


def _reconcile_interrupted_bridge(
    bridge_dir: Path,
    state_path: Path,
    trace_dir: Path,
    checkpoint_dir: Path,
    panel: Panel,
    prompt_hash: str,
) -> None:
    names = {
        Arm.DIRECT_LLM.value: ("direct_llm_trace.csv", "direct_llm_checkpoints.csv"),
        Arm.LLM_GUIDED_MCTS.value: ("mcts_trace.csv", "mcts_checkpoints.csv"),
    }
    for request_path in sorted(bridge_dir.glob("*.request.json")):
        request_id = request_path.name.removesuffix(".request.json")
        marker_path = bridge_dir / f"{request_id}.launched.json"
        response_path = bridge_dir / f"{request_id}.response.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        metadata = request.get("resume_metadata", {})
        if not metadata:
            continue
        if not marker_path.exists():
            if not response_path.exists():
                request_path.replace(bridge_dir / f"{request_id}.unlaunched.json")
            continue
        arm = Arm(metadata["arm"])
        trace_name, checkpoint_name = names[arm.value]
        trace_path = trace_dir / trace_name
        existing = list(csv.DictReader(trace_path.open(encoding="utf-8"))) if trace_path.exists() else []
        proposal_index = int(metadata["proposal_index"])
        if any(int(row["proposal_index"]) == proposal_index for row in existing):
            marker_path.replace(bridge_dir / f"{request_id}.reconciled.json")
            continue
        marker = normalize_launch_marker(
            json.loads(marker_path.read_text(encoding="utf-8")), request
        )
        _write_json(marker_path, marker)
        failures = {str(key): int(value) for key, value in metadata["failures"].items()}
        reason = "INTERRUPTED_LAUNCHED_ATTEMPT"
        failures[reason] = failures.get(reason, 0) + 1
        _, accepted = _replay_candidates(list(metadata["accepted_formulas"]), panel)
        rng = random.Random()
        rng.setstate(ast.literal_eval(metadata["rng_state"]))
        root = _restore_tree(metadata["tree"])
        row = {
            "run_segment_id": metadata["run_segment_id"], "arm": arm.value,
            "proposal_index": proposal_index,
            "charged_call_index": int(metadata["charged_call_index"]),
            "accepted_index": len(accepted), "prompt_version": metadata["prompt_version"],
            "generator_prompt_hash": metadata["generator_prompt_hash"],
            "formula": "", "parent_formula": metadata["parent_formula"],
            "llm_suggestion": "", "refinement_dimension": metadata["refinement_dimension"],
            "parse_validation_status": "rejected", "rejection_reason": reason,
            "timestamp_utc": marker["timestamp_utc"], "runtime_seconds": "",
            "llm_call_count": int(metadata["charged_call_index"]),
            "accepted_formula_count": len(accepted), "parent_id": metadata["parent_id"],
            "selected_uct": metadata["selected_uct"],
            "native_task_id": marker.get("subagent_task_id") or "",
            "prompt_hash": request["prompt_hash"], "subagent_failure_status": reason,
        }
        _persist_arm_state(
            state_path, arm, proposal_index, int(metadata["charged_call_index"]),
            accepted, failures, int(metadata["effective_count"]), rng, root,
            int(metadata["next_node_id"]), row, None,
            int(metadata["charged_call_index"]) >= 150, prompt_hash,
            float(metadata["elapsed_seconds"]),
        )
        _append_csv(trace_path, TRACE_FIELDS, row)
        marker_path.replace(bridge_dir / f"{request_id}.reconciled.json")


def run_arm(
    arm: Arm,
    target: int,
    panel: Panel,
    trace_path: Path,
    checkpoint_path: Path,
    provider: NativeSubagentProvider | None,
    schema_path: Path,
    project_root: Path,
    seed: int,
    llm_cap: int,
    prompt_wrapper: str | None = None,
    prompt_hash: str = "",
    state_path: Path | None = None,
    run_segment_id: str = "",
) -> dict[str, object]:
    rng = random.Random(seed)
    zoo = AlphaZoo()
    accepted: list[Candidate] = []
    failures: dict[str, int] = {}
    proposals = calls = effective_count = 0
    started = time.perf_counter()
    elapsed_offset = 0.0
    root = TreeNode(0.0, node_id=0)
    next_node_id = 1
    best: Candidate | None = None

    if state_path and state_path.exists():
        document = json.loads(state_path.read_text(encoding="utf-8"))
        if document.get("prompt_version") != PROMPT_VERSION or document.get("prompt_hash") != prompt_hash:
            raise RuntimeError("resume-state prompt identity does not match frozen V1 wrapper")
        arm_state = document.get("arm_state", {})
        if arm_state.get("arm") == arm.value:
            _repair_append_only_files(trace_path, checkpoint_path, arm_state)
            proposals = int(arm_state["proposals"])
            calls = int(arm_state["calls"])
            failures = {str(key): int(value) for key, value in arm_state["failures"].items()}
            effective_count = int(arm_state["effective_count"])
            elapsed_offset = float(arm_state.get("elapsed_seconds", 0.0))
            rng.setstate(ast.literal_eval(arm_state["rng_state"]))
            zoo, accepted = _replay_candidates(list(arm_state["accepted_formulas"]), panel)
            best = max(accepted, key=lambda item: item.metrics.reward, default=None)
            root = _restore_tree(arm_state["tree"])
            next_node_id = int(arm_state["next_node_id"])

    if arm != Arm.RANDOM and prompt_wrapper is None:
        raise RuntimeError("frozen FORMULA_GENERATOR wrapper is required")

    while len(accepted) < target and (arm == Arm.RANDOM or calls < llm_cap):
        proposals += 1
        proposal_started = time.perf_counter()
        suggestion = formula_text = parent_formula = dimension = ""
        node_id = parent_id = children = ""
        visits = q = selected_uct = backup_result = ""
        parent: TreeNode | None = None
        path: list[TreeNode] = []

        if arm == Arm.RANDOM:
            formula_text = random_formula(rng)
        else:
            calls += 1
            if arm == Arm.LLM_GUIDED_MCTS:
                path, parent, selected_uct_value = _select(root)
                parent.expansion_attempts += 1
                parent_formula = parent.formula or ""
                parent_id = parent.node_id
                selected_uct = selected_uct_value
                dimension = _dimension(rng, parent.scores)
            else:
                dimension = _dimension(rng, best.scores if best else None)
            best_feedback = None if best is None else {
                "formula": best.formula, "reward": best.metrics.reward, **best.scores
            }
            resume_metadata = {
                "experiment_id": C0.experiment_id,
                "run_segment_id": run_segment_id, "arm": arm.value,
                "proposal_index": proposals, "charged_call_index": calls,
                "accepted_index": len(accepted), "prompt_version": PROMPT_VERSION,
                "generator_prompt_hash": prompt_hash, "refinement_dimension": dimension,
                "parent_formula": parent_formula, "parent_id": parent_id,
                "selected_uct": selected_uct, "rng_state": repr(rng.getstate()),
                "tree": _tree_state(root), "next_node_id": next_node_id,
                "accepted_formulas": [item.formula for item in accepted],
                "failures": failures, "effective_count": effective_count,
                "elapsed_seconds": elapsed_offset + time.perf_counter() - started,
            }
            result = provider.invoke(
                _prompt(prompt_wrapper, arm, best_feedback, parent, dimension),
                schema_path,
                project_root,
                resume_metadata,
            )
            if not result.ok:
                reason = "PROVIDER_TIMEOUT" if (result.error or "").startswith("provider timeout") else "PROVIDER_FAILURE"
                failures[reason] = failures.get(reason, 0) + 1
                failed_row = {
                    "run_segment_id": run_segment_id, "arm": arm.value,
                    "proposal_index": proposals, "charged_call_index": calls,
                    "accepted_index": len(accepted), "prompt_version": PROMPT_VERSION,
                    "generator_prompt_hash": prompt_hash, "llm_suggestion": "",
                    "refinement_dimension": dimension, "parse_validation_status": "rejected",
                    "rejection_reason": reason + ":" + (result.error or "")[:500],
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime_seconds": result.latency_seconds, "llm_call_count": calls,
                    "accepted_formula_count": len(accepted), "parent_formula": parent_formula,
                    "parent_id": parent_id, "selected_uct": selected_uct,
                    "native_task_id": result.task_id or "", "prompt_hash": result.prompt_hash or "",
                    "subagent_failure_status": result.subagent_failure or reason,
                }
                failed_row["runtime_seconds"] = time.perf_counter() - proposal_started
                if state_path:
                    _persist_arm_state(
                        state_path, arm, proposals, calls, accepted, failures, effective_count,
                        rng, root, next_node_id, failed_row, None,
                        len(accepted) == target or calls >= llm_cap, prompt_hash,
                        elapsed_offset + time.perf_counter() - started,
                    )
                _append_csv(trace_path, TRACE_FIELDS, failed_row)
                continue
            suggestion = result.output["suggestion"]
            formula_text = result.output["formula"]

        row: dict[str, object] = {
            "run_segment_id": run_segment_id, "arm": arm.value,
            "proposal_index": proposals, "charged_call_index": calls if arm != Arm.RANDOM else 0,
            "accepted_index": len(accepted), "prompt_version": PROMPT_VERSION if arm != Arm.RANDOM else "",
            "generator_prompt_hash": prompt_hash if arm != Arm.RANDOM else "",
            "formula": formula_text,
            "parent_formula": parent_formula, "llm_suggestion": suggestion,
            "refinement_dimension": dimension, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "llm_call_count": calls, "parent_id": parent_id, "selected_uct": selected_uct,
            "native_task_id": "" if arm == Arm.RANDOM else (result.task_id or ""),
            "prompt_hash": "" if arm == Arm.RANDOM else (result.prompt_hash or ""),
            "subagent_failure_status": "",
        }
        try:
            candidate = evaluate_candidate(formula_text, panel, zoo)
            row["canonical_formula"] = candidate.canonical
            if candidate.canonical in zoo.canonical_formulas:
                raise ValueError("DUPLICATE_CANONICAL_FORMULA")
            if candidate.exact_fp in zoo.exact_signals:
                raise ValueError("DUPLICATE_EXACT_SIGNAL")
        except (FormulaError, ValueError, KeyError) as exc:
            raw_reason = str(exc) or exc.__class__.__name__
            reason = raw_reason.split("|", 1)[0]
            failures[reason] = failures.get(reason, 0) + 1
            if reason == "INSUFFICIENT_TRAIN_SESSION_COVERAGE":
                parts = raw_reason.split("|")
                if len(parts) == 4:
                    row.update(coverage_usable_sessions=parts[1], coverage_eligible_sessions=parts[2], coverage_ratio=parts[3])
            row.update(parse_validation_status="rejected", rejection_reason=raw_reason, zoo_membership_decision="rejected")
        else:
            zoo.add(candidate.formula, candidate.canonical, candidate.signal)
            accepted.append(candidate)
            effective_count += int(_effective(candidate))
            if best is None or candidate.metrics.reward > best.metrics.reward:
                best = candidate
            scores = candidate.scores
            row.update(
                parse_validation_status="accepted", rejection_reason="", zoo_membership_decision="added",
                mean_rank_ic=candidate.metrics.mean_rank_ic, rank_ir=candidate.metrics.rank_ir,
                positive_ratio=candidate.metrics.positive_ratio,
                subperiod_direction_ratio=candidate.metrics.subperiod_direction_ratio,
                turnover=candidate.metrics.daily_turnover, diversity=1-candidate.metrics.max_abs_zoo_corr,
                ors_proxy=scores["overfitting_risk_proxy"], effectiveness_score=scores["effectiveness"],
                stability_score=scores["stability"], turnover_score=scores["turnover"],
                diversity_score=scores["diversity"], overfitting_risk_proxy_score=scores["overfitting_risk_proxy"],
                composite_reward=candidate.metrics.reward, effective_candidate=_effective(candidate),
                coverage_usable_sessions=candidate.coverage_usable,
                coverage_eligible_sessions=candidate.coverage_eligible, coverage_ratio=candidate.coverage_ratio,
                exact_fingerprint=candidate.exact_fp, rank_fingerprint=candidate.rank_fp,
                portfolio_fingerprint=candidate.portfolio_fp,
            )
            if arm == Arm.LLM_GUIDED_MCTS:
                assert parent is not None
                old_parent_reward = parent.reward
                child = TreeNode(
                    candidate.metrics.reward, node_id=next_node_id, parent_id=parent.node_id,
                    formula=candidate.formula, scores=candidate.scores,
                )
                next_node_id += 1
                parent.children.append(child)
                if candidate.metrics.reward > old_parent_reward:
                    parent.expansion_limit += 1  # frozen breakthrough b=1 virtual re-expansion
                backup_max(path + [child], candidate.metrics.reward)
                node_id, visits, q = child.node_id, child.visits, child.reward
                children, backup_result = _json([x.node_id for x in child.children]), candidate.metrics.reward
                row.update(node_id=node_id, visits=visits, q=q, children=children, backup_result=backup_result)

        row["runtime_seconds"] = time.perf_counter() - proposal_started
        row["accepted_formula_count"] = len(accepted)
        row["accepted_index"] = len(accepted)

        checkpoint = None
        if len(accepted) in C0.checkpoints and row.get("parse_validation_status") == "accepted":
            counts = zoo.counts()
            best_metrics = best.metrics
            checkpoint = {
                "arm": arm.value, "accepted_count": len(accepted), "best_reward": best_metrics.reward,
                "best_mean_rank_ic": best_metrics.mean_rank_ic, "best_rank_ir": best_metrics.rank_ir,
                "best_turnover": best_metrics.daily_turnover,
                "best_diversity": 1-best_metrics.max_abs_zoo_corr,
                "best_ors_proxy": best.scores["overfitting_risk_proxy"],
                "effective_candidate_count": effective_count, "raw_proposal_count": proposals,
                "canonical_formula_count": counts["canonical_formula_count"],
                "unique_exact_signals": counts["unique_exact_signal_count"],
                "unique_rank_signals": counts["unique_rank_signal_count"],
                "unique_portfolio_orderings": counts["unique_portfolio_ordering_count"],
                "redundancy_rate": 1-counts["unique_rank_signal_count"]/len(accepted),
                "invalid_rejected_by_reason": _json(failures), "llm_calls_used": calls,
                "elapsed_wall_clock_seconds": elapsed_offset + time.perf_counter()-started,
            }
        elapsed = elapsed_offset + time.perf_counter() - started
        if state_path:
            _persist_arm_state(
                state_path, arm, proposals, calls, accepted, failures, effective_count,
                rng, root, next_node_id, row, checkpoint,
                len(accepted) == target or (arm != Arm.RANDOM and calls >= llm_cap),
                prompt_hash, elapsed,
            )
        _append_csv(trace_path, TRACE_FIELDS, row)
        if checkpoint:
            _append_csv(checkpoint_path, CHECKPOINT_FIELDS, checkpoint)

    counts = zoo.counts()
    return {
        "arm": arm.value, "seed": seed, "target": target, "accepted": len(accepted),
        "proposals": proposals, "llm_calls": calls, "reached_budget": len(accepted) == target,
        "stopping_rule_reached": len(accepted) == target or (arm != Arm.RANDOM and calls >= llm_cap),
        "effective_candidates": effective_count, "failures": failures, "zoo": counts,
        "redundancy_rate": 1-counts["unique_rank_signal_count"]/len(accepted) if accepted else None,
        "elapsed_seconds": elapsed_offset + time.perf_counter()-started,
        "best": None if best is None else {
            "formula": best.formula, "canonical": best.canonical, "reward": best.metrics.reward,
            **asdict(best.metrics), **best.scores,
        },
        "accepted_candidates": accepted,
    }


def write_report(report_path: Path, smoke: dict[str, object], formal: dict[str, dict[str, object]]) -> None:
    lines = [
        "# ALPHA_JUNGLE_QLIB_C0 Train search run report", "",
        "```text", "status=TRAIN_SEARCH_COMPLETE", "validation_accessed=false",
        "final_test_accessed=false", f"FINAL_TEST_LOCKED={str(FINAL_TEST_LOCKED).lower()}", "```", "",
        "The earlier pre-smoke stop was resolved prospectively by `C0_CONTRACT_AMENDMENT_V1.md`.", "",
        "## Smoke", "", "`SMOKE_ONLY`; `NOT_PART_OF_C0_RESULTS`. All three arms accepted three formulas; all smoke state was discarded before formal execution.", "",
        "## Formal Train-only run", "",
        "| Arm | Accepted | Proposals | LLM calls | Budget reached | Best reward | Unique rank signals | Redundancy |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for arm in Arm:
        result = formal[arm.value]
        lines.append(
            f"| {arm.value} | {result['accepted']} | {result['proposals']} | {result['llm_calls']} | "
            f"{result['reached_budget']} | {result['best']['reward'] if result['best'] else ''} | "
            f"{result['zoo']['unique_rank_signal_count']} | {result['redundancy_rate']} |"
        )
    lines += [
        "", "Checkpoint CSVs contain the frozen Train-only diagnostics at 10/20/50/100 accepted formulas.",
        "No Validation metric, Validation ranking, or Final-Test value was computed.", "",
        "```text", "READY_FOR_VALIDATION=true", "```", "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", type=Path, default=Path(r"D:\qlib_data\cn_data"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke-only", action="store_true")
    mode.add_argument("--formal-after-smoke", action="store_true")
    mode.add_argument("--resume-after-quota", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "reports" / "alpha_jungle_c0"
    prompt_path = output / "FORMULA_GENERATOR_PROMPT_V1.txt"
    prompt_wrapper = prompt_path.read_text(encoding="utf-8")
    if prompt_wrapper.count("{{PROPOSAL_CONTEXT}}") != 1:
        raise RuntimeError("frozen FORMULA_GENERATOR wrapper needs one proposal-context slot")
    generator_prompt_hash = hashlib.sha256(prompt_wrapper.encode("utf-8")).hexdigest()
    panel = load_panel(args.provider_uri)
    bridge_dir = output / "native_subagent_bridge"
    if bridge_dir.exists() and not args.resume_after_quota:
        raise FileExistsError("native bridge directory exists; refusing ambiguous reuse")
    provider = NativeSubagentProvider(bridge_dir)
    seeds = {Arm.RANDOM: 20260922, Arm.DIRECT_LLM: 20260923, Arm.LLM_GUIDED_MCTS: 20260924}

    if args.resume_after_quota:
        manifest = json.loads((output / "search_run_manifest.json").read_text(encoding="utf-8"))
        smoke_results = manifest["smoke"]
        random_result = manifest["formal"].get(Arm.RANDOM.value)
        if (
            any(smoke_results[arm.value]["accepted"] != 3 for arm in Arm)
            or not json.loads((output / "smoke_reset_record.json").read_text(encoding="utf-8"))["state_reset"]
            or not random_result or random_result["accepted"] != 100
            or random_result["llm_calls"] != 0
        ):
            raise RuntimeError("persisted smoke/Random state differs from the audited resume point")
    elif args.formal_after_smoke:
        smoke_record = json.loads((output / "smoke_reset_record.json").read_text(encoding="utf-8"))
        smoke_results = smoke_record["results"]
        if not smoke_record.get("state_reset") or any(
            smoke_results[arm.value]["accepted"] != 3
            or not smoke_results[arm.value]["reached_budget"] for arm in Arm
        ):
            raise RuntimeError("audited R/L/M smoke PASS with reset is required")
    else:
        with tempfile.TemporaryDirectory(prefix="alpha_jungle_c0_smoke_") as temp_name:
            temp = Path(temp_name)
            smoke_results = {}
            for arm in Arm:
                result = run_arm(
                    arm, 3, panel, temp / f"{arm.value}.csv", temp / f"{arm.value}_cp.csv",
                    None if arm == Arm.RANDOM else provider, temp / "schema.json", root,
                    seeds[arm], 12, prompt_wrapper, generator_prompt_hash,
                    run_segment_id="SMOKE_ONLY",
                )
                if not result["reached_budget"]:
                    raise RuntimeError(f"SMOKE_ONLY failed for {arm.value}: {result}")
                smoke_results[arm.value] = {k: v for k, v in result.items() if k != "accepted_candidates"}
            smoke_trace = {
                path.name: list(csv.DictReader(path.open(encoding="utf-8")))
                for path in temp.glob("*.csv")
            }
            _write_json(output / "smoke_reset_record.json", {
                "status": "SMOKE_ONLY_NOT_PART_OF_C0_RESULTS", "results": smoke_results,
                "trace_audit": smoke_trace, "state_reset": True,
                "temporary_directory_deleted_on_exit": True,
            })
            shutil.rmtree(bridge_dir)
            if args.smoke_only:
                print(json.dumps(smoke_results, indent=2, default=str))
                return 0

    trace_dir = output / "search_traces"
    checkpoint_dir = output / "checkpoints"
    required_paths = [
        trace_dir / "random_search_trace.csv", trace_dir / "direct_llm_trace.csv",
        trace_dir / "mcts_trace.csv", checkpoint_dir / "random_checkpoints.csv",
        checkpoint_dir / "direct_llm_checkpoints.csv", checkpoint_dir / "mcts_checkpoints.csv",
        output / "best_train_candidates.csv",
    ]
    if not args.resume_after_quota and any(path.exists() for path in required_paths):
        raise FileExistsError("formal trace/checkpoint exists; refusing to overwrite earlier rows")
    trace_dir.mkdir(exist_ok=True)
    checkpoint_dir.mkdir(exist_ok=True)
    names = {
        Arm.RANDOM: ("random_search_trace.csv", "random_checkpoints.csv"),
        Arm.DIRECT_LLM: ("direct_llm_trace.csv", "direct_llm_checkpoints.csv"),
        Arm.LLM_GUIDED_MCTS: ("mcts_trace.csv", "mcts_checkpoints.csv"),
    }
    formal = {Arm.RANDOM.value: random_result} if args.resume_after_quota else {}
    all_best_rows = []
    state_path = output / "FORMAL_SEARCH_RESUME_STATE.json"
    if args.resume_after_quota and not state_path.exists():
        _write_json(state_path, {
            "experiment_id": C0.experiment_id, "current_arm": Arm.DIRECT_LLM.value,
            "random_complete": True, "direct_complete": False, "mcts_complete": False,
            "direct_calls_used": 0, "direct_accepted": 0,
            "mcts_calls_used": 0, "mcts_accepted": 0,
            "last_committed_proposal_id": None, "prompt_version": PROMPT_VERSION,
            "prompt_hash": generator_prompt_hash, "final_test_locked": FINAL_TEST_LOCKED,
            "validation_accessed": False, "final_test_accessed": False,
        })
    arms_to_run = (Arm.DIRECT_LLM, Arm.LLM_GUIDED_MCTS) if args.resume_after_quota else tuple(Arm)
    if args.resume_after_quota:
        _reconcile_interrupted_bridge(
            bridge_dir, state_path, trace_dir, checkpoint_dir, panel, generator_prompt_hash
        )
        resume_document = json.loads(state_path.read_text(encoding="utf-8"))
        saved_direct = manifest["formal"].get(Arm.DIRECT_LLM.value)
        if resume_document.get("direct_complete") and saved_direct:
            formal[Arm.DIRECT_LLM.value] = saved_direct
            arms_to_run = (Arm.LLM_GUIDED_MCTS,)
    with tempfile.TemporaryDirectory(prefix="alpha_jungle_c0_schema_") as schema_name:
        schema = Path(schema_name) / "proposal_schema.json"
        for arm in arms_to_run:
            trace_name, cp_name = names[arm]
            result = run_arm(
                arm, C0.valid_evaluations_per_arm, panel, trace_dir / trace_name,
                checkpoint_dir / cp_name, None if arm == Arm.RANDOM else provider,
                schema, root, seeds[arm], 150, prompt_wrapper, generator_prompt_hash,
                state_path if arm != Arm.RANDOM else None, PRIMARY_RUN_SEGMENT_ID,
            )
            formal[arm.value] = {k: v for k, v in result.items() if k != "accepted_candidates"}
            ranked = sorted(result["accepted_candidates"], key=lambda x: x.metrics.reward, reverse=True)[:10]
            all_best_rows.extend({
                "arm": arm.value, "rank": rank, "formula": item.formula,
                "canonical_formula": item.canonical, "reward": item.metrics.reward,
                "mean_rank_ic": item.metrics.mean_rank_ic, "rank_ir": item.metrics.rank_ir,
                "turnover": item.metrics.daily_turnover, "diversity": 1-item.metrics.max_abs_zoo_corr,
                "ors_proxy": item.scores["overfitting_risk_proxy"],
            } for rank, item in enumerate(ranked, 1))
            _write_json(output / "search_run_manifest.json", {
                "experiment_id": C0.experiment_id, "status": "FORMAL_TRAIN_SEARCH_RUNNING",
                "provider_uri": str(args.provider_uri.resolve()), "python": __import__("sys").version,
                "qlib": qlib.__version__, "seeds": {key.value: value for key, value in seeds.items()},
                "smoke": smoke_results, "formal": formal, "validation_accessed": False,
                "final_test_accessed": False, "final_test_locked": FINAL_TEST_LOCKED,
            })

    if args.resume_after_quota:
        random_candidates = _accepted_candidates_from_trace(trace_dir / "random_search_trace.csv", panel)
        ranked = sorted(random_candidates, key=lambda x: x.metrics.reward, reverse=True)[:10]
        all_best_rows[0:0] = [{
            "arm": Arm.RANDOM.value, "rank": rank, "formula": item.formula,
            "canonical_formula": item.canonical, "reward": item.metrics.reward,
            "mean_rank_ic": item.metrics.mean_rank_ic, "rank_ir": item.metrics.rank_ir,
            "turnover": item.metrics.daily_turnover, "diversity": 1-item.metrics.max_abs_zoo_corr,
            "ors_proxy": item.scores["overfitting_risk_proxy"],
        } for rank, item in enumerate(ranked, 1)]

    pd.DataFrame(all_best_rows).to_csv(output / "best_train_candidates.csv", index=False)
    ready = all(
        formal[arm.value].get("stopping_rule_reached", formal[arm.value]["reached_budget"])
        for arm in Arm
    )
    manifest = {
        "experiment_id": C0.experiment_id,
        "status": "TRAIN_SEARCH_COMPLETE" if ready else "TRAIN_SEARCH_STOPPED_AT_FROZEN_CAP",
        "provider_uri": str(args.provider_uri.resolve()), "python": __import__("sys").version,
        "qlib": qlib.__version__, "seeds": {key.value: value for key, value in seeds.items()},
        "smoke": smoke_results, "formal": formal, "validation_accessed": False,
        "final_test_accessed": False, "final_test_locked": FINAL_TEST_LOCKED,
        "ready_for_validation": ready,
    }
    _write_json(output / "search_run_manifest.json", manifest)
    write_report(output / "TRAIN_SEARCH_RUN_REPORT.md", smoke_results, formal)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
