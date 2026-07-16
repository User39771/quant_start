from __future__ import annotations


class DataLayerError(RuntimeError):
    """Base error for public data-layer failures."""


class CacheMissError(DataLayerError):
    """Raised when cache-only mode cannot satisfy an exact query."""


class RequestBudgetExceeded(DataLayerError):
    """Raised before a live request would exceed the run request budget."""


class PublicDataFetchError(DataLayerError):
    """Raised when a public data source request fails after retries."""


class DataQualityError(DataLayerError):
    """Raised when fetched data cannot be standardized safely."""
