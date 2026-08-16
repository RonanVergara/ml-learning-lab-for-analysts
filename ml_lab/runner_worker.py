from __future__ import annotations

import builtins
import contextlib
import io
import json
import sys
import time


SAFE_BUILTINS = {
    "abs": abs,
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "print": print,
    "round": round,
    "range": range,
    "sorted": sorted,
}


class OutputLimitExceeded(RuntimeError):
    pass


class ContractError(RuntimeError):
    pass


class LimitedWriter(io.StringIO):
    def __init__(self, byte_limit: int) -> None:
        super().__init__()
        self.byte_limit = byte_limit
        self.bytes_written = 0

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8")
        if self.bytes_written + len(encoded) > self.byte_limit:
            raise OutputLimitExceeded("The editable region produced too much output.")
        self.bytes_written += len(encoded)
        return super().write(value)


def _execute(request: dict[str, object], output: LimitedWriter) -> dict[str, object]:
    namespace: dict[str, object] = {"__builtins__": builtins.__dict__}
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(
            compile(str(request["trusted_setup_code"]), "<trusted-setup>", "exec"),
            namespace,
            namespace,
        )
        missing_exports = [
            name for name in request["trusted_setup_exports"] if name not in namespace
        ]
        if missing_exports:
            raise ContractError(
                "Trusted setup did not create: " + ", ".join(sorted(missing_exports))
            )
        full_builtins = namespace["__builtins__"]
        namespace["__builtins__"] = {
            name: SAFE_BUILTINS[name] for name in request["allowed_calls"]
        }
        try:
            exec(
                compile(str(request["source"]), "<editable-region>", "exec"),
                namespace,
                namespace,
            )
        finally:
            namespace["__builtins__"] = full_builtins

        checks = []
        for checkpoint in request["checkpoints"]:
            value = eval(
                compile(
                    str(checkpoint["expression"]),
                    f"<{checkpoint['id']}-checkpoint>",
                    "eval",
                ),
                namespace,
                namespace,
            )
            if type(value) is not bool:
                raise ContractError(
                    f"Checkpoint {checkpoint['id']} must return a Python boolean."
                )
            passed = value
            checks.append(
                {
                    "id": checkpoint["id"],
                    "name": checkpoint["label"],
                    "passed": passed,
                    "message": (
                        checkpoint["pass_message"] if passed else checkpoint["fail_message"]
                    ),
                }
            )
    return {
        "status": "passed" if all(check["passed"] for check in checks) else "check_failed",
        "stdout": output.getvalue(),
        "checks": checks,
    }


def main() -> int:
    request = json.loads(sys.stdin.read())
    started = time.perf_counter()
    output = LimitedWriter(int(request["output_limit_bytes"]))
    try:
        response = _execute(request, output)
    except OutputLimitExceeded as exc:
        response = {
            "status": "output_limit",
            "error": str(exc),
            "stdout": "",
            "checks": [],
        }
    except ContractError as exc:
        response = {
            "status": "contract_error",
            "error": str(exc),
            "stdout": output.getvalue(),
            "checks": [],
        }
    except Exception as exc:
        response = {
            "status": "runtime_error",
            "error": f"{type(exc).__name__}: {exc}",
            "stdout": output.getvalue(),
            "checks": [],
        }
    response["duration_ms"] = int((time.perf_counter() - started) * 1000)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
