from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import streamlit as st
from pydantic import Field, ValidationError

from .content import ActivitySpec, ContractModel
from .registry import Registry


@dataclass(frozen=True)
class ActivityItemResult:
    scenario_id: str
    prompt: str
    correct: bool
    rationale: str


@dataclass(frozen=True)
class ActivityEvaluation:
    items: list[ActivityItemResult]

    @property
    def passed(self) -> bool:
        return bool(self.items) and all(item.correct for item in self.items)


class ActivityHandler(Protocol):
    type_name: str

    def validate(self, activity: ActivitySpec) -> list[str]: ...

    def child_ids(self, activity: ActivitySpec) -> list[str]: ...

    def evaluate(self, activity: ActivitySpec, answers: dict[str, str]) -> ActivityEvaluation: ...

    def render(self, activity: ActivitySpec) -> ActivityEvaluation | None: ...


class ScenarioSorterItem(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1)
    answer: Literal["reporting", "rules", "ml"]
    rationale: str = Field(min_length=1)


class ScenarioSorterConfig(ContractModel):
    scenarios: list[ScenarioSorterItem] = Field(min_length=3)


class ScenarioSorterHandler:
    type_name = "scenario_sorter"

    def _configuration(self, activity: ActivitySpec) -> ScenarioSorterConfig:
        return ScenarioSorterConfig.model_validate(activity.configuration)

    def validate(self, activity: ActivitySpec) -> list[str]:
        errors: list[str] = []
        try:
            scenarios = self._configuration(activity).scenarios
        except ValidationError as exc:
            return [f"Activity {activity.id} configuration is invalid: {exc.errors()[0]['msg']}"]
        scenario_ids = [scenario.id for scenario in scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            errors.append(f"Activity {activity.id} has duplicate scenario IDs")
        represented = {scenario.answer for scenario in scenarios}
        if represented != {"reporting", "rules", "ml"}:
            errors.append(f"Activity {activity.id} must represent reporting, rules, and ml")
        return errors

    def child_ids(self, activity: ActivitySpec) -> list[str]:
        return [scenario.id for scenario in self._configuration(activity).scenarios]

    def evaluate(self, activity: ActivitySpec, answers: dict[str, str]) -> ActivityEvaluation:
        scenarios = self._configuration(activity).scenarios
        return ActivityEvaluation(
            items=[
                ActivityItemResult(
                    scenario_id=scenario.id,
                    prompt=scenario.prompt,
                    correct=answers.get(scenario.id) == scenario.answer,
                    rationale=scenario.rationale,
                )
                for scenario in scenarios
            ]
        )

    def render(self, activity: ActivitySpec) -> ActivityEvaluation | None:
        scenarios = self._configuration(activity).scenarios
        choices = ["Select…", "reporting", "rules", "ml"]
        answers = {
            scenario.id: st.selectbox(
                scenario.prompt,
                choices,
                key=f"activity_{activity.id}_{scenario.id}",
            )
            for scenario in scenarios
        }
        if st.button("Check all six requests", type="primary"):
            return self.evaluate(activity, answers)
        return None


def build_activity_registry() -> Registry[ActivityHandler]:
    registry: Registry[ActivityHandler] = Registry("activity")
    handler = ScenarioSorterHandler()
    registry.register(handler.type_name, handler)
    return registry
