"""Tests for the retrieval profiling baseline format."""

from __future__ import annotations

import pytest

from benchmarks.knowledge_profile import summarize


def test_summarize_reports_latency_distribution() -> None:
    summary = summarize([5.0, 1.0, 3.0, 2.0, 4.0])

    assert summary.count == 5
    assert summary.minimum_ms == 1.0
    assert summary.median_ms == 3.0
    assert summary.p95_ms == 5.0
    assert summary.maximum_ms == 5.0
    assert summary.mean_ms == pytest.approx(3.0)


def test_summarize_empty_samples_is_stable() -> None:
    summary = summarize([])

    assert summary.count == 0
    assert summary.mean_ms == 0.0
