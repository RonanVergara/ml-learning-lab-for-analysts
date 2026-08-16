from __future__ import annotations

from ml_lab.content import load_curriculum
from ml_lab.runner import RunRequest, request_from_lab, run_code


def test_valid_bounded_code_passes_all_checkpoints() -> None:
    lab = load_curriculum().lessons[0].lab
    source = "\n".join(
        [
            'yesterday_volume = "reporting"',
            'critical_routing = "rules"',
            'repeat_contact_risk = "ml"',
        ]
    )
    result = run_code(request_from_lab(lab, source))
    assert result.status == "passed"
    assert result.passed
    assert len(result.checks) == 3


def test_incorrect_values_return_checkpoint_feedback() -> None:
    lab = load_curriculum().lessons[0].lab
    result = run_code(request_from_lab(lab, lab.default_code))
    assert result.status == "check_failed"
    assert not result.passed
    assert all(not check["passed"] for check in result.checks)


def test_file_and_import_operations_are_rejected_before_execution() -> None:
    lab = load_curriculum().lessons[0].lab
    source = "\n".join(
        [
            'yesterday_volume = open("secret.txt")',
            'critical_routing = "rules"',
            'repeat_contact_risk = "ml"',
        ]
    )
    result = run_code(request_from_lab(lab, source))
    assert result.status == "validation_error"
    assert "allowlisted" in result.error or "not available" in result.error


def test_long_running_allowlisted_expression_times_out_and_returns() -> None:
    request = RunRequest(
        lab_id="timeout-test",
        source="result = sum(range(10 ** 10))",
        allowed_assignments=["result"],
        allowed_calls=["sum", "range"],
        expected_values={"result": 0},
        min_editable_lines=1,
        max_editable_lines=1,
        timeout_seconds=0.2,
        output_limit_bytes=1024,
    )
    result = run_code(request)
    assert result.status == "timeout"
    assert "stopped" in result.error
