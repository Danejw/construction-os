"""Guarded, auditable action runtime for approved Project Operator work."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.event_ledger import (
    EventActorType,
    ProjectEventCreate,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.permissions import ProjectOperatorPermissions
from construction_os.project_operator.service import ProjectOperatorService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperatorActionType(StrEnum):
    DRAFT_PROJECT_EMAIL = "draft_project_email"
    CREATE_INTERNAL_TASK = "create_internal_task"
    CREATE_CALENDAR_REMINDER = "create_calendar_reminder"
    GENERATE_RFI_DRAFT = "generate_rfi_draft"
    GENERATE_MEETING_AGENDA = "generate_meeting_agenda"
    REQUEST_INFORMATION = "request_information"
    UPDATE_NONCRITICAL_STATUS = "update_noncritical_status"
    GENERATE_PROJECT_SUMMARY = "generate_project_summary"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class ExecutionStatus(StrEnum):
    DRY_RUN = "dry_run"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActionDefinition(BaseModel):
    action_type: OperatorActionType
    required_inputs: list[str]
    allowed_roles: list[str]
    approval_required: bool = True
    dry_run_supported: bool = True
    execution_tool: str
    verification_method: str
    external_side_effect: bool = False


ACTION_DEFINITIONS: dict[OperatorActionType, ActionDefinition] = {
    OperatorActionType.DRAFT_PROJECT_EMAIL: ActionDefinition(
        action_type=OperatorActionType.DRAFT_PROJECT_EMAIL,
        required_inputs=["recipient", "subject", "body"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.draft_email",
        verification_method="draft_content_returned",
    ),
    OperatorActionType.CREATE_INTERNAL_TASK: ActionDefinition(
        action_type=OperatorActionType.CREATE_INTERNAL_TASK,
        required_inputs=["title", "description"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.create_internal_task",
        verification_method="task_reference_returned",
    ),
    OperatorActionType.CREATE_CALENDAR_REMINDER: ActionDefinition(
        action_type=OperatorActionType.CREATE_CALENDAR_REMINDER,
        required_inputs=["title", "scheduled_for"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.create_calendar_reminder",
        verification_method="reminder_reference_returned",
    ),
    OperatorActionType.GENERATE_RFI_DRAFT: ActionDefinition(
        action_type=OperatorActionType.GENERATE_RFI_DRAFT,
        required_inputs=["subject", "question", "background"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.generate_rfi_draft",
        verification_method="rfi_draft_returned",
    ),
    OperatorActionType.GENERATE_MEETING_AGENDA: ActionDefinition(
        action_type=OperatorActionType.GENERATE_MEETING_AGENDA,
        required_inputs=["title", "topics"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.generate_meeting_agenda",
        verification_method="agenda_returned",
    ),
    OperatorActionType.REQUEST_INFORMATION: ActionDefinition(
        action_type=OperatorActionType.REQUEST_INFORMATION,
        required_inputs=["recipient", "request"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.prepare_information_request",
        verification_method="request_draft_returned",
    ),
    OperatorActionType.UPDATE_NONCRITICAL_STATUS: ActionDefinition(
        action_type=OperatorActionType.UPDATE_NONCRITICAL_STATUS,
        required_inputs=["entity_id", "status"],
        allowed_roles=["project_manager", "administrator"],
        execution_tool="operator.update_noncritical_status",
        verification_method="status_confirmation_returned",
    ),
    OperatorActionType.GENERATE_PROJECT_SUMMARY: ActionDefinition(
        action_type=OperatorActionType.GENERATE_PROJECT_SUMMARY,
        required_inputs=["title", "content"],
        allowed_roles=["project_manager", "administrator", "viewer"],
        execution_tool="operator.generate_project_summary",
        verification_method="summary_returned",
    ),
}


class ProposedActionCreate(BaseModel):
    action_type: OperatorActionType
    title: str
    reason: str
    inputs: dict[str, object]
    evidence_ids: list[str] = Field(min_length=1)
    signal_id: str | None = None
    proposed_by: str = "project-operator"

    @field_validator("title", "reason", "proposed_by")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("action text fields cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_inputs(self) -> "ProposedActionCreate":
        definition = ACTION_DEFINITIONS[self.action_type]
        missing = [
            key for key in definition.required_inputs if not self.inputs.get(key)
        ]
        if missing:
            raise ValueError(f"missing required action inputs: {missing}")
        return self


class ProposedAction(ProposedActionCreate):
    id: str
    project_id: str
    status: ActionStatus = ActionStatus.PROPOSED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ActionDecisionRequest(BaseModel):
    actor_id: str
    actor_role: str
    reason: str | None = None

    @field_validator("actor_id", "actor_role")
    @classmethod
    def required_identity(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("actor identity and role cannot be empty")
        return normalized


class ActionApproval(BaseModel):
    id: str
    project_id: str
    action_id: str
    approved: bool
    actor_id: str
    actor_role: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ActionExecutionRequest(BaseModel):
    actor_id: str
    actor_role: str
    idempotency_key: str

    @field_validator("actor_id", "actor_role", "idempotency_key")
    @classmethod
    def required_execution_identity(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(
                "execution identity and idempotency key cannot be empty"
            )
        return normalized


class ActionExecution(BaseModel):
    id: str
    project_id: str
    action_id: str
    idempotency_key: str
    status: ExecutionStatus
    dry_run: bool
    tool_name: str
    arguments: dict[str, object]
    result: dict[str, object]
    verified: bool
    error: str | None = None
    actor_id: str
    created_at: datetime = Field(default_factory=utc_now)


class ActionRepository(Protocol):
    async def save_action(self, action: ProposedAction) -> ProposedAction: ...

    async def get_action(self, action_id: str) -> ProposedAction | None: ...

    async def list_actions(self, project_id: str) -> list[ProposedAction]: ...

    async def save_approval(self, approval: ActionApproval) -> ActionApproval: ...

    async def latest_approval(self, action_id: str) -> ActionApproval | None: ...

    async def save_execution(self, execution: ActionExecution) -> ActionExecution: ...

    async def get_execution_by_key(
        self, idempotency_key: str
    ) -> ActionExecution | None: ...


class InMemoryActionRepository:
    def __init__(self) -> None:
        self._actions: dict[str, ProposedAction] = {}
        self._approvals: list[ActionApproval] = []
        self._executions: dict[str, ActionExecution] = {}
        self._lock = asyncio.Lock()

    async def save_action(self, action: ProposedAction) -> ProposedAction:
        async with self._lock:
            self._actions[action.id] = action.model_copy(deep=True)
            return action.model_copy(deep=True)

    async def get_action(self, action_id: str) -> ProposedAction | None:
        async with self._lock:
            action = self._actions.get(action_id)
            return action.model_copy(deep=True) if action else None

    async def list_actions(self, project_id: str) -> list[ProposedAction]:
        async with self._lock:
            actions = [
                action.model_copy(deep=True)
                for action in self._actions.values()
                if action.project_id == project_id
            ]
        return sorted(actions, key=lambda item: item.created_at, reverse=True)

    async def save_approval(self, approval: ActionApproval) -> ActionApproval:
        async with self._lock:
            self._approvals.append(approval.model_copy(deep=True))
            return approval.model_copy(deep=True)

    async def latest_approval(self, action_id: str) -> ActionApproval | None:
        async with self._lock:
            matches = [
                item for item in self._approvals if item.action_id == action_id
            ]
            return matches[-1].model_copy(deep=True) if matches else None

    async def save_execution(self, execution: ActionExecution) -> ActionExecution:
        async with self._lock:
            self._executions[execution.idempotency_key] = execution.model_copy(
                deep=True
            )
            return execution.model_copy(deep=True)

    async def get_execution_by_key(
        self, idempotency_key: str
    ) -> ActionExecution | None:
        async with self._lock:
            item = self._executions.get(idempotency_key)
            return item.model_copy(deep=True) if item else None


class SurrealActionRepository:
    async def _ensure_tables(self) -> None:
        await repo_query(
            "DEFINE TABLE IF NOT EXISTS operator_action SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_approval SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_execution SCHEMALESS;"
        )

    async def _upsert(
        self, record_id: str, model: BaseModel
    ) -> dict[str, object]:
        await self._ensure_tables()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(record_id),
                "data": model.model_dump(mode="json", exclude={"id"}),
            },
        )
        return result[0]

    async def save_action(self, action: ProposedAction) -> ProposedAction:
        return ProposedAction(
            id=action.id,
            **await self._upsert(action.id, action),
        )

    async def get_action(self, action_id: str) -> ProposedAction | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id(action_id)},
        )
        return ProposedAction(id=action_id, **result[0]) if result else None

    async def list_actions(self, project_id: str) -> list[ProposedAction]:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM operator_action WHERE project_id = $project_id "
            "ORDER BY created_at DESC;",
            {"project_id": project_id},
        )
        return [ProposedAction(**item) for item in result]

    async def save_approval(self, approval: ActionApproval) -> ActionApproval:
        return ActionApproval(
            id=approval.id,
            **await self._upsert(approval.id, approval),
        )

    async def latest_approval(self, action_id: str) -> ActionApproval | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM operator_approval WHERE action_id = $action_id "
            "ORDER BY created_at DESC LIMIT 1;",
            {"action_id": action_id},
        )
        return ActionApproval(**result[0]) if result else None

    async def save_execution(self, execution: ActionExecution) -> ActionExecution:
        return ActionExecution(
            id=execution.id,
            **await self._upsert(execution.id, execution),
        )

    async def get_execution_by_key(
        self, idempotency_key: str
    ) -> ActionExecution | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM operator_execution WHERE idempotency_key = $key "
            "LIMIT 1;",
            {"key": idempotency_key},
        )
        return ActionExecution(**result[0]) if result else None


class SafeActionExecutor:
    """Deterministic executor for bounded internal and draft-producing actions."""

    async def execute(
        self,
        definition: ActionDefinition,
        inputs: dict[str, object],
        *,
        dry_run: bool,
    ) -> dict[str, object]:
        if definition.external_side_effect:
            raise ValueError("external side effects are not enabled in this runtime")
        return {
            "tool": definition.execution_tool,
            "mode": "dry_run" if dry_run else "executed",
            "output": dict(inputs),
            "reference": f"operator-result:{uuid4().hex}",
        }


class ActionRuntimeService:
    def __init__(
        self,
        repository: ActionRepository,
        operator: ProjectOperatorService,
        ledger: ProjectEventLedgerService,
        executor: SafeActionExecutor | None = None,
    ) -> None:
        self.repository = repository
        self.operator = operator
        self.ledger = ledger
        self.executor = executor or SafeActionExecutor()

    async def propose(
        self, project_id: str, body: ProposedActionCreate
    ) -> ProposedAction:
        config = await self.operator.get_config(project_id)
        if not ProjectOperatorPermissions.can_recommend(config):
            raise ValueError(
                "project operator configuration does not allow recommendations"
            )
        now = utc_now()
        action = ProposedAction(
            id=f"operator_action:{uuid4().hex}",
            project_id=project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        saved = await self.repository.save_action(action)
        await self._event(
            saved,
            ProjectEventType.ACTION_PROPOSED,
            "Action proposed",
            EventActorType.AGENT,
            body.proposed_by,
        )
        return saved

    async def list_actions(self, project_id: str) -> list[ProposedAction]:
        return await self.repository.list_actions(project_id)

    async def decide(
        self,
        project_id: str,
        action_id: str,
        decision: ActionDecisionRequest,
        *,
        approved: bool,
    ) -> ProposedAction:
        action = await self._get_project_action(project_id, action_id)
        definition = ACTION_DEFINITIONS[action.action_type]
        if decision.actor_role not in definition.allowed_roles:
            raise ValueError("actor role is not allowed to decide this action")
        approval = ActionApproval(
            id=f"operator_approval:{uuid4().hex}",
            project_id=project_id,
            action_id=action_id,
            approved=approved,
            actor_id=decision.actor_id,
            actor_role=decision.actor_role,
            reason=decision.reason,
        )
        await self.repository.save_approval(approval)
        updated = action.model_copy(
            update={
                "status": (
                    ActionStatus.APPROVED if approved else ActionStatus.REJECTED
                ),
                "updated_at": utc_now(),
            }
        )
        saved = await self.repository.save_action(updated)
        await self._event(
            saved,
            (
                ProjectEventType.ACTION_APPROVED
                if approved
                else ProjectEventType.ACTION_REJECTED
            ),
            decision.reason
            or ("Action approved" if approved else "Action rejected"),
            EventActorType.HUMAN,
            decision.actor_id,
        )
        return saved

    async def dry_run(
        self,
        project_id: str,
        action_id: str,
        request: ActionExecutionRequest,
    ) -> ActionExecution:
        action = await self._get_project_action(project_id, action_id)
        definition = ACTION_DEFINITIONS[action.action_type]
        if request.actor_role not in definition.allowed_roles:
            raise ValueError("actor role is not allowed to dry-run this action")
        if not definition.dry_run_supported:
            raise ValueError("this action does not support dry runs")
        dry_run_request = request.model_copy(
            update={
                "idempotency_key": f"dry-run:{request.idempotency_key}",
            }
        )
        existing = await self.repository.get_execution_by_key(
            dry_run_request.idempotency_key
        )
        if existing:
            if existing.project_id != project_id or existing.action_id != action_id:
                raise ValueError("idempotency key is already used by another action")
            return existing
        return await self._execute(
            action,
            dry_run_request,
            definition,
            dry_run=True,
        )

    async def execute(
        self,
        project_id: str,
        action_id: str,
        request: ActionExecutionRequest,
    ) -> ActionExecution:
        existing = await self.repository.get_execution_by_key(
            request.idempotency_key
        )
        if existing:
            if existing.project_id != project_id or existing.action_id != action_id:
                raise ValueError("idempotency key is already used by another action")
            return existing
        action = await self._get_project_action(project_id, action_id)
        if action.status == ActionStatus.EXECUTED:
            raise ValueError("action has already been executed")
        definition = ACTION_DEFINITIONS[action.action_type]
        config = await self.operator.get_config(project_id)
        if not ProjectOperatorPermissions.can_execute_approved(
            config,
            approved=True,
        ):
            raise ValueError(
                "project operator configuration does not allow approved execution"
            )
        approval = await self.repository.latest_approval(action_id)
        if definition.approval_required and (
            approval is None or not approval.approved
        ):
            raise ValueError("action requires an explicit approval")
        if request.actor_role not in definition.allowed_roles:
            raise ValueError("actor role is not allowed to execute this action")
        execution = await self._execute(
            action,
            request,
            definition,
            dry_run=False,
        )
        updated = action.model_copy(
            update={
                "status": (
                    ActionStatus.EXECUTED
                    if execution.verified
                    else ActionStatus.FAILED
                ),
                "updated_at": utc_now(),
            }
        )
        await self.repository.save_action(updated)
        await self._event(
            updated,
            (
                ProjectEventType.ACTION_EXECUTED
                if execution.verified
                else ProjectEventType.ACTION_FAILED
            ),
            (
                "Action execution verified"
                if execution.verified
                else "Action execution failed verification"
            ),
            EventActorType.TOOL,
            definition.execution_tool,
        )
        return execution

    async def _execute(
        self,
        action: ProposedAction,
        request: ActionExecutionRequest,
        definition: ActionDefinition,
        *,
        dry_run: bool,
    ) -> ActionExecution:
        result = await self.executor.execute(
            definition,
            action.inputs,
            dry_run=dry_run,
        )
        verified = bool(
            result.get("reference") and result.get("output") is not None
        )
        execution = ActionExecution(
            id=f"operator_execution:{uuid4().hex}",
            project_id=action.project_id,
            action_id=action.id,
            idempotency_key=request.idempotency_key,
            status=(
                ExecutionStatus.DRY_RUN
                if dry_run
                else (
                    ExecutionStatus.SUCCEEDED
                    if verified
                    else ExecutionStatus.FAILED
                )
            ),
            dry_run=dry_run,
            tool_name=definition.execution_tool,
            arguments=action.inputs,
            result=result,
            verified=verified,
            actor_id=request.actor_id,
        )
        return await self.repository.save_execution(execution)

    async def _get_project_action(
        self,
        project_id: str,
        action_id: str,
    ) -> ProposedAction:
        action = await self.repository.get_action(action_id)
        if action is None or action.project_id != project_id:
            raise ValueError("action is unavailable for this project")
        return action

    async def _event(
        self,
        action: ProposedAction,
        event_type: ProjectEventType,
        reason: str,
        actor_type: EventActorType,
        actor_id: str,
    ) -> None:
        await self.ledger.append(
            action.project_id,
            ProjectEventCreate(
                entity_type="proposed_action",
                entity_id=action.id,
                event_type=event_type,
                new_state=action.model_dump(mode="json"),
                reason=reason,
                actor_type=actor_type,
                actor_id=actor_id,
                evidence_ids=action.evidence_ids,
            ),
        )
