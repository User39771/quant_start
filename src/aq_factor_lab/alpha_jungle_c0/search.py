from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from .contract import C0


class Arm(StrEnum):
    RANDOM = "GRAMMAR_RANDOM"
    DIRECT_LLM = "DIRECT_LLM"
    LLM_GUIDED_MCTS = "LLM_GUIDED_MCTS"


@dataclass(frozen=True)
class SearchBudget:
    unique_valid_evaluations: int = C0.valid_evaluations_per_arm
    checkpoints: tuple[int, ...] = C0.checkpoints
    llm_calls: int = 150


@dataclass
class EvaluationLedger:
    accepted_canonical: set[str] = field(default_factory=set)
    accepted_signal: set[str] = field(default_factory=set)
    failures: dict[str, int] = field(default_factory=dict)
    llm_calls: int = 0

    def reject(self, reason: str) -> None:
        self.failures[reason] = self.failures.get(reason, 0) + 1

    def accept(self, canonical: str, signal_fingerprint: str) -> bool:
        if canonical in self.accepted_canonical:
            self.reject("duplicate_canonical_formula")
            return False
        if signal_fingerprint in self.accepted_signal:
            self.reject("duplicate_exact_signal")
            return False
        self.accepted_canonical.add(canonical)
        self.accepted_signal.add(signal_fingerprint)
        return True


@dataclass
class MCTSNode:
    reward: float
    visits: int = 1
    children: list[MCTSNode] = field(default_factory=list)


def uct(parent_visits: int, child: MCTSNode, c: float = 1.0) -> float:
    if child.visits <= 0:
        return math.inf
    return child.reward + c * math.sqrt(math.log(max(parent_visits, 1)) / child.visits)


def backup_max(path: list[MCTSNode], reward: float) -> None:
    for node in path:
        node.visits += 1
        node.reward = max(node.reward, reward)


def search_disabled() -> None:
    raise RuntimeError(
        "C0 scaffold only: actual Random/Direct-LLM/MCTS search is not authorized in this turn"
    )
