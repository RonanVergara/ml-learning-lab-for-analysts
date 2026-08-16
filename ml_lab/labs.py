from __future__ import annotations

from typing import Protocol

import streamlit as st
from pydantic import ValidationError

from .content import LabSpec
from .lab_contracts import BoundedPythonLabConfig
from .registry import Registry
from .runner import (
    RunRequest,
    RunResult,
    RunnerValidationError,
    request_from_lab,
    run_code,
    validate_source,
)


class LabHandler(Protocol):
    type_name: str

    def validate(self, lab: LabSpec) -> list[str]: ...

    def child_ids(self, lab: LabSpec) -> list[str]: ...

    def build_request(self, lab: LabSpec, source: str) -> RunRequest: ...

    def run(self, lab: LabSpec, source: str) -> RunResult: ...

    def render(self, lab: LabSpec) -> RunResult | None: ...


class BoundedPythonLabHandler:
    type_name = "bounded_python"

    def configuration(self, lab: LabSpec) -> BoundedPythonLabConfig:
        return BoundedPythonLabConfig.model_validate(lab.configuration)

    def child_ids(self, lab: LabSpec) -> list[str]:
        return [checkpoint.id for checkpoint in self.configuration(lab).checkpoints]

    def validate(self, lab: LabSpec) -> list[str]:
        try:
            configuration = self.configuration(lab)
        except ValidationError as exc:
            return [f"Lab {lab.id} configuration is invalid: {exc.errors()[0]['msg']}"]

        errors: list[str] = []
        setup = configuration.trusted_setup
        if len(setup.code.encode("utf-8")) > 131_072:
            errors.append(f"Lab {lab.id} trusted setup is too large")
        try:
            compile(setup.code, f"<{lab.id}-trusted-setup>", "exec")
        except SyntaxError as exc:
            errors.append(f"Lab {lab.id} trusted setup does not compile: {exc.msg}")
        for export in setup.exports:
            if not export.isidentifier() or export.startswith("__"):
                errors.append(f"Lab {lab.id} has invalid trusted export {export!r}")
        if set(setup.exports) & set(configuration.policy.allowed_assignments):
            errors.append(f"Lab {lab.id} lets learner code overwrite a trusted export")
        for assignment in configuration.policy.allowed_assignments:
            if not assignment.isidentifier() or assignment.startswith("__"):
                errors.append(f"Lab {lab.id} has invalid learner assignment {assignment!r}")
        for operation in (
            configuration.policy.allowed_calls + configuration.policy.allowed_attributes
        ):
            if not operation.isidentifier() or operation.startswith("_"):
                errors.append(f"Lab {lab.id} has invalid allowed operation {operation!r}")

        checkpoint_ids = [checkpoint.id for checkpoint in configuration.checkpoints]
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            errors.append(f"Lab {lab.id} has duplicate checkpoint IDs")
        for checkpoint in configuration.checkpoints:
            if len(checkpoint.expression.encode("utf-8")) > 8_192:
                errors.append(f"Lab checkpoint {checkpoint.id} expression is too large")
            try:
                compile(checkpoint.expression, f"<{checkpoint.id}-checkpoint>", "eval")
            except SyntaxError as exc:
                errors.append(f"Lab checkpoint {checkpoint.id} does not compile: {exc.msg}")

        try:
            validate_source(self.build_request(lab, configuration.default_code))
        except (RunnerValidationError, ValidationError) as exc:
            errors.append(f"Lab {lab.id} starter code violates its policy: {exc}")
        else:
            execution = self.run(lab, configuration.default_code)
            if execution.status not in {"passed", "check_failed"}:
                detail = execution.error or execution.status
                errors.append(f"Lab {lab.id} trusted setup/checkpoint contract failed: {detail}")
        return errors

    def build_request(self, lab: LabSpec, source: str) -> RunRequest:
        return request_from_lab(lab, source)

    def run(self, lab: LabSpec, source: str) -> RunResult:
        return run_code(self.build_request(lab, source))

    def render(self, lab: LabSpec) -> RunResult | None:
        configuration = self.configuration(lab)
        st.warning(
            "Trusted-local teaching safeguard: only this bounded region is checked and run in a "
            "short-lived child process. It is not a secure sandbox for hostile code."
        )
        st.caption("Read-only setup")
        st.code(configuration.trusted_setup.display_code, language="python")
        editor_key = f"editor_{lab.id}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = configuration.default_code
        if st.button("Reset editable region"):
            st.session_state[editor_key] = configuration.default_code
        source = st.text_area(
            "Editable region",
            key=editor_key,
            height=150,
            help=(
                f"This lab expects {configuration.policy.min_editable_lines}–"
                f"{configuration.policy.max_editable_lines} editable lines."
            ),
        )
        if st.button("Run checkpoint", type="primary"):
            return self.run(lab, source)
        return None


def build_lab_registry() -> Registry[LabHandler]:
    registry: Registry[LabHandler] = Registry("lab")
    handler = BoundedPythonLabHandler()
    registry.register(handler.type_name, handler)
    return registry
