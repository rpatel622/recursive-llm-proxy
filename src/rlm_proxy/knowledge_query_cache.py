"""Bounded TTL cache preserving the existing knowledge client contract."""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from typing import Any, Dict, Tuple

from .ui_clients import KnowledgeApiClient


class CachedKnowledgeApiClient:
    """Cache deterministic search responses and invalidate on knowledge mutations."""

    def __init__(
        self,
        client: KnowledgeApiClient,
        *,
        maximum_entries: int = 128,
        ttl_seconds: float = 60.0,
        clock=time.monotonic,
    ) -> None:
        if maximum_entries <= 0 or ttl_seconds < 0:
            raise ValueError("cache limits must be positive")
        self.client = client
        self.maximum_entries = maximum_entries
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._cache: "OrderedDict[str, Tuple[float, Dict[str, Any]]]" = OrderedDict()

    def search(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        key = json.dumps([query, sorted(kwargs.items())], separators=(",", ":"), default=str)
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] <= self.ttl_seconds:
                self._cache.move_to_end(key)
                return deepcopy(cached[1])
            if cached is not None:
                self._cache.pop(key, None)

        result = self.client.search(query, **kwargs)
        with self._lock:
            self._cache[key] = (now, deepcopy(result))
            self._cache.move_to_end(key)
            while len(self._cache) > self.maximum_entries:
                self._cache.popitem(last=False)
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def enqueue_ingestion(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        result = self.client.enqueue_ingestion(*args, **kwargs)
        self.clear()
        return result

    def delete_document(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        result = self.client.delete_document(*args, **kwargs)
        self.clear()
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)
