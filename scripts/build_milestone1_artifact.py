from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_lab.exporter import build_vertical_slice_package, validate_package


def main() -> None:
    result = build_vertical_slice_package()
    report = validate_package(result.data)
    target_dir = PROJECT_ROOT / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / result.filename
    target.write_bytes(result.data)
    print(f"Wrote {target}")
    print(f"Validated {report['artifact_count']} artifacts and {report['rows']} rows")


if __name__ == "__main__":
    main()
