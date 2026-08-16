from __future__ import annotations

import re
import sys
from pathlib import Path

from importlib.metadata import version


ROOT = Path(__file__).resolve().parents[1]


def test_required_documentation_exists_and_readme_links_resolve() -> None:
    required = {
        ROOT / "README.md",
        ROOT / "docs" / "quick-start.md",
        ROOT / "docs" / "troubleshooting.md",
        ROOT / "docs" / "learner-guide.md",
        ROOT / "docs" / "developer-guide.md",
        ROOT / "docs" / "content-authoring-guide.md",
    }
    assert all(path.is_file() and path.stat().st_size > 200 for path in required)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    relative_links = re.findall(r"\[[^]]+\]\((?!https?://)([^)]+)\)", readme)
    assert relative_links
    assert all((ROOT / link).is_file() for link in relative_links)


def test_launcher_and_lock_target_only_python_313() -> None:
    launcher = (ROOT / "Launch ML Learning Lab.cmd").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    assert "py -3.13" in launcher
    assert "requirements.lock" in bootstrap
    assert "MLLearningLab" in bootstrap
    assert sys.version_info[:2] == (3, 13)


def test_direct_dependency_versions_match_the_tested_environment() -> None:
    expected = {
        "streamlit": "1.61.1",
        "scikit-learn": "1.9.0",
        "pandas": "3.0.5",
        "numpy": "2.5.2",
        "plotly": "6.9.0",
        "matplotlib": "3.11.1",
        "pydantic": "2.13.4",
        "openpyxl": "3.1.5",
        "nbformat": "5.11.0",
        "pillow": "12.3.0",
        "pytest": "9.1.1",
    }
    assert {name: version(name) for name in expected} == expected
