from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import CONTENT_VERSION, SCHEMA_VERSION, workspace_root


class RoadmapUnit(BaseModel):
    id: str
    title: str
    expected_lessons: int
    milestone: int


class OrientationEntry(BaseModel):
    title: str
    description: str
    excel_python_map: list[dict[str, str]]


class ActivityScenario(BaseModel):
    id: str
    prompt: str
    answer: Literal["reporting", "rules", "ml"]
    rationale: str


class ActivitySpec(BaseModel):
    id: str
    type: Literal["scenario_sorter"]
    title: str
    instructions: str
    objective_ids: list[str]
    scenarios: list[ActivityScenario]


class LabPolicySpec(BaseModel):
    allowed_assignments: list[str]
    allowed_calls: list[str] = Field(default_factory=list)
    min_editable_lines: int
    max_editable_lines: int
    timeout_seconds: float = 5.0
    output_limit_bytes: int = 65_536


class LabSpec(BaseModel):
    id: str
    title: str
    instructions: str
    objective_ids: list[str]
    read_only_setup: str
    default_code: str
    expected_values: dict[str, str]
    policy: LabPolicySpec

    @model_validator(mode="after")
    def validate_editable_region(self) -> "LabSpec":
        lines = [line for line in self.default_code.splitlines() if line.strip()]
        if not self.policy.min_editable_lines <= len(lines) <= self.policy.max_editable_lines:
            raise ValueError("Default code does not match its declared editable-line bounds")
        if set(self.expected_values) != set(self.policy.allowed_assignments):
            raise ValueError("Expected values must match the allowed assignment names")
        return self


class CheckOption(BaseModel):
    label: str
    rationale: str


class KnowledgeCheck(BaseModel):
    id: str
    objective_ids: list[str]
    prompt: str
    options: list[CheckOption]
    correct_index: int

    @model_validator(mode="after")
    def validate_answer(self) -> "KnowledgeCheck":
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError("Knowledge-check answer is outside the option list")
        if len(self.options) < 2:
            raise ValueError("Knowledge checks require at least two options")
        return self


class LessonSpec(BaseModel):
    id: str
    module_id: str
    title: str
    duration_minutes: int
    objective_ids: list[str]
    scenario: str
    understand: list[dict[str, str]]
    activity: ActivitySpec
    lab: LabSpec
    checks: list[KnowledgeCheck]
    takeaway: str


class CurriculumSpec(BaseModel):
    schema_version: int
    content_version: str
    course_title: str
    orientation_entry: OrientationEntry
    roadmap: list[RoadmapUnit]
    objectives: dict[str, str]
    lessons: list[LessonSpec]

    @model_validator(mode="after")
    def validate_contract(self) -> "CurriculumSpec":
        if self.schema_version != SCHEMA_VERSION:
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
