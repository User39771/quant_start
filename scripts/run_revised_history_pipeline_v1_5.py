from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


FREEZE_DATE = "2026-07-11"
OLD_PANEL_END = "2026-06-16"


def versioned_name(name: str) -> str:
    return name.replace("_v1_2", "_v1_5").replace("_v1_4", "_v1_5")


def classify_periods(frame: pd.DataFrame, old_end: str = OLD_PANEL_END, freeze: str = FREEZE_DATE) -> pd.DataFrame:
    out = frame.copy()
    start = pd.to_datetime(out["rebalance_date"])
    end = pd.to_datetime(out["next_rebalance_date"])
    out["sample_regime"] = "pipeline_unseen_retrospective_extension"
    out.loc[end.le(pd.Timestamp(old_end)), "sample_regime"] = "revised_history"
    out.loc[start.gt(pd.Timestamp(freeze)), "sample_regime"] = "prospective_holdout"
    out["freeze_date"] = freeze
    out["prospective_flag"] = start.gt(pd.Timestamp(freeze))
    return out


def _run(command: list[str], cwd: Path, allowed_exit_codes: tuple[int, ...] = (0,)) -> int:
    completed = subprocess.run(command, cwd=cwd, text=True)
    if completed.returncode not in allowed_exit_codes:
        raise RuntimeError(f"failed ({completed.returncode}): {' '.join(command)}")
    return completed.returncode


def run(root: Path) -> None:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="quant_v1_5_") as directory:
        stage = Path(directory)
        (stage / "scripts").mkdir(parents=True)
        (stage / "data" / "processed").mkdir(parents=True)
        (stage / "reports").mkdir()
        (stage / "scripts" / "__init__.py").write_text("", encoding="ascii")
        for name in (
            "run_adjusted_stock_pool_baseline_v1_2.py",
            "analyze_baseline_attribution_v1_2.py",
            "test_lowvol20_hypothesis_v1_4.py",
        ):
            shutil.copy2(root / "scripts" / name, stage / "scripts" / name)
        data = stage / "data" / "processed"
        shutil.copy2(root / "data" / "processed" / "adjusted_price_panel_v1_5.csv", data / "adjusted_price_panel_v1_2.csv")
        shutil.copy2(root / "data" / "processed" / "hybrid_benchmark_panel_v1_5.csv", data / "hybrid_benchmark_panel_v1_2.csv")
        shutil.copy2(root / "data" / "processed" / "research_universe_lowvol_freeze_20260711.csv", data / "backtest_universe_research_v1_2.csv")
        expanded = root / "data" / "processed" / "backtest_universe_expanded_only_v1_2.csv"
        if expanded.exists():
            shutil.copy2(expanded, data / expanded.name)

        _run([sys.executable, "scripts/run_adjusted_stock_pool_baseline_v1_2.py"], stage)
        _run([sys.executable, "scripts/analyze_baseline_attribution_v1_2.py"], stage)
        _run([sys.executable, "scripts/test_lowvol20_hypothesis_v1_4.py", "--project-root", str(stage)], stage, (0, 1))

        for source in list((stage / "reports").iterdir()) + list(data.glob("lowvol20_factor_panel_v1_4.csv")):
            destination_dir = root / ("data/processed" if source.parent == data else "reports")
            destination = destination_dir / versioned_name(source.name)
            shutil.copy2(source, destination)

    versioned_csvs = list((root / "reports").glob("*_v1_5.csv")) + [root / "data/processed/lowvol20_factor_panel_v1_5.csv"]
    for path in versioned_csvs:
        frame = pd.read_csv(path, dtype=str)
        if {"rebalance_date", "next_rebalance_date"}.issubset(frame.columns):
            classify_periods(frame).to_csv(path, index=False)
    for path in (root / "reports").glob("*_v1_5.md"):
        if path.name.startswith(("adjusted_stock_pool", "baseline_attribution", "factor_lowvol20")):
            text = path.read_text(encoding="utf-8").replace("v1.2", "v1.5").replace("v1.4", "v1.5")
            path.write_text(text, encoding="utf-8")

    prospective = root / "reports" / "lowvol20_prospective_periods_v1_5.csv"
    if not prospective.exists():
        pd.DataFrame(columns=["rebalance_date", "next_rebalance_date", "status"]).to_csv(prospective, index=False)
    log = root / "reports" / "lowvol20_prospective_log_v1_5.md"
    if not log.exists():
        log.write_text(
            "# LOWVOL20 Prospective Log v1.5\n\nstatus=waiting_for_complete_period\nprospective_period_count=0\nformal_performance_conclusion_allowed=false\n",
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    run(args.project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
