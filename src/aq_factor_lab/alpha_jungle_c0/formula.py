from __future__ import annotations

import ast
from dataclasses import dataclass

FIELDS = frozenset({"open", "high", "low", "close", "volume", "vwap"})
WINDOWS = frozenset({2, 3, 5, 10, 20, 30, 60})
MAX_DEPTH = 5
MAX_OPERATORS = 8
MAX_PARAMETERS = 3

# name: (expression-argument count, integer-parameter count)
OPERATORS: dict[str, tuple[int, int]] = {
    "Neg": (1, 0),
    "Abs": (1, 0),
    "Sign": (1, 0),
    "Delay": (1, 1),
    "Diff": (1, 1),
    "Pct": (1, 1),
    "Ma": (1, 1),
    "Med": (1, 1),
    "Sum": (1, 1),
    "Std": (1, 1),
    "Max": (1, 1),
    "Min": (1, 1),
    "Rank": (1, 1),
    "Skew": (1, 1),
    "Kurt": (1, 1),
    "Vari": (1, 1),
    "Zscore": (1, 1),
    "Autocorr": (1, 2),
    "Add": (2, 0),
    "Sub": (2, 0),
    "Mul": (2, 0),
    "Greater": (2, 0),
    "Less": (2, 0),
    "Corr": (2, 1),
}
COMMUTATIVE = frozenset({"Add", "Mul", "Greater", "Less", "Corr"})
PRICE_FIELDS = frozenset({"open", "high", "low", "close", "vwap"})


class FormulaError(ValueError):
    pass


@dataclass(frozen=True)
class Formula:
    name: str
    args: tuple[Formula | str | int, ...]

    @property
    def operator_count(self) -> int:
        return 1 + sum(arg.operator_count for arg in self.args if isinstance(arg, Formula))

    @property
    def depth(self) -> int:
        children = [arg.depth for arg in self.args if isinstance(arg, Formula)]
        return 1 + (max(children) if children else 0)

    @property
    def parameters(self) -> tuple[int, ...]:
        return tuple(
            sorted({arg for node in self.walk() for arg in node.args if isinstance(arg, int)})
        )

    def walk(self):
        yield self
        for arg in self.args:
            if isinstance(arg, Formula):
                yield from arg.walk()

    def canonical(self) -> str:
        args = [arg.canonical() if isinstance(arg, Formula) else str(arg) for arg in self.args]
        if self.name in COMMUTATIVE:
            expr_count, _ = OPERATORS[self.name]
            args[:expr_count] = sorted(args[:expr_count])
        return f"{self.name}({','.join(args)})"

    def qlib_expression(self) -> str:
        e = [
            arg.qlib_expression()
            if isinstance(arg, Formula)
            else (f"${arg}" if isinstance(arg, str) else str(arg))
            for arg in self.args
        ]
        name = self.name
        if name == "Neg":
            return f"(-{e[0]})"
        if name in {"Abs", "Sign", "Med", "Sum", "Std", "Max", "Min", "Rank", "Skew", "Kurt"}:
            return f"{name}({','.join(e)})"
        if name == "Delay":
            return f"Ref({e[0]},{e[1]})"
        if name == "Diff":
            return f"Delta({e[0]},{e[1]})"
        if name == "Pct":
            return f"(({e[0]})/Ref({e[0]},{e[1]})-1)"
        if name == "Ma":
            return f"Mean({e[0]},{e[1]})"
        if name == "Vari":
            return f"(Std({e[0]},{e[1]})/Mean({e[0]},{e[1]}))"
        if name == "Zscore":
            return f"((({e[0]})-Mean({e[0]},{e[1]}))/Std({e[0]},{e[1]}))"
        if name == "Autocorr":
            return f"Corr({e[0]},Ref({e[0]},{e[1]}),{e[2]})"
        if name in {"Add", "Sub", "Mul"}:
            symbol = {"Add": "+", "Sub": "-", "Mul": "*"}[name]
            return f"(({e[0]}){symbol}({e[1]}))"
        return f"{name}({','.join(e)})"


def _parse(node: ast.AST) -> Formula | str | int:
    if isinstance(node, ast.Name) and node.id.lower() in FIELDS:
        return node.id.lower()
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.keywords:
        raise FormulaError("formula must use only named grammar calls, fields, and integer windows")
    name = node.func.id
    if name not in OPERATORS:
        raise FormulaError(f"operator not allowed: {name}")
    expr_n, param_n = OPERATORS[name]
    if len(node.args) != expr_n + param_n:
        raise FormulaError(f"{name} expects {expr_n} expression args and {param_n} integer params")
    args = tuple(_parse(arg) for arg in node.args)
    if any(not isinstance(arg, (Formula, str)) for arg in args[:expr_n]):
        raise FormulaError(f"{name} expression arguments must be expressions or fields")
    if any(not isinstance(arg, int) or arg not in WINDOWS for arg in args[expr_n:]):
        raise FormulaError(f"{name} parameters must be frozen windows: {sorted(WINDOWS)}")
    return Formula(name, args)


def _unit(value: Formula | str) -> str:
    if isinstance(value, str):
        return "PRICE" if value in PRICE_FIELDS else "VOLUME"
    child_units = [_unit(arg) for arg in value.args if isinstance(arg, (Formula, str))]
    if value.name in {"Sign", "Pct", "Rank", "Skew", "Kurt", "Vari", "Zscore", "Autocorr", "Corr"}:
        return "DIMENSIONLESS"
    if value.name in {"Add", "Sub", "Greater", "Less"}:
        if child_units[0] != child_units[1]:
            raise FormulaError(f"{value.name} requires matching units")
        return child_units[0]
    if value.name == "Mul":
        if child_units[0] == "DIMENSIONLESS":
            return child_units[1]
        if child_units[1] == "DIMENSIONLESS":
            return child_units[0]
        raise FormulaError("Mul requires at least one dimensionless operand")
    return child_units[0]


def parse_formula(text: str) -> Formula:
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(str(exc)) from exc
    formula = _parse(parsed.body)
    if not isinstance(formula, Formula):
        raise FormulaError("a raw field is not a formula")
    if formula.operator_count > MAX_OPERATORS or formula.depth > MAX_DEPTH:
        raise FormulaError("formula exceeds frozen complexity limits")
    if len(formula.parameters) > MAX_PARAMETERS:
        raise FormulaError("formula exceeds three unique numeric parameters")
    if len({node.name for node in formula.walk()}) < 2:
        raise FormulaError("formula requires at least two distinct operations")
    if any(
        node.name == "Delay" and any(isinstance(x, int) and x < 0 for x in node.args)
        for node in formula.walk()
    ):
        raise FormulaError("future references are forbidden")
    if _unit(formula) != "DIMENSIONLESS":
        raise FormulaError("formula root must be dimensionless")
    return formula


def required_historical_lookback(value: Formula | str) -> int:
    """Maximum prior-session distance needed to evaluate an AST at one date."""
    if isinstance(value, str):
        return 0
    child_lookbacks = [
        required_historical_lookback(arg) for arg in value.args if isinstance(arg, (Formula, str))
    ]
    base = max(child_lookbacks, default=0)
    integers = [arg for arg in value.args if isinstance(arg, int)]
    if value.name in {"Delay", "Diff", "Pct"}:
        return base + integers[0]
    if value.name == "Autocorr":
        window, lag = integers
        return base + lag + window - 1
    if value.name in {
        "Ma", "Med", "Sum", "Std", "Max", "Min", "Rank", "Skew", "Kurt", "Vari", "Zscore", "Corr"
    }:
        return base + integers[0] - 1
    return base
