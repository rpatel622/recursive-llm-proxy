"""Tests for deterministic evaluation scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.harness import evaluate, load_fixture


def test_smoke_fixture_passes() -> None:
    fixture = load_fixture(Path("evaluation/fixtures/smoke-v1.json"))
    actual = json.loads(Path("evaluation/fixtures/smoke-results.json").read_text())
    report = evaluate(fixture, actual)

    assert report.case_count == 3
    assert report.passed_count == 3
    assert report.mean_score == 1.0


def test_fixture_version_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text('{"fixture_version": 2, "cases": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported fixture version"):
        load_fixture(path)


def test_missing_actual_result_fails_case() -> None:
    fixture = {
        "fixture_version": 1,
        "cases": [
            {
                "id": "route",
                "category": "routing",
                "expected": {"slot_slug": "engineering", "workstream_slugs": ["prod"]},
            }
        ],
    }
    report = evaluate(fixture, {})

    assert report.passed_count == 0
    assert report.cases[0].score == 0.0
