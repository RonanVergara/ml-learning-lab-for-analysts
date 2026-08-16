from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ml_lab.content import load_curriculum
from ml_lab.lab_contracts import BoundedPythonLabConfig
from ml_lab.runner import CheckpointContract, RunRequest, request_from_lab, run_code


def _request(
    source: str,
    *,
    setup: str = "",
    exports: list[str] | None = None,
    checkpoints: list[CheckpointContract] | None = None,
    assignments: list[str] | None = None,
    calls: list[str] | None = None,
    attributes: list[str] | None = None,
    max_source_bytes: int = 8_192,
    timeout_seconds: float = 2.0,
    output_limit_bytes: int = 1_024,
) -> RunRequest:
    return RunRequest(
        lab_id="runner-test",
        source=source,
        trusted_setup_code=setup,
        trusted_setup_exports=exports or [],
        checkpoints=checkpoints
        or [
            CheckpointContract(
                id="RUN-C1",
                label="Result exists",
                expression="result is not None",
                pass_message="Result is available.",
                fail_message="Create a result.",
            )
        ],
        allowed_assignments=assignments or ["result"],
        allowed_calls=calls or [],
        allowed_attributes=attributes or [],
        min_editable_lines=1,
        max_editable_lines=1,
        max_source_bytes=max_source_bytes,
        timeout_seconds=timeout_seconds,
        output_limit_bytes=output_limit_bytes,
    )


def _process_exists(pid: int) -> bool:
    completed = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return f'"{pid}"' in completed.stdout


def _wait_for_process_exit(pid: int, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_exists(pid):
            return True
        time.sleep(0.1)
    return not _process_exists(pid)


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
    assert [check["id"] for check in result.checks] == [
        "F1-LAB-C1",
        "F1-LAB-C2",
        "F1-LAB-C3",
    ]
    assert all(check["message"] for check in result.checks)
    assert result.worker_pid is not None
    assert not Path(result.working_directory).exists()


def test_incorrect_values_return_checkpoint_feedback() -> None:
    lab = load_curriculum().lessons[0].lab
    configuration = BoundedPythonLabConfig.model_validate(lab.configuration)
    result = run_code(request_from_lab(lab, configuration.default_code))
    assert result.status == "check_failed"
    assert not result.passed
    assert all(not check["passed"] for check in result.checks)
    assert all(check["message"] for check in result.checks)


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


def test_future_pandas_lab_executes_trusted_setup_and_checkpoint_contracts() -> None:
    request = _request(
        'average_handle_time = cases["handle_time"].mean()',
        setup=(
            "import pandas as pd\n"
            'cases = pd.DataFrame({"handle_time": [10.0, 20.0, 30.0]})'
        ),
        exports=["cases"],
        checkpoints=[
            CheckpointContract(
                id="PANDAS-C1",
                label="Mean handle time",
                expression="bool(abs(average_handle_time - 20.0) < 1e-9)",
                pass_message="The DataFrame mean is correct.",
                fail_message="Select handle_time and call mean().",
            )
        ],
        assignments=["average_handle_time"],
        attributes=["mean"],
    )
    result = run_code(request)
    assert result.status == "passed"
    assert result.checks == [
        {
            "id": "PANDAS-C1",
            "name": "Mean handle time",
            "passed": True,
            "message": "The DataFrame mean is correct.",
        }
    ]


def test_missing_trusted_setup_export_is_a_contract_error() -> None:
    result = run_code(_request("result = 1", exports=["cases"]))
    assert result.status == "contract_error"
    assert "cases" in result.error


def test_checkpoint_must_return_an_explicit_python_boolean() -> None:
    checkpoint = CheckpointContract(
        id="RUN-C-NONBOOL",
        label="Invalid checkpoint",
        expression="1",
        pass_message="unused",
        fail_message="unused",
    )
    result = run_code(_request("result = 1", checkpoints=[checkpoint]))
    assert result.status == "contract_error"
    assert "must return a Python boolean" in result.error


def test_source_size_is_rejected_before_worker_start() -> None:
    result = run_code(_request('result = "' + ("x" * 200) + '"', max_source_bytes=64))
    assert result.status == "validation_error"
    assert "bytes" in result.error
    assert result.worker_pid is None


def test_worker_enforces_output_limit() -> None:
    result = run_code(
        _request(
            'result = print("x" * 4096)',
            calls=["print"],
            output_limit_bytes=128,
        )
    )
    assert result.status == "output_limit"
    assert "too much output" in result.error
    assert result.worker_pid is not None
    assert not Path(result.working_directory).exists()


def test_long_running_allowlisted_expression_times_out_and_cleans_worker() -> None:
    request = _request(
        "result = sum(range(10 ** 10))",
        calls=["sum", "range"],
        timeout_seconds=0.2,
    )
    result = run_code(request)
    assert result.status == "timeout"
    assert "stopped" in result.error
    assert result.worker_pid is not None
    assert _wait_for_process_exit(result.worker_pid)
    assert not Path(result.working_directory).exists()


def test_timeout_terminates_descendant_process_tree(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    setup = "\n".join(
        [
            "import subprocess",
            "import sys",
            'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])',
            f"open({json.dumps(str(child_pid_file))}, 'w').write(str(child.pid))",
        ]
    )
    result = run_code(
        _request(
            "result = sum(range(10 ** 10))",
            setup=setup,
            calls=["sum", "range"],
            timeout_seconds=0.5,
        )
    )
    assert result.status == "timeout"
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(child_pid)
    assert not Path(result.working_directory).exists()
