from __future__ import annotations

from ml_lab.config import CONTENT_VERSION, CURRICULUM_SCHEMA_VERSION
from ml_lab.activities import ScenarioSorterConfig
from ml_lab.content import load_curriculum
from ml_lab.lab_contracts import BoundedPythonLabConfig
from ml_lab.labs import build_lab_registry
from ml_lab.validation import build_traceability_report


def test_curriculum_contract_and_traceability() -> None:
    curriculum = load_curriculum()
    assert curriculum.schema_version == CURRICULUM_SCHEMA_VERSION
    assert curriculum.content_version == CONTENT_VERSION
    assert len(curriculum.lessons) == 1
    assert build_traceability_report(curriculum, build_lab_registry()) == {
        "F1": [
            "activity:F1-SORT",
            "lab:F1-LAB",
            "lab-checkpoint:F1-LAB-C1",
            "lab-checkpoint:F1-LAB-C2",
            "lab-checkpoint:F1-LAB-C3",
            "check:F1-C1",
            "check:F1-C2",
            "check:F1-C3",
        ]
    }


def test_vertical_slice_content_is_complete_and_beginner_bounded() -> None:
    lesson = load_curriculum().lessons[0]
    lab_configuration = BoundedPythonLabConfig.model_validate(lesson.lab.configuration)
    assert len(lesson.understand) == 3
    assert len(ScenarioSorterConfig.model_validate(lesson.activity.configuration).scenarios) == 6
    assert len(lesson.checks) == 3
    editable_lines = [
        line for line in lab_configuration.default_code.splitlines() if line.strip()
    ]
    assert len(editable_lines) == 3
    assert lab_configuration.policy.min_editable_lines == 3
    assert lab_configuration.policy.max_editable_lines == 3
    assert lesson.lab.type == "bounded_python"
    assert lab_configuration.trusted_setup.exports == ["label_guide"]
    assert len(lab_configuration.checkpoints) == 3
    for check in lesson.checks:
        assert all(option.rationale.strip() for option in check.options)
