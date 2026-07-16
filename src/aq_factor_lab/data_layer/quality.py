from __future__ import annotations

from pathlib import Path

import pandas as pd

from .errors import DataQualityError


def append_quality_warning(log_dir: Path, warning: dict[str, object]) -> None:
    path = log_dir / "data_layer_quality_warnings.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([warning])
    if path.exists():
        row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        row.to_csv(path, index=False, encoding="utf-8-sig")


def append_failure(log_dir: Path, failure: dict[str, object]) -> None:
    path = log_dir / "data_layer_failures.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([failure])
    if path.exists():
        row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        row.to_csv(path, index=False, encoding="utf-8-sig")


def validate_price_frame(df: pd.DataFrame, *, endpoint: str) -> None:
    required = {"symbol", "date", "open", "high", "low", "close", "adjusted", "source"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise DataQualityError(f"{endpoint} missing required columns: {missing}")
    if df["date"].isna().any():
        raise DataQualityError(f"{endpoint} contains unparsable dates")
    duplicated = df.duplicated(["symbol", "date"])
    if duplicated.any():
        raise DataQualityError(f"{endpoint} contains duplicate symbol/date rows")
    if (df["high"] < df["low"]).any():
        raise DataQualityError(f"{endpoint} contains high < low rows")
    for column in ["volume", "amount"]:
        if column in df.columns and (df[column].dropna() < 0).any():
            raise DataQualityError(f"{endpoint} contains negative {column}")
