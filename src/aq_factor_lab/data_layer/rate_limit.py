from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .config import DataLayerConfig
from .errors import RequestBudgetExceeded


@dataclass
class RequestBudget:
    config: DataLayerConfig
    used: int = 0

    def acquire(self) -> None:
        if self.used >= self.config.max_requests_per_run:
            raise RequestBudgetExceeded(
                "Public data request budget exceeded: "
                f"used={self.used}, max={self.config.max_requests_per_run}"
            )
        self.used += 1

    def sleep_after_request(self) -> None:
        if self.config.sleep_seconds <= 0:
            return
        jitter = random.uniform(0, self.config.sleep_seconds * 0.1)
        time.sleep(self.config.sleep_seconds + jitter)
