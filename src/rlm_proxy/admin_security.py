"""Admin API scopes and in-process token-bucket rate limits."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from threading import RLock
from typing import Dict, FrozenSet, Iterable, Optional


@dataclass(frozen=True)
class ApiPrincipal:
    principal_id: str
    scopes: FrozenSet[str]

    def require(self, scope: str) -> None:
        if scope not in self.scopes and "admin:*" not in self.scopes:
            raise PermissionError("missing required scope: %s" % scope)


class ApiKeyRegistry:
    """Store only keyed hashes while resolving API principals."""

    def __init__(self, secret: bytes) -> None:
        if not secret:
            raise ValueError("registry secret is required")
        self._secret = secret
        self._principals: Dict[str, ApiPrincipal] = {}

    def register(self, api_key: str, principal_id: str, scopes: Iterable[str]) -> None:
        if not api_key or not principal_id:
            raise ValueError("api key and principal id are required")
        digest = self._digest(api_key)
        self._principals[digest] = ApiPrincipal(principal_id, frozenset(scopes))

    def authenticate(self, api_key: str) -> Optional[ApiPrincipal]:
        candidate = self._digest(api_key)
        for digest, principal in self._principals.items():
            if hmac.compare_digest(candidate, digest):
                return principal
        return None

    def revoke(self, api_key: str) -> bool:
        return self._principals.pop(self._digest(api_key), None) is not None

    def _digest(self, api_key: str) -> str:
        return hmac.new(self._secret, api_key.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Thread-safe per-principal rate limiter with deterministic injection points."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("capacity and refill rate must be positive")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._lock = RLock()
        self._buckets: Dict[str, _Bucket] = {}

    def allow(self, principal_id: str, cost: float = 1.0, now: Optional[float] = None) -> bool:
        if cost <= 0 or cost > self.capacity:
            raise ValueError("cost must be positive and not exceed capacity")
        current = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._buckets.get(principal_id)
            if bucket is None:
                bucket = _Bucket(float(self.capacity), current)
                self._buckets[principal_id] = bucket
            elapsed = max(0.0, current - bucket.updated_at)
            bucket.tokens = min(
                float(self.capacity), bucket.tokens + elapsed * self.refill_per_second
            )
            bucket.updated_at = current
            if bucket.tokens < cost:
                return False
            bucket.tokens -= cost
            return True


__all__ = ["ApiKeyRegistry", "ApiPrincipal", "TokenBucketLimiter"]
