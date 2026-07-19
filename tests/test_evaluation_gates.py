"""Tests for evaluation thresholds and regression checks."""

from evaluation.gates import check_report


def test_gate_passes_report_above_thresholds() -> None:
    result = check_report(
        {"case_count": 10, "passed_count": 9, "mean_score": 0.95},
        {
            "gate_version": 1,
            "minimum_mean_score": 0.9,
            "minimum_pass_rate": 0.9,
            "maximum_mean_score_drop": 0.02,
        },
        {"mean_score": 0.96},
    )
    assert result["passed"] is True
    assert result["failures"] == []


def test_gate_reports_threshold_and_regression_failures() -> None:
    result = check_report(
        {"case_count": 10, "passed_count": 7, "mean_score": 0.80},
        {
            "gate_version": 1,
            "minimum_mean_score": 0.9,
            "minimum_pass_rate": 0.9,
            "maximum_mean_score_drop": 0.02,
        },
        {"mean_score": 0.95},
    )
    assert result["passed"] is False
    assert len(result["failures"]) == 3
