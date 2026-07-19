from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None,
    reason="proxy extras are not installed",
)


def test_control_plane_exposes_secured_routes(tmp_path: Path) -> None:
    from rlm_proxy.admin_security import ApiKeyRegistry, TokenBucketLimiter
    from rlm_proxy.audit_log import AuditLog
    from rlm_proxy.control_plane import create_control_plane
    from rlm_proxy.stack_health import HealthCheck

    keys = ApiKeyRegistry(b"secret")
    keys.register("key", "operator", ["admin:*"])
    app = create_control_plane(
        checks=[HealthCheck("proxy", True, lambda: {"status": "ok"})],
        key_registry=keys,
        limiter=TokenBucketLimiter(10, 10),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
    )
    paths = {route.path for route in app.routes}
    assert "/readyz" in paths
    assert "/v1/admin/catalog/export" in paths
    assert "/v1/admin/catalog/import" in paths
    assert "/v1/admin/audit/verify" in paths
