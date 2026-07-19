from rlm_proxy.stack_health import HealthCheck, check_stack


def test_required_failure_marks_stack_unavailable() -> None:
    result = check_stack(
        [
            HealthCheck("proxy", True, lambda: {"status": "ok"}),
            HealthCheck("knowledge", True, lambda: {"status": "down"}),
        ]
    )

    assert result["status"] == "unavailable"
    assert result["ready"] is False


def test_optional_failure_marks_stack_degraded() -> None:
    def fail():
        raise RuntimeError("offline")

    result = check_stack(
        [
            HealthCheck("proxy", True, lambda: {"status": "ready"}),
            HealthCheck("jobs", False, fail),
        ]
    )

    assert result["status"] == "degraded"
    assert result["checks"][1]["error"] == "offline"


def test_all_healthy_is_ready() -> None:
    result = check_stack([HealthCheck("proxy", True, lambda: {"status": "healthy"})])
    assert result["status"] == "ready"
