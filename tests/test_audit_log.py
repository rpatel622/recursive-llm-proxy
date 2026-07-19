import json
from pathlib import Path

from rlm_proxy.audit_log import AuditLog


def test_audit_log_builds_verifiable_chain(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    first = log.append("operator", "catalog.import", "catalog", "success", timestamp=1.0)
    second = log.append("operator", "knowledge.delete", "doc-1", "success", timestamp=2.0)

    assert first.sequence == 0
    assert second.previous_hash == first.event_hash
    assert log.verify() is True


def test_audit_log_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("operator", "catalog.export", "catalog", "success", timestamp=1.0)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["outcome"] = "failure"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert log.verify() is False


def test_audit_log_requires_identity(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    try:
        log.append("", "action", "resource", "success")
    except ValueError as exc:
        assert "required" in str(exc)
    else:
        raise AssertionError("expected ValueError")
