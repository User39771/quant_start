from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data_layer import DataLayerConfig, configure_data_layer, get_daily_price
from aq_factor_lab.data_layer.cache import build_query_payload, cache_paths, query_key


def main() -> None:
    """Run one conservative public-data request and then prove exact-cache reuse."""
    config = DataLayerConfig(root_dir=ROOT, sleep_seconds=1.0, max_requests_per_run=1)
    configure_data_layer(config)

    payload = build_query_payload(
        endpoint="daily_price",
        config=config,
        symbol="600519",
        start="2026-06-01",
        end="2026-06-05",
        adjusted=True,
    )
    key = query_key(payload)
    paths = cache_paths(config, "daily_price", key)

    initial_status = "cache_hit" if paths.clean.exists() else "cache_miss"
    print(f"initial_status={initial_status}")
    print(f"query_key={key}")
    print(f"clean_cache={paths.clean}")

    first = get_daily_price("600519", "2026-06-01", "2026-06-05", adjusted=True)
    print(f"first_call_rows={len(first)}")
    print(f"after_first_call_cache_exists={paths.clean.exists()}")

    second = get_daily_price("600519", "2026-06-01", "2026-06-05", adjusted=True)
    print(f"second_call_rows={len(second)}")
    print("second_call_expected=exact_clean_cache_hit_no_live_request")


if __name__ == "__main__":
    main()
