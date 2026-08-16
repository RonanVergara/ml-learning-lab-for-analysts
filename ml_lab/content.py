from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import CONTENT_VERSION, CURRICULUM_SCHEMA_VERSION, workspace_root


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoadmapUnit(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    expected_lessons: int = Field(ge=1)
    milestone: int = Field(ge=1)


class OrientationEntry(ContractModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    excel_python_map: list[dict[str, str]] = Field(min_length=1)


class ActivitySpec(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    objective_ids: list[str] = Field(min_length=1)
    configuration: dict[str, Any]


class LabSpec(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    objective_ids: list[str] = Field(min_length=1)
    configuration: dict[str, Any]


class CheckOption(ContractModel):
    label: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class KnowledgeCheck(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    objective_ids: list[str] = Field(min_length=1)
    prompt: str = Field(min_length=1)
    options: list[CheckOption] = Field(min_length=2)
    correct_index: int

    @model_validator(mode="after")
    def validate_answer(self) -> "KnowledgeCheck":
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError("Knowledge-check answer is outside the option list")
        if len(self.options) < 2:
            raise ValueError("Knowledge checks require at least two options")
        return self


class LessonSpec(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    module_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0, le=180)
    objective_ids: list[str] = Field(min_length=1)
    scenario: str = Field(min_length=1)
    understand: list[dict[str, str]] = Field(min_length=1)
    activity: ActivitySpec
    lab: LabSpec
    checks: list[KnowledgeCheck] = Field(min_length=1)
    takeaway: str = Field(min_length=1)


class CurriculumSpec(ContractModel):
    schema_version: int = Field(ge=1)
    content_version: str = Field(min_length=1)
    course_title: str = Field(min_length=1)
    orientation_entry: OrientationEntry
    roadmap: list[RoadmapUnit] = Field(min_length=1)
    objectives: dict[str, str] = Field(min_length=1)
    lessons: list[LessonSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "CurriculumSpec":
        if self.schema_version != CURRICULUM_SCHEMA_VERSION:
            raise ValueError("Curriculum schema version is not supported")
        if self.content_version != CONTENT_VERSION:
            raise ValueError("Curriculum content version does not match the application")
        lesson_ids = [lesson.id for lesson in self.lessons]
        if len(lesson_ids) != len(set(lesson_ids)):
            raise ValueError("Lesson IDs must be unique")
        known = set(self.objectives)
        references: list[str] = []
        for lesson in self.lessons:
            references.extend(lesson.objective_ids)
            references.extend(lesson.activity.objective_ids)
            references.extend(lesson.lab.objective_ids)
            for check in lesson.checks:
                references.extend(check.objective_ids)
        unknown = sorted(set(references) - known)
        if unknown:
            raise ValueError(f"Unknown objective references: {unknown}")
        return self

    def traceability_report(self) -> dict[str, list[str]]:
        evidence = {objective_id: [] for objective_id in self.objectives}
        for lesson in self.lessons:
            for objective_id in lesson.activity.objective_ids:
                evidence[objective_id].append(f"activity:{lesson.activity.id}")
            for objective_id in lesson.lab.objective_ids:
                evidence[objective_id].append(f"lab:{lesson.lab.id}")
            for check in lesson.checks:
                for objective_id in check.objective_ids:
                    evidence[objective_id].append(f"check:{check.id}")
        return evidence


def load_curriculum(path: Path | None = None) -> CurriculumSpec:
    curriculum_path = path or workspace_root() / "content" / "curriculum.json"
    raw = json.loads(curriculum_path.read_text(encoding="utf-8"))
    return CurriculumSpec.model_validate(raw)
