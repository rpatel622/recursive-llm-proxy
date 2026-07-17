"""Tests for bounded rolling-window ingestion."""

from __future__ import annotations

import pytest

from rlm_proxy.ingestion import natural_windows, preprocess_dump, should_preprocess
from rlm_proxy.models import IngestionOptions


def test_natural_windows_prefers_paragraph_boundaries():
    text = "First section.\n\nSecond section is longer.\n\nThird section."
    windows = natural_windows(text, window_chars=32, overlap_chars=4)
    assert len(windows) >= 2
    assert "First section." in windows[0]
    assert any("Third section." in item for item in windows)


def test_natural_windows_validates_overlap():
    with pytest.raises(ValueError, match="overlap"):
        natural_windows("text", window_chars=10, overlap_chars=10)


def test_should_preprocess_uses_threshold_and_enabled_flag():
    assert should_preprocess("x" * 20, IngestionOptions(threshold_chars=10)) is True
    assert should_preprocess("x" * 20, IngestionOptions(enabled=False, threshold_chars=10)) is False


@pytest.mark.asyncio
async def test_preprocess_extracts_request_and_preserves_raw_text(monkeypatch):
    calls = []

    async def fake_window_call(
        chunk,
        index,
        total,
        rolling_state,
        model,
        api_base,
        api_key,
        metadata_chars,
    ):
        calls.append((index, chunk, dict(rolling_state)))
        return {
            "request": "Compare the two rollout plans." if index == total else None,
            "title": f"Section {index}",
            "summary": f"Summary {index}",
            "topics": ["rollout"],
            "entities": ["Service A"],
            "facts": [f"Fact {index}"],
            "boundary": "paragraph boundary",
            "rolling_state": {
                "topics": ["rollout"],
                "entities": ["Service A"],
                "constraints": ["zero downtime"],
            },
        }

    monkeypatch.setattr("rlm_proxy.ingestion._window_call", fake_window_call)
    text = ("Plan A details.\n\n" * 20) + "Compare the two rollout plans."
    options = IngestionOptions(
        threshold_chars=1,
        window_chars=120,
        overlap_chars=10,
        max_windows=20,
    )
    result = await preprocess_dump(
        text,
        options,
        model="openai/local",
        api_base="http://localhost:8080/v1",
        api_key="key",
    )

    assert result.query == "Compare the two rollout plans."
    assert result.metadata["window_count"] == len(calls)
    assert "rolling-ingested-user-dump" in result.context
    assert "Plan A details." in result.context
    assert calls[1][2]["topics"] == ["rollout"]


@pytest.mark.asyncio
async def test_preprocess_enforces_window_cap(monkeypatch):
    options = IngestionOptions(
        threshold_chars=1,
        window_chars=20,
        overlap_chars=0,
        max_windows=2,
    )
    with pytest.raises(ValueError, match="maximum"):
        await preprocess_dump(
            "paragraph one.\n\nparagraph two.\n\nparagraph three.\n\nparagraph four.",
            options,
            model="openai/local",
            api_base="http://localhost:8080/v1",
            api_key="key",
        )
