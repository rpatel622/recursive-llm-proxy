"""Threshold and regression checks for machine-readable evaluation reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

GATE_FORMAT_VERSION = 1


def load_object(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def check_report(
    report: Dict[str, Any],
    policy: Dict[str, Any],
    baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if policy.get("gate_version") != GATE_FORMAT_VERSION:
        raise ValueError("unsupported evaluation gate version")

    case_count = int(report.get("case_count", 0))
    passed_count = int(report.get("passed_count", 0))
    mean_score = float(report.get("mean_score", 0.0))
    pass_rate = passed_count / case_count if case_count else 1.0

    failures = []
    minimum_score = float(policy.get("minimum_mean_score", 0.0))
    minimum_pass_rate = float(policy.get("minimum_pass_rate", 0.0))
    if mean_score < minimum_score:
        failures.append(f"mean score {mean_score:.4f} is below {minimum_score:.4f}")
    if pass_rate < minimum_pass_rate:
        failures.append(f"pass rate {pass_rate:.4f} is below {minimum_pass_rate:.4f}")

    maximum_score_drop = float(policy.get("maximum_mean_score_drop", 0.0))
    if baseline is not None:
        baseline_score = float(baseline.get("mean_score", 0.0))
        score_drop = baseline_score - mean_score
        if score_drop > maximum_score_drop:
            failures.append(
                f"mean score dropped by {score_drop:.4f}; maximum allowed is {maximum_score_drop:.4f}"
            )

    return {
        "gate_version": GATE_FORMAT_VERSION,
        "passed": not failures,
        "mean_score": mean_score,
        "pass_rate": pass_rate,
        "failures": failures,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Apply quality gates to an evaluation report")
    parser.add_argument("report", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = check_report(
        load_object(args.report),
        load_object(args.policy),
        load_object(args.baseline) if args.baseline else None,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
