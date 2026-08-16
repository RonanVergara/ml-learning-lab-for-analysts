from __future__ import annotations

from pydantic import Field, model_validator

from .content import ContractModel


class LabPolicySpec(ContractModel):
    allowed_assignments: list[str] = Field(min_length=1)
    allowed_calls: list[str] = Field(default_factory=list)
    allowed_attributes: list[str] = Field(default_factory=list)
    min_editable_lines: int = Field(ge=1)
    max_editable_lines: int = Field(ge=1)
    max_source_bytes: int = Field(default=8_192, ge=64, le=65_536)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    output_limit_bytes: int = Field(default=65_536, ge=128, le=1_048_576)


class TrustedSetupSpec(ContractModel):
    display_code: str = Field(min_length=1)
    code: str = ""
    exports: list[str] = Field(default_factory=list)


class LabCheckpointSpec(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    pass_message: str = Field(min_length=1)
    fail_message: str = Field(min_length=1)


class BoundedPythonLabConfig(ContractModel):
    trusted_setup: TrustedSetupSpec
    default_code: str = Field(min_length=1)
    checkpoints: list[LabCheckpointSpec] = Field(min_length=1)
    policy: LabPolicySpec

    @model_validator(mode="after")
    def validate_editable_region(self) -> "BoundedPythonLabConfig":
        lines = [line for line in self.default_code.splitlines() if line.strip()]
        if not self.policy.min_editable_lines <= len(lines) <= self.policy.max_editable_lines:
            raise ValueError("Default code does not match its declared editable-line bounds")
        if self.policy.min_editable_lines > self.policy.max_editable_lines:
            raise ValueError("Minimum editable lines cannot exceed maximum editable lines")
        for values, label in (
            (self.policy.allowed_assignments, "allowed assignments"),
            (self.policy.allowed_calls, "allowed calls"),
            (self.policy.allowed_attributes, "allowed attributes"),
            (self.trusted_setup.exports, "trusted setup exports"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Lab {label} must be unique")
        return self
