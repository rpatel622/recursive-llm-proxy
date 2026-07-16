"""Tests for process-local proxy monitoring metrics."""

from rlm_proxy.metrics import ProxyMetrics


def test_metrics_aggregate_success_clarification_and_failure():
    metrics = ProxyMetrics(recent_limit=2)

    metrics.record(
        request_id="one",
        status="ok",
        latency_ms=10.0,
        routing={"status": "route", "slot_slug": "engineering"},
        stats={"prompt_tokens": 12, "completion_tokens": 3},
    )
    metrics.record(
        request_id="two",
        status="clarify",
        latency_ms=20.0,
        routing={"status": "clarify"},
    )
    metrics.record(
        request_id="three",
        status="error",
        latency_ms=30.0,
        error="provider unavailable",
    )

    snapshot = metrics.snapshot()

    assert snapshot["total_requests"] == 3
    assert snapshot["successful_requests"] == 1
    assert snapshot["clarifications"] == 1
    assert snapshot["failed_requests"] == 1
    assert snapshot["average_latency_ms"] == 20.0
    assert snapshot["prompt_tokens"] == 12
    assert snapshot["completion_tokens"] == 3
    assert snapshot["total_tokens"] == 15
    assert [item["request_id"] for item in snapshot["recent"]] == ["three", "two"]


def test_metrics_reject_invalid_limits_and_latency():
    try:
        ProxyMetrics(recent_limit=0)
    except ValueError as exc:
        assert "recent_limit" in str(exc)
    else:
        raise AssertionError("expected invalid recent_limit to fail")

    metrics = ProxyMetrics()
    try:
        metrics.record(request_id="bad", status="error", latency_ms=-1)
    except ValueError as exc:
        assert "latency_ms" in str(exc)
    else:
        raise AssertionError("expected negative latency to fail")
