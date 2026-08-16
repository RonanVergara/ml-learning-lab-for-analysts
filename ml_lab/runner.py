from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .content import LabSpec
from .lab_contracts import BoundedPythonLabConfig


class RunnerValidationError(ValueError):
    """Learner code does not match the bounded lab policy."""


@dataclass(frozen=True)
class CheckpointContract:
    id: str
    label: str
    expression: str
    pass_message: str
    fail_message: str


@dataclass(frozen=True)
class RunRequest:
    lab_id: str
    source: str
    trusted_setup_code: str
    trusted_setup_exports: list[str]
    checkpoints: list[CheckpointContract]
    allowed_assignments: list[str]
    allowed_calls: list[str]
    allowed_attributes: list[str]
    min_editable_lines: int
    max_editable_lines: int
    max_source_bytes: int = 8_192
    timeout_seconds: float = 5.0
    output_limit_bytes: int = 65_536


@dataclass(frozen=True)
class RunResult:
    status: str
    stdout: str = ""
    error: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    worker_pid: int | None = None
    working_directory: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed" and all(check.get("passed") for check in self.checks)


SAFE_CALLS = {"abs", "len", "max", "min", "print", "range", "round", "sorted", "sum"}
SAFE_ATTRIBUTES = {
    "agg",
    "astype",
    "count",
    "fillna",
    "groupby",
    "head",
    "isna",
    "mean",
    "round",
    "sort_values",
    "sum",
    "value_counts",
}
ALLOWED_NODES = {
    ast.Module,
    ast.Assign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.Expr,
    ast.Call,
    ast.keyword,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UnaryOp,
    ast.USub,
    ast.UAdd,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
}


def validate_source(request: RunRequest) -> ast.Module:
    source_size = len(request.source.encode("utf-8"))
    if source_size > request.max_source_bytes:
        raise RunnerValidationError(
            f"This editable region is {source_size} bytes; the lab limit is {request.max_source_bytes}."
        )
    lines = [line for line in request.source.splitlines() if line.strip()]
    if not request.min_editable_lines <= len(lines) <= request.max_editable_lines:
        raise RunnerValidationError(
            f"Use {request.min_editable_lines}–{request.max_editable_lines} non-empty editable lines."
        )
    if not set(request.allowed_calls) <= SAFE_CALLS:
        raise RunnerValidationError("This lab declares an unsupported built-in operation.")
    if not set(request.allowed_attributes) <= SAFE_ATTRIBUTES:
        raise RunnerValidationError("This lab declares an unsupported attribute operation.")
    try:
        tree = ast.parse(request.source, mode="exec")
    except SyntaxError as exc:
        raise RunnerValidationError(
            f"Python could not read line {exc.lineno}: {exc.msg}."
        ) from exc
    for node in ast.walk(tree):
        if type(node) not in ALLOWED_NODES:
            raise RunnerValidationError(
                f"{type(node).__name__} is outside this lesson's bounded editable region."
            )
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise RunnerValidationError("Use one simple variable assignment per line.")
            if node.targets[0].id not in request.allowed_assignments:
                raise RunnerValidationError(
                    f"Only these variables may be edited: {', '.join(request.allowed_assignments)}."
                )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise RunnerValidationError("Dunder names are not available in learning labs.")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            permitted = (
                set(request.allowed_assignments)
                | set(request.allowed_calls)
                | set(request.trusted_setup_exports)
            )
            if node.id not in permitted:
                raise RunnerValidationError(f"'{node.id}' is not available in this lab.")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr not in request.allowed_attributes:
                raise RunnerValidationError(f"Attribute operation '{node.attr}' is not allowlisted.")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in request.allowed_calls:
                    raise RunnerValidationError("That built-in operation is not allowlisted.")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in request.allowed_attributes:
                    raise RunnerValidationError("That attribute operation is not allowlisted.")
            else:
                raise RunnerValidationError("That operation is not allowlisted for this lab.")
    assigned = {
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    missing = set(request.allowed_assignments) - assigned
    if missing:
        raise RunnerValidationError(f"Add an assignment for: {', '.join(sorted(missing))}.")
    return tree


def request_from_lab(lab: LabSpec, source: str) -> RunRequest:
    configuration = BoundedPythonLabConfig.model_validate(lab.configuration)
    return RunRequest(
        lab_id=lab.id,
        source=source,
        trusted_setup_code=configuration.trusted_setup.code,
        trusted_setup_exports=configuration.trusted_setup.exports,
        checkpoints=[
            CheckpointContract(
                id=checkpoint.id,
                label=checkpoint.label,
                expression=checkpoint.expression,
                pass_message=checkpoint.pass_message,
                fail_message=checkpoint.fail_message,
            )
            for checkpoint in configuration.checkpoints
        ],
        allowed_assignments=configuration.policy.allowed_assignments,
        allowed_calls=configuration.policy.allowed_calls,
        allowed_attributes=configuration.policy.allowed_attributes,
        min_editable_lines=configuration.policy.min_editable_lines,
        max_editable_lines=configuration.policy.max_editable_lines,
        max_source_bytes=configuration.policy.max_source_bytes,
        timeout_seconds=configuration.policy.timeout_seconds,
        output_limit_bytes=configuration.policy.output_limit_bytes,
    )


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_code(request: RunRequest) -> RunResult:
    started = time.perf_counter()
    try:
        validate_source(request)
    except RunnerValidationError as exc:
        return RunResult(
            status="validation_error",
            error=str(exc),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    payload = {
        "source": request.source,
        "trusted_setup_code": request.trusted_setup_code,
        "trusted_setup_exports": request.trusted_setup_exports,
        "checkpoints": [checkpoint.__dict__ for checkpoint in request.checkpoints],
        "allowed_calls": request.allowed_calls,
        "output_limit_bytes": request.output_limit_bytes,
    }
    worker = Path(__file__).with_name("runner_worker.py")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start_new_session = os.name != "nt"
    environment = {
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
    }
    for key in ("SYSTEMROOT", "WINDIR", "PATH"):
        if key in os.environ:
            environment[key] = os.environ[key]
    temp_dir_path = ""
    worker_pid: int | None = None
    with tempfile.TemporaryDirectory(prefix="ml-lab-") as temp_dir:
        temp_dir_path = temp_dir
        process = subprocess.Popen(
            [sys.executable, "-I", str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=temp_dir,
            env=environment,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        worker_pid = process.pid
        try:
            stdout, stderr = process.communicate(
                json.dumps(payload, ensure_ascii=False), timeout=request.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            process.communicate()
            result = RunResult(
                status="timeout",
                error=f"This run exceeded {request.timeout_seconds:g} seconds and was stopped.",
                duration_ms=int((time.perf_counter() - started) * 1000),
                worker_pid=worker_pid,
                working_directory=temp_dir_path,
            )
        else:
            if len(stdout.encode("utf-8")) > request.output_limit_bytes + 16_384:
                result = RunResult(
                    status="output_limit",
                    error="This run produced more output than the lesson allows.",
                    worker_pid=worker_pid,
                    working_directory=temp_dir_path,
                )
            elif process.returncode != 0:
                result = RunResult(
                    status="runtime_error",
                    error=(stderr.strip() or "The learning worker stopped unexpectedly."),
                    worker_pid=worker_pid,
                    working_directory=temp_dir_path,
                )
            else:
                try:
                    response = json.loads(stdout)
                except json.JSONDecodeError:
                    result = RunResult(
                        status="runtime_error",
                        error="The learning worker returned invalid output.",
                        worker_pid=worker_pid,
                        working_directory=temp_dir_path,
                    )
                else:
                    result = RunResult(
                        status=response["status"],
                        stdout=response.get("stdout", ""),
                        error=response.get("error", ""),
                        checks=response.get("checks", []),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        worker_pid=worker_pid,
                        working_directory=temp_dir_path,
                    )
    return result
