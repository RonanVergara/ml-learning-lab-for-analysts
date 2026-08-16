from __future__ import annotations

import re
from dataclasses import dataclass

from .activities import ActivityHandler
from .config import CURRICULUM_SCHEMA_VERSION
from .content import CurriculumSpec
from .labs import LabHandler
from .registry import Registry, RegistryError


class CurriculumStartupError(ValueError):
    """The complete curriculum cannot be safely served by this application build."""


@dataclass(frozen=True)
class CurriculumValidationReport:
    lessons: int
    objectives: int
    activities: int
    labs: int
    knowledge_checks: int
    lab_checkpoints: int


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")


def _validate_ids(label: str, values: list[str], errors: list[str]) -> None:
    for duplicate in _duplicates(values):
        errors.append(f"Duplicate {label} ID: {duplicate}")
    for value in values:
        if not _STABLE_ID.fullmatch(value):
            errors.append(f"Invalid {label} ID: {value!r}")


def build_traceability_report(
    curriculum: CurriculumSpec,
    lab_registry: Registry[LabHandler],
) -> dict[str, list[str]]:
    evidence = curriculum.traceability_report()
    for lesson in curriculum.lessons:
        checkpoint_ids = lab_registry.require(lesson.lab.type).child_ids(lesson.lab)
        for objective_id in lesson.lab.objective_ids:
            lab_marker = f"lab:{lesson.lab.id}"
            insert_at = evidence[objective_id].index(lab_marker) + 1
            evidence[objective_id][insert_at:insert_at] = [
                f"lab-checkpoint:{checkpoint_id}" for checkpoint_id in checkpoint_ids
            ]
    return evidence


def validate_curriculum_startup(
    curriculum: CurriculumSpec,
    activity_registry: Registry[ActivityHandler],
    lab_registry: Registry[LabHandler],
) -> CurriculumValidationReport:
    errors: list[str] = []
    if curriculum.schema_version != CURRICULUM_SCHEMA_VERSION:
        errors.append("Curriculum schema does not match this application build")

    roadmap_ids = [unit.id for unit in curriculum.roadmap]
    _validate_ids("roadmap", roadmap_ids, errors)
    _validate_ids("objective", list(curriculum.objectives), errors)
    for objective_id, description in curriculum.objectives.items():
        if not description.strip():
            errors.append(f"Objective {objective_id} has an empty description")
    known_modules = set(roadmap_ids)
    known_objectives = set(curriculum.objectives)

    lesson_ids: list[str] = []
    activity_ids: list[str] = []
    lab_ids: list[str] = []
    check_ids: list[str] = []
    checkpoint_ids: list[str] = []
    activity_item_ids: list[str] = []

    for mapping in curriculum.orientation_entry.excel_python_map:
        if set(mapping) != {"excel", "python"} or not all(mapping.values()):
            errors.append("Every orientation map row must contain non-empty excel and python values")

    for lesson in curriculum.lessons:
        lesson_ids.append(lesson.id)
        activity_ids.append(lesson.activity.id)
        lab_ids.append(lesson.lab.id)
        check_ids.extend(check.id for check in lesson.checks)

        if lesson.module_id not in known_modules:
            errors.append(f"Lesson {lesson.id} references unknown module {lesson.module_id}")
        if len(lesson.objective_ids) != len(set(lesson.objective_ids)):
            errors.append(f"Lesson {lesson.id} repeats objective IDs")
        lesson_objectives = set(lesson.objective_ids)
        if not lesson_objectives <= known_objectives:
            errors.append(f"Lesson {lesson.id} references an unknown objective")
        component_objectives = [
            (f"activity {lesson.activity.id}", set(lesson.activity.objective_ids)),
            (f"lab {lesson.lab.id}", set(lesson.lab.objective_ids)),
            *[
                (f"check {check.id}", set(check.objective_ids))
                for check in lesson.checks
            ],
        ]
        for label, objective_ids in component_objectives:
            if not objective_ids or not objective_ids <= lesson_objectives:
                errors.append(f"{label} must reference objectives owned by lesson {lesson.id}")
        for label, objective_ids in (
            (f"activity {lesson.activity.id}", lesson.activity.objective_ids),
            (f"lab {lesson.lab.id}", lesson.lab.objective_ids),
            *[(f"check {check.id}", check.objective_ids) for check in lesson.checks],
        ):
            if len(objective_ids) != len(set(objective_ids)):
                errors.append(f"{label} repeats objective IDs")

        for section in lesson.understand:
            if set(section) != {"title", "body"} or not all(section.values()):
                errors.append(f"Lesson {lesson.id} has an incomplete explanation section")
            elif len(section["body"].split()) > 250:
                errors.append(f"Lesson {lesson.id} has an explanation chunk over 250 words")
        for check in lesson.checks:
            labels = [option.label for option in check.options]
            if len(labels) != len({label.casefold() for label in labels}):
                errors.append(f"Knowledge check {check.id} has duplicate option labels")

        try:
            activity_handler = activity_registry.require(lesson.activity.type)
            activity_errors = activity_handler.validate(lesson.activity)
            errors.extend(activity_errors)
            if not activity_errors:
                activity_item_ids.extend(activity_handler.child_ids(lesson.activity))
        except RegistryError as exc:
            errors.append(str(exc))
        except ValueError as exc:
            errors.append(f"Activity {lesson.activity.id} configuration is invalid: {exc}")

        try:
            lab_handler = lab_registry.require(lesson.lab.type)
            lab_errors = lab_handler.validate(lesson.lab)
            errors.extend(lab_errors)
            if not lab_errors:
                checkpoint_ids.extend(lab_handler.child_ids(lesson.lab))
        except RegistryError as exc:
            errors.append(str(exc))
        except ValueError as exc:
            errors.append(f"Lab {lesson.lab.id} configuration is invalid: {exc}")

    for label, values in (
        ("lesson", lesson_ids),
        ("activity", activity_ids),
        ("lab", lab_ids),
        ("knowledge-check", check_ids),
        ("lab-checkpoint", checkpoint_ids),
        ("activity-item", activity_item_ids),
    ):
        _validate_ids(label, values, errors)

    lesson_counts = {
        module_id: sum(lesson.module_id == module_id for lesson in curriculum.lessons)
        for module_id in known_modules
    }
    for unit in curriculum.roadmap:
        if lesson_counts[unit.id] > unit.expected_lessons:
            errors.append(
                f"Roadmap unit {unit.id} declares {unit.expected_lessons} lessons but contains "
                f"{lesson_counts[unit.id]}"
            )

    try:
        traceability = build_traceability_report(curriculum, lab_registry)
    except (RegistryError, ValueError):
        traceability = curriculum.traceability_report()
    for objective_id, evidence in traceability.items():
        if not evidence:
            errors.append(f"Objective {objective_id} has no assessment evidence")

    if errors:
        unique_errors = list(dict.fromkeys(errors))
        raise CurriculumStartupError(
            "Curriculum startup validation failed:\n- " + "\n- ".join(unique_errors)
        )
    return CurriculumValidationReport(
        lessons=len(curriculum.lessons),
        objectives=len(curriculum.objectives),
        activities=len(activity_ids),
        labs=len(lab_ids),
        knowledge_checks=len(check_ids),
        lab_checkpoints=len(checkpoint_ids),
    )
