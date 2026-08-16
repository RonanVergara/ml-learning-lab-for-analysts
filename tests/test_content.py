from __future__ import annotations

from ml_lab.config import CONTENT_VERSION, SCHEMA_VERSION
from ml_lab.content import load_curriculum


def test_curriculum_contract_and_traceability() -> None:
    curriculum = load_curriculum()
    assert curriculum.schema_version == SCHEMA_VERSION
    assert curriculum.content_version == CONTENT_VERSION
    assert len(curriculum.lessons) == 1
    assert curriculum.traceability_report() == {
        "F1": [
            "activity:F1-SORT",
            "lab:F1-LAB",
            "check:F1-C1",
            "check:F1-C2",
            "check:F1-C3",
        ]
    }


def test_vertical_slice_content_is_complete_and_beginner_bounded() -> None:
    lesson = load_curriculum().lessons[0]
    assert len(lesson.understand) == 3
    assert len(lesson.activity.scenarios) == 6
    assert len(lesson.checks) == 3
    editable_lines = [line for line in lesson.lab.default_code.splitlines() if line.strip()]
    assert len(editable_lines) == 3
    assert lesson.lab.policy.min_editable_lines == 3
    assert lesson.lab.policy.max_editable_lines == 3
    for check in lesson.checks:
        assert all(option.rationale.strip() for option in check.options)
