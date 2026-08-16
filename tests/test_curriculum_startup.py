from __future__ import annotations

import pytest

from ml_lab.activities import ScenarioSorterConfig, build_activity_registry
from ml_lab.content import load_curriculum
from ml_lab.lab_contracts import BoundedPythonLabConfig
from ml_lab.labs import build_lab_registry
from ml_lab.registry import Registry, RegistryError
from ml_lab.validation import CurriculumStartupError, validate_curriculum_startup


def test_activity_and_lab_registries_dispatch_declared_types() -> None:
    curriculum = load_curriculum()
    activity_registry = build_activity_registry()
    lab_registry = build_lab_registry()
    lesson = curriculum.lessons[0]

    activity_handler = activity_registry.require(lesson.activity.type)
    config = ScenarioSorterConfig.model_validate(lesson.activity.configuration)
    answers = {scenario.id: scenario.answer for scenario in config.scenarios}
    assert activity_handler.evaluate(lesson.activity, answers).passed

    lab_handler = lab_registry.require(lesson.lab.type)
    lab_config = BoundedPythonLabConfig.model_validate(lesson.lab.configuration)
    assert lab_handler.build_request(lesson.lab, lab_config.default_code).lab_id == lesson.lab.id
    assert activity_registry.keys() == ("scenario_sorter",)
    assert lab_registry.keys() == ("bounded_python",)


def test_registry_rejects_duplicate_and_unknown_keys() -> None:
    registry: Registry[object] = Registry("test")
    value = object()
    registry.register("known", value)
    with pytest.raises(RegistryError, match="duplicated"):
        registry.register("known", value)
    with pytest.raises(RegistryError, match="Unknown test registry key"):
        registry.require("missing")


def test_complete_curriculum_passes_startup_validation() -> None:
    report = validate_curriculum_startup(
        load_curriculum(), build_activity_registry(), build_lab_registry()
    )
    assert report.lessons == 1
    assert report.objectives == 1
    assert report.activities == 1
    assert report.labs == 1
    assert report.knowledge_checks == 3
    assert report.lab_checkpoints == 3


def test_startup_validation_rejects_unknown_registry_types() -> None:
    curriculum = load_curriculum().model_copy(deep=True)
    curriculum.lessons[0].activity.type = "unregistered_activity"
    curriculum.lessons[0].lab.type = "unregistered_lab"
    with pytest.raises(CurriculumStartupError) as error:
        validate_curriculum_startup(curriculum, build_activity_registry(), build_lab_registry())
    message = str(error.value)
    assert "Unknown activity registry key" in message
    assert "Unknown lab registry key" in message


def test_startup_validation_rejects_type_specific_configuration_errors() -> None:
    curriculum = load_curriculum().model_copy(deep=True)
    curriculum.lessons[0].activity.configuration = {"scenarios": []}
    curriculum.lessons[0].lab.configuration["unexpected"] = True
    with pytest.raises(CurriculumStartupError) as error:
        validate_curriculum_startup(curriculum, build_activity_registry(), build_lab_registry())
    message = str(error.value)
    assert "Activity F1-SORT configuration is invalid" in message
    assert "Lab F1-LAB configuration is invalid" in message


def test_startup_validation_aggregates_duplicate_orphan_and_contract_errors() -> None:
    curriculum = load_curriculum().model_copy(deep=True)
    lesson = curriculum.lessons[0]
    curriculum.objectives["ORPHAN"] = "This objective has no assessment evidence."
    lesson.checks[1].id = lesson.checks[0].id
    lesson.lab.configuration["trusted_setup"]["exports"] = ["missing_export"]
    lesson.lab.configuration["checkpoints"][0]["expression"] = "not valid python !"

    with pytest.raises(CurriculumStartupError) as error:
        validate_curriculum_startup(curriculum, build_activity_registry(), build_lab_registry())
    message = str(error.value)
    assert "Duplicate knowledge-check ID" in message
    assert "Objective ORPHAN has no assessment evidence" in message
    assert "does not compile" in message
    assert "trusted setup/checkpoint contract failed" in message
