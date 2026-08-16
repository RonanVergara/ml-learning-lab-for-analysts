from __future__ import annotations

import contextlib
import io
import json
import sys
import time


SAFE_BUILTINS = {
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "round": round,
    "range": range,
    "sorted": sorted,
}


class LimitedWriter(io.StringIO):
    def __init__(self, byte_limit: int) -> None:
        super().__init__()
        self.byte_limit = byte_limit
        self.bytes_written = 0

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8")
        if self.bytes_written + len(encoded) > self.byte_limit:
            raise RuntimeError("The editable region produced too much output.")
        self.bytes_written += len(encoded)
        return super().write(value)


def main() -> int:
    request = json.loads(sys.stdin.read())
    started = time.perf_counter()
    output = LimitedWriter(int(request["output_limit_bytes"]))
    namespace: dict[str, object] = {}
    safe_builtins = {name: SAFE_BUILTINS[name] for name in request["allowed_calls"]}
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exec(
                compile(request["source"], "<editable-region>", "exec"),
                {"__builtins__": safe_builtins},
                namespace,
            )
        checks = []
        for name, expected in request["expected_values"].items():
            actual = namespace.get(name)
            checks.append(
                {
                    "name": name,
                    "passed": actual == expected,
                    "expected": expected,
                    "actual": actual,
                }
            )
        status = "passed" if all(check["passed"] for check in checks) else "check_failed"
        response = {
            "status": status,
            "stdout": output.getvalue(),
            "checks": checks,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        response = {
            "status": "runtime_error",
            "error": f"{type(exc).__name__}: {exc}",
            "stdout": output.getvalue(),
            "checks": [],
        }
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
