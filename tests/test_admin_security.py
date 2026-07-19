import pytest

from rlm_proxy.admin_security import ApiKeyRegistry, TokenBucketLimiter


def test_registry_authenticates_scoped_principal() -> None:
    registry = ApiKeyRegistry(b"secret")
    registry.register("key-1", "operator", ["catalog:read", "knowledge:write"])

    principal = registry.authenticate("key-1")

    assert principal is not None
    principal.require("catalog:read")
    with pytest.raises(PermissionError, match="missing required scope"):
        principal.require("catalog:write")


def test_registry_revokes_without_storing_plaintext() -> None:
    registry = ApiKeyRegistry(b"secret")
    registry.register("key-1", "operator", ["admin:*"])

    assert registry.revoke("key-1") is True
    assert registry.authenticate("key-1") is None


def test_token_bucket_refills_deterministically() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1.0)

    assert limiter.allow("operator", now=0.0) is True
    assert limiter.allow("operator", now=0.0) is True
    assert limiter.allow("operator", now=0.0) is False
    assert limiter.allow("operator", now=1.0) is True


def test_invalid_cost_is_rejected() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1.0)
    with pytest.raises(ValueError, match="cost"):
        limiter.allow("operator", cost=3)
