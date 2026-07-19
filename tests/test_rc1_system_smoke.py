from pathlib import Path

import httpx
import pytest

from rlm_proxy.admin_security import ApiKeyRegistry, TokenBucketLimiter
from rlm_proxy.audit_log import AuditLog
from rlm_proxy.control_plane import create_control_plane
from rlm_proxy.conversation_memory import ConversationMemoryStore
from rlm_proxy.release_manifest import build_manifest, verify_manifest
from rlm_proxy.stack_health import HealthCheck


@pytest.mark.asyncio
async def test_rc1_persistence_control_plane_and_manifest(tmp_path: Path) -> None:
    memory_path = tmp_path / "memory.sqlite3"
    memory = ConversationMemoryStore(str(memory_path))
    snapshot = memory.create("rc1")
    snapshot = memory.append("rc1", "user", "remember this", snapshot.revision)
    snapshot = memory.append("rc1", "assistant", "remembered", snapshot.revision)

    restarted = ConversationMemoryStore(str(memory_path)).get("rc1")
    assert [message.content for message in restarted.messages] == ["remember this", "remembered"]

    keys = ApiKeyRegistry(b"rc1-test-secret")
    keys.register("rc1-key", "release-test", ["admin:*"])
    audit = AuditLog(tmp_path / "audit.jsonl")
    app = create_control_plane(
        checks=[HealthCheck("proxy", True, lambda: {"status": "ready"})],
        key_registry=keys,
        limiter=TokenBucketLimiter(20, 20.0),
        audit_log=audit,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://rc1") as client:
        ready = await client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["ready"] is True
        exported = await client.get(
            "/v1/admin/catalog/export",
            headers={"Authorization": "Bearer rc1-key"},
        )
        assert exported.status_code == 200
        verified = await client.get(
            "/v1/admin/audit/verify",
            headers={"Authorization": "Bearer rc1-key"},
        )
        assert verified.json()["verified"] is True

    assert audit.verify() is True

    artifact = tmp_path / "artifact.whl"
    artifact.write_bytes(b"rc1-artifact")
    manifest = build_manifest(tmp_path, [artifact.name])
    assert verify_manifest(tmp_path, manifest) == []
