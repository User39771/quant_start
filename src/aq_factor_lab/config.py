from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DEFAULT_SLEEP_SECONDS = 10.0


@dataclass(frozen=True)
class ResearchConfig:
    root_dir: Path
    start_date: date
    end_date: date
    holding_days: int = 20
    min_history_days: int = 120
    group_count: int = 5
    max_symbols: int | None = None
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS
    use_cache: bool = True
    price_cache_only: bool = True
    cache_only: bool = False

    @property
    def cache_dir(self) -> Path:
        return self.root_dir / "data" / "cache"

    @property
    def processed_dir(self) -> Path:
        return self.root_dir / "data" / "processed"

    @property
    def report_dir(self) -> Path:
        return self.root_dir / "reports"


def default_dates(years: int = 3) -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=365 * years + 90)
    return start, end


def yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")
