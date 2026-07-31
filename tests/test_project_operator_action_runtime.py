import pytest
from pydantic import ValidationError

from construction_os.project_operator.action_runtime import (
    ActionDecisionRequest,
    ActionExecutionRequest,
    ActionRuntimeService,
    ActionStatus,
    ExecutionStatus,
    InMemoryActionRepository,
    OperatorActionType,
    ProposedActionCreate,
)
from construction_os.project_operator.event_ledger import (
    InMemoryProjectEventRepository,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.models import (
    OperatorAutomationLevel,
    OperatorConfigUpdate,
    OperatorMode,
)
from construction_os.project_operator.repository import (
    InMemoryProjectOperatorRepository,
)
from construction_os.project_operator.service import ProjectOperatorService


async def _runtime(
    level: OperatorAutomationLevel = OperatorAutomationLevel.EXECUTE_APPROVED,
) -> tuple[ActionRuntimeService, ProjectEventLedgerService]:
    operator = ProjectOperatorService(InMemoryProjectOperatorRepository())
    await operator.update_config(
        "project:alpha",
        OperatorConfigUpdate(
            enabled=True,
            mode=OperatorMode.MANUAL,
            automation_level=level,
        ),
    )
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    return ActionRuntimeService(InMemoryActionRepository(), operator, ledger), ledger


def _proposal() -> ProposedActionCreate:
    return ProposedActionCreate(
        action_type=OperatorActionType.DRAFT_PROJECT_EMAIL,
        title="Request lead-time confirmation",
        reason="The current project state has no confirmed delivery date.",
        inputs={
            "recipient": "plumbing-subcontractor",
            "subject": "Grease interceptor lead time",
            "body": "Please confirm manufacturer, availability, and delivery date.",
        },
        evidence_ids=["operator_evidence:lead-time"],
        signal_id="operator_signal:missing-information",
    )


@pytest.mark.asyncio
async def test_proposal_requires_recommend_permission() -> None:
    operator = ProjectOperatorService(InMemoryProjectOperatorRepository())
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    runtime = ActionRuntimeService(InMemoryActionRepository(), operator, ledger)

    with pytest.raises(ValueError, match="does not allow recommendations"):
        await runtime.propose("project:alpha", _proposal())


@pytest.mark.asyncio
async def test_action_requires_explicit_approval_before_execution() -> None:
    runtime, _ledger = await _runtime()
    action = await runtime.propose("project:alpha", _proposal())
    request = ActionExecutionRequest(
        actor_id="user:pm",
        actor_role="project_manager",
        idempotency_key="execute-action-one",
    )

    dry_run = await runtime.dry_run("project:alpha", action.id, request)
    assert dry_run.status == ExecutionStatus.DRY_RUN
    assert dry_run.dry_run is True
    assert dry_run.arguments == action.inputs

    with pytest.raises(ValueError, match="explicit approval"):
        await runtime.execute("project:alpha", action.id, request)


@pytest.mark.asyncio
async def test_approved_action_executes_once_and_records_audit_events() -> None:
    runtime, ledger = await _runtime()
    action = await runtime.propose("project:alpha", _proposal())
    approved = await runtime.decide(
        "project:alpha",
        action.id,
        ActionDecisionRequest(
            actor_id="user:pm",
            actor_role="project_manager",
            reason="The request is accurate and ready.",
        ),
        approved=True,
    )
    request = ActionExecutionRequest(
        actor_id="user:pm",
        actor_role="project_manager",
        idempotency_key="approved-action-one",
    )

    first = await runtime.execute("project:alpha", action.id, request)
    second = await runtime.execute("project:alpha", action.id, request)

    assert approved.status == ActionStatus.APPROVED
    assert first.status == ExecutionStatus.SUCCEEDED
    assert first.verified is True
    assert second.id == first.id
    assert first.result["reference"].startswith("operator-result:")
    events = await ledger.list_events("project:alpha", action.id)
    assert [event.event_type for event in events] == [
        ProjectEventType.ACTION_PROPOSED,
        ProjectEventType.ACTION_APPROVED,
        ProjectEventType.ACTION_EXECUTED,
    ]


@pytest.mark.asyncio
async def test_action_decision_is_role_bounded() -> None:
    runtime, _ledger = await _runtime()
    action = await runtime.propose("project:alpha", _proposal())

    with pytest.raises(ValueError, match="role is not allowed"):
        await runtime.decide(
            "project:alpha",
            action.id,
            ActionDecisionRequest(
                actor_id="user:viewer",
                actor_role="viewer",
            ),
            approved=True,
        )


@pytest.mark.asyncio
async def test_execution_requires_execute_approved_configuration() -> None:
    runtime, _ledger = await _runtime(OperatorAutomationLevel.RECOMMEND)
    action = await runtime.propose("project:alpha", _proposal())
    await runtime.decide(
        "project:alpha",
        action.id,
        ActionDecisionRequest(
            actor_id="user:pm",
            actor_role="project_manager",
        ),
        approved=True,
    )

    with pytest.raises(ValueError, match="does not allow approved execution"):
        await runtime.execute(
            "project:alpha",
            action.id,
            ActionExecutionRequest(
                actor_id="user:pm",
                actor_role="project_manager",
                idempotency_key="blocked-execution",
            ),
        )


def test_action_inputs_are_validated_before_proposal() -> None:
    with pytest.raises(ValidationError, match="missing required action inputs"):
        ProposedActionCreate(
            action_type=OperatorActionType.GENERATE_RFI_DRAFT,
            title="Incomplete RFI",
            reason="Missing information",
            inputs={"subject": "Exhaust routing"},
            evidence_ids=["operator_evidence:rfi"],
        )
