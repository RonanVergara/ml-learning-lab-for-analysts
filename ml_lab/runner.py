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


class RunnerValidationError(ValueError):
    """Learner code does not match the bounded lab policy."""


@dataclass(frozen=True)
class RunRequest:
    lab_id: str
    source: str
    allowed_assignments: list[str]
    allowed_calls: list[str]
    expected_values: dict[str, Any]
    min_editable_lines: int
    max_editable_lines: int
    timeout_seconds: float = 5.0
    output_limit_bytes: int = 65_536


@dataclass(frozen=True)
class RunResult:
    status: str
    stdout: str = ""
    error: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "passed" and all(check.get("passed") for check in self.checks)


SAFE_CALLS = {"len", "sum", "min", "max", "round", "range", "sorted"}
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
}


def validate_source(request: RunRequest) -> ast.Module:
    lines = [line for line in request.source.splitlines() if line.strip()]
    if not request.min_editable_lines <= len(lines) <= request.max_editable_lines:
        raise RunnerValidationError(
            f"Use {request.min_editable_lines}–{request.max_editable_lines} non-empty editable lines."
        )
    if not set(request.allowed_calls) <= SAFE_CALLS:
        raise RunnerValidationError("This lab declares an unsupported operation.")
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
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            permitted = set(request.allowed_assignments) | set(request.allowed_calls)
            if node.id not in permitted:
                raise RunnerValidationError(f"'{node.id}' is not available in this lab.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in request.allowed_calls:
                raise RunnerValidationError("That operation is not allowlisted for this lab.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise RunnerValidationError("Dunder names are not available in learning labs.")
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
    return RunRequest(
        lab_id=lab.id,
        source=source,
        allowed_assignments=lab.policy.allowed_assignments,
        allowed_calls=lab.policy.allowed_calls,
        expected_values=lab.expected_values,
        min_editable_lines=lab.policy.min_editable_lines,
        max_editable_lines=lab.policy.max_editable_lines,
        timeout_seconds=lab.policy.timeout_seconds,
        output_limit_bytes=lab.policy.output_limit_bytes,
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
        "allowed_calls": request.allowed_calls,
        "expected_values": request.expected_values,
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
    with tempfile.TemporaryDirectory(prefix="ml-lab-") as temp_dir:
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
        try:
            stdout, stderr = process.communicate(
                json.dumps(payload, ensure_ascii=False), timeout=request.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            process.communicate()
            return RunResult(
                status="timeout",
                error=f"This run exceeded {request.timeout_seconds:g} seconds and was stopped.",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
    if len(stdout.encode("utf-8")) > request.output_limit_bytes:
        return RunResult(
            status="output_limit",
            error="This run produced more output than the lesson allows.",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    if process.returncode != 0:
        return RunResult(
            status="runtime_error",
            error=(stderr.strip() or "The learning worker stopped unexpectedly."),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError:
        return RunResult(status="runtime_error", error="The learning worker returned invalid output.")
    return RunResult(
        status=response["status"],
        stdout=response.get("stdout", ""),
        error=response.get("error", ""),
        checks=response.get("checks", []),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
