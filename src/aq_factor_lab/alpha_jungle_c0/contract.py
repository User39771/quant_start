from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

FINAL_TEST_LOCKED = True
LABEL_HORIZON_SESSIONS = 11
MIN_DAILY_ACTIVE_CONSTITUENT_FRACTION = 0.80
MIN_DAILY_VALID_INSTRUMENTS = 20
MIN_FORMULA_SESSION_COVERAGE = 0.90


class FinalTestLockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class C0Contract:
    experiment_id: str = "ALPHA_JUNGLE_QLIB_C0"
    train_start: date = date(2011, 1, 1)
    train_end: date = date(2018, 12, 31)
    validation_start: date = date(2019, 1, 1)
    validation_end: date = date(2020, 12, 31)
    final_test_start: date = date(2021, 1, 1)
    final_test_end: date = date(2024, 11, 30)
    label_expression: str = "Ref($close,-11)/Ref($close,-1)-1"
    universe: str = "csi300"
    valid_evaluations_per_arm: int = 100
    checkpoints: tuple[int, ...] = (10, 20, 50, 100)


C0 = C0Contract()


def label_eligible_sessions(calendar: list[date], split_start: date, split_end: date) -> list[date]:
    """Return signal sessions whose t+11 label endpoint remains in the split."""
    sessions = sorted(day for day in calendar if split_start <= day <= split_end)
    return sessions[:-LABEL_HORIZON_SESSIONS] if len(sessions) > LABEL_HORIZON_SESSIONS else []


def assert_period_allowed(
    start: date, end: date, *, final_test_locked: bool = FINAL_TEST_LOCKED
) -> None:
    """Fail before any provider read that overlaps the frozen final-test interval."""
    if start > end:
        raise ValueError("start must not be after end")
    overlaps = start <= C0.final_test_end and end >= C0.final_test_start
    if final_test_locked and overlaps:
        raise FinalTestLockedError(
            f"FINAL_TEST_LOCKED: requested {start.isoformat()}..{end.isoformat()} overlaps "
            f"{C0.final_test_start.isoformat()}..{C0.final_test_end.isoformat()}"
        )


def alpha158_request(start: date, end: date) -> dict[str, object]:
    assert_period_allowed(start, end)
    return {
        "handler": "Alpha158",
        "instruments": C0.universe,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "label": C0.label_expression,
    }


def inspect_provider_layout(provider_uri: Path) -> dict[str, object]:
    """Read only filesystem metadata; never loads features or computes outcomes."""
    provider_uri = provider_uri.resolve()
    required = {name: provider_uri / name for name in ("calendars", "instruments", "features")}
    return {
        "provider_uri": str(provider_uri),
        "exists": provider_uri.is_dir(),
        "components": {name: path.is_dir() for name, path in required.items()},
        "csi300_membership_file": str(required["instruments"] / "csi300.txt"),
        "csi300_membership_available": (required["instruments"] / "csi300.txt").is_file(),
    }
