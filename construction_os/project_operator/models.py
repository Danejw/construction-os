"""Typed configuration and operation contracts for the Project Operator."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OperatorMode(StrEnum):
    """How operator runs are initiated for a project."""

    DISABLED = "disabled"
    MANUAL = "manual"
    SOURCE_TRIGGERED = "source_triggered"
    SCHEDULED = "scheduled"


class OperatorAutomationLevel(StrEnum):
    """Maximum behavior the operator may perform for a project."""

    DISABLED = "disabled"
    OBSERVE_ONLY = "observe_only"
    RECOMMEND = "recommend"
    EXECUTE_APPROVED = "execute_approved"


class OperatorOperation(StrEnum):
    """Stable service boundary for current and future operator workflows."""

    INGEST_EVENT = "ingest_event"
    ANALYZE_PROJECT = "analyze_project"
    PROPOSE_ACTION = "propose_action"
    APPROVE_ACTION = "approve_action"
    EXECUTE_ACTION = "execute_action"


class OperatorConfig(BaseModel):
    """Project-scoped Project Operator configuration."""

    project_id: str
    enabled: bool = False
    mode: OperatorMode = OperatorMode.DISABLED
    automation_level: OperatorAutomationLevel = OperatorAutomationLevel.DISABLED
    allowed_source_types: list[str] = Field(default_factory=list)
    approval_policy: dict[str, str | bool | int] = Field(default_factory=dict)
    last_operator_run: datetime | None = None

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("project:"):
            raise ValueError("project_id must identify a project record")
        return normalized

    @field_validator("allowed_source_types")
    @classmethod
    def normalize_source_types(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value or "").strip().lower()
            if item and item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def validate_disabled_state(self) -> "OperatorConfig":
        if not self.enabled:
            self.mode = OperatorMode.DISABLED
            self.automation_level = OperatorAutomationLevel.DISABLED
        elif self.mode == OperatorMode.DISABLED:
            raise ValueError("enabled operator config requires an active mode")
        elif self.automation_level == OperatorAutomationLevel.DISABLED:
            raise ValueError("enabled operator config requires an automation level")
        return self


class OperatorConfigUpdate(BaseModel):
    """Mutable project-level operator settings accepted by the API."""

    enabled: bool
    mode: OperatorMode = OperatorMode.DISABLED
    automation_level: OperatorAutomationLevel = OperatorAutomationLevel.DISABLED
    allowed_source_types: list[str] = Field(default_factory=list)
    approval_policy: dict[str, str | bool | int] = Field(default_factory=dict)


class OperatorOperationRequest(BaseModel):
    """Generic bounded input for a foundation-stage operator operation."""

    payload: dict[str, object] = Field(default_factory=dict)
    approved: bool = False


class OperatorOperationResult(BaseModel):
    """Stable response returned from the operator service boundary."""

    project_id: str
    operation: OperatorOperation
    accepted: bool
    status: Literal["blocked", "accepted", "completed"]
    detail: str
    payload: dict[str, object] = Field(default_factory=dict)
