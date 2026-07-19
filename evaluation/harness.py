"""Deterministic routing, retrieval, and grounding evaluation helpers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

FIXTURE_VERSION = 1


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    passed: bool
    score: float
    details: Dict[str, Any]


@dataclass(frozen=True)
class EvaluationReport:
    fixture_version: int
    case_count: int
    passed_count: int
    mean_score: float
    cases: List[CaseResult]

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["cases"] = [asdict(case) for case in self.cases]
        return value


def load_fixture(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fixture root must be an object")
    if value.get("fixture_version") != FIXTURE_VERSION:
        raise ValueError(
            f"unsupported fixture version: {value.get('fixture_version')}; expected {FIXTURE_VERSION}"
        )
    cases = value.get("cases")
    if not isinstance(cases, list):
        raise ValueError("fixture cases must be a list")
    seen: Set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("fixture cases must be objects")
        case_id = case.get("id")
        category = case.get("category")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("every case requires a non-empty id")
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        if category not in {"routing", "retrieval", "grounding"}:
            raise ValueError(f"unsupported category for {case_id}: {category}")
    return value


def _set_score(expected: Sequence[str], actual: Sequence[str]) -> float:
    expected_set = set(expected)
    actual_set = set(actual)
    if not expected_set:
        return 1.0 if not actual_set else 0.0
    return len(expected_set & actual_set) / len(expected_set | actual_set)


def evaluate_case(case: Dict[str, Any], actual: Dict[str, Any]) -> CaseResult:
    category = str(case["category"])
    expected = dict(case.get("expected") or {})
    details: Dict[str, Any] = {"expected": expected, "actual": actual}

    if category == "routing":
        slot_match = actual.get("slot_slug") == expected.get("slot_slug")
        stream_score = _set_score(
            [str(item) for item in expected.get("workstream_slugs", [])],
            [str(item) for item in actual.get("workstream_slugs", [])],
        )
        score = (float(slot_match) + stream_score) / 2.0
        passed = slot_match and stream_score == 1.0
    elif category == "retrieval":
        score = _set_score(
            [str(item) for item in expected.get("document_ids", [])],
            [str(item) for item in actual.get("document_ids", [])],
        )
        passed = score >= float(case.get("minimum_score", 1.0))
    else:
        expected_citations = [str(item) for item in expected.get("citation_ids", [])]
        actual_citations = [str(item) for item in actual.get("citation_ids", [])]
        citation_score = _set_score(expected_citations, actual_citations)
        answer = str(actual.get("answer", ""))
        required_phrases = [str(item) for item in expected.get("answer_contains", [])]
        phrase_score = (
            sum(1 for phrase in required_phrases if phrase.lower() in answer.lower())
            / len(required_phrases)
            if required_phrases
            else 1.0
        )
        score = (citation_score + phrase_score) / 2.0
        passed = citation_score == 1.0 and phrase_score == 1.0

    return CaseResult(str(case["id"]), category, passed, score, details)


def evaluate(fixture: Dict[str, Any], actual_results: Dict[str, Dict[str, Any]]) -> EvaluationReport:
    results = [
        evaluate_case(case, actual_results.get(str(case["id"]), {}))
        for case in fixture["cases"]
    ]
    mean_score = sum(case.score for case in results) / len(results) if results else 1.0
    return EvaluationReport(
        fixture_version=FIXTURE_VERSION,
        case_count=len(results),
        passed_count=sum(1 for case in results if case.passed),
        mean_score=mean_score,
        cases=results,
    )


def _load_actual(path: Path) -> Dict[str, Dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("actual result root must be an object keyed by case id")
    return {str(key): dict(item) for key, item in value.items()}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate routing, retrieval, and grounding results")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = evaluate(load_fixture(args.fixture), _load_actual(args.actual))
    encoded = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report.passed_count == report.case_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
