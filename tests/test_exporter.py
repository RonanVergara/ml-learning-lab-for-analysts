from __future__ import annotations

import io
import zipfile

import pytest

from ml_lab.config import APP_ID, APP_VERSION
from ml_lab.exporter import build_vertical_slice_package, validate_package


def test_vertical_slice_package_contains_and_validates_every_format() -> None:
    package = build_vertical_slice_package()
    report = validate_package(package.data)
    assert report["valid"] is True
    assert report["artifact_count"] == 7
    assert report["rows"] == 6
    assert package.filename == "ml-learning-lab-milestone1.1-evidence.zip"
    assert {path.rsplit(".", 1)[-1] for path in report["artifacts"]} >= {
        "csv",
        "png",
        "xlsx",
        "ipynb",
        "md",
        "html",
        "json",
    }


def test_package_manifest_identifies_the_milestone_1_1_application() -> None:
    package = build_vertical_slice_package()
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        import json

        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["package_type"] == "milestone-1.1-vertical-slice"
    assert manifest["app_id"] == APP_ID
    assert manifest["app_version"] == APP_VERSION


def test_package_validator_detects_corruption() -> None:
    package = build_vertical_slice_package()
    source = zipfile.ZipFile(io.BytesIO(package.data))
    values = {name: source.read(name) for name in source.namelist()}
    values["data/sample_cases.csv"] += b"\nCORRUPTED"
    mutated = io.BytesIO()
    with zipfile.ZipFile(mutated, "w") as archive:
        for name, value in values.items():
            archive.writestr(name, value)
    with pytest.raises(ValueError, match="CSV|hash"):
        validate_package(mutated.getvalue())
