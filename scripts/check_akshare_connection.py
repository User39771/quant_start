from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.config import DEFAULT_SLEEP_SECONDS
from aq_factor_lab.data import safe_fetch


def default_fetcher(ak_module: Any) -> Callable[[], Any]:
    return lambda: ak_module.stock_zh_a_hist(
        symbol="600519",
        period="daily",
        adjust="qfq",
        timeout=20,
    )


def run_diagnostics(
    *,
    ak_module: Any,
    requests_module: Any,
    fetcher: Callable[[], Any] | None = None,
    repeats: int = 5,
    repeat_sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
) -> dict[str, Any]:
    probe = fetcher or default_fetcher(ak_module)
    result: dict[str, Any] = {
        "python_executable": sys.executable,
        "akshare_version": getattr(ak_module, "__version__", "unknown"),
        "requests_version": getattr(requests_module, "__version__", "unknown"),
        "single_request_ok": False,
        "single_request_error": "",
        "success_count": 0,
        "total_count": repeats,
        "success_rate": 0.0,
        "errors": [],
    }

    try:
        safe_fetch(
            "diagnostic single A-share request",
            probe,
            max_attempts=1,
            base_sleep=0,
            random_sleep_range=(0, 0),
        )
        result["single_request_ok"] = True
    except Exception as exc:
        result["single_request_error"] = f"{type(exc).__name__}: {exc}"

    success_count = 0
    errors: list[str] = []
    for index in range(1, repeats + 1):
        try:
            safe_fetch(
                f"diagnostic repeated A-share request {index}",
                probe,
                max_attempts=1,
                base_sleep=0,
                random_sleep_range=(0, 0),
            )
            success_count += 1
        except Exception as exc:
            errors.append(f"{index}: {type(exc).__name__}: {exc}")
        if index < repeats and repeat_sleep_seconds > 0:
            time.sleep(repeat_sleep_seconds)

    result["success_count"] = success_count
    result["success_rate"] = success_count / repeats if repeats else 0.0
    result["errors"] = errors
    return result


def main() -> None:
    import akshare as ak
    import requests

    result = run_diagnostics(ak_module=ak, requests_module=requests)
    print(f"Python executable: {result['python_executable']}")
    print(f"AkShare version: {result['akshare_version']}")
    print(f"requests version: {result['requests_version']}")
    print(f"Single A-share request OK: {result['single_request_ok']}")
    if result["single_request_error"]:
        print(f"Single A-share request error: {result['single_request_error']}")
    print(
        "Repeated A-share request success rate: "
        f"{result['success_count']}/{result['total_count']} ({result['success_rate']:.1%})"
    )
    if result["errors"]:
        print("Repeated request errors:")
        for error in result["errors"]:
            print(f"- {error}")


if __name__ == "__main__":
    main()
