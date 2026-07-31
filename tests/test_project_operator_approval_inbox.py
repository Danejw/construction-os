from datetime import datetime, timezone

import pytest

from construction_os.project_operator.approval_inbox import (
    ApprovalInboxService,
    SignalCorrectionRequest,
)
from construction_os.project_operator.event_ledger import (
    EventActorType,
    InMemoryProjectEventRepository,
    ProjectEventCreate,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.operational_state import (
    InMemoryOperationalStateRepository,
    OperationalStateService,
)
from construction_os.project_operator.signal_detection import (
    InMemoryProjectSignalRepository,
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
    SignalSeverity,
)


def _signal(
    *,
    signal_id: str,
    signal_type: ProjectSignalType,
    severity: SignalSeverity,
    status: ProjectSignalStatus = ProjectSignalStatus.NEW,
) -> ProjectSignal:
    created_at = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    return ProjectSignal(
        id=signal_id,
        project_id="project:alpha",
        signal_type=signal_type,
        severity=severity,
        summary=f"Signal {signal_id}",
        why_it_matters="This affects the project operating state.",
        affected_entity_ids=["operator_record:one"],
        evidence_ids=["operator_evidence:one"],
        confidence=0.9,
        recommended_response="Review the evidence and confirm the next action.",
        fingerprint=f"fingerprint-{signal_id}",
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


def _services() -> tuple[
    InMemoryProjectSignalRepository,
    ProjectEventLedgerService,
    ApprovalInboxService,
]:
    signal_repository = InMemoryProjectSignalRepository()
    state_service = OperationalStateService(InMemoryOperationalStateRepository())
    signal_service = ProjectSignalDetectionService(state_service, signal_repository)
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    inbox = ApprovalInboxService(signal_service, ledger)
    return signal_repository, ledger, inbox


@pytest.mark.asyncio
async def test_inbox_groups_changes_attention_and_recommended_actions() -> None:
    repository, _ledger, inbox = _services()
    change = await repository.save(
        _signal(
            signal_id="operator_signal:change",
            signal_type=ProjectSignalType.DOCUMENT_REVISION,
            severity=SignalSeverity.MEDIUM,
        )
    )
    attention = await repository.save(
        _signal(
            signal_id="operator_signal:conflict",
            signal_type=ProjectSignalType.CONFLICT,
            severity=SignalSeverity.HIGH,
        )
    )

    result = await inbox.build("project:alpha")

    assert [item.id for item in result.what_changed] == [change.id]
    assert [item.id for item in result.needs_attention] == [attention.id]
    assert {item.id for item in result.recommended_actions} == {
        change.id,
        attention.id,
    }
    assert result.needs_attention[0].evidence_ids == ["operator_evidence:one"]


@pytest.mark.asyncio
async def test_dismissed_and_resolved_signals_are_hidden() -> None:
    repository, _ledger, inbox = _services()
    await repository.save(
        _signal(
            signal_id="operator_signal:dismissed",
            signal_type=ProjectSignalType.MISSING_INFORMATION,
            severity=SignalSeverity.MEDIUM,
            status=ProjectSignalStatus.DISMISSED,
        )
    )
    await repository.save(
        _signal(
            signal_id="operator_signal:resolved",
            signal_type=ProjectSignalType.OVERDUE_ITEM,
            severity=SignalSeverity.HIGH,
            status=ProjectSignalStatus.RESOLVED,
        )
    )

    result = await inbox.build("project:alpha")

    assert result.what_changed == []
    assert result.needs_attention == []
    assert result.recommended_actions == []


@pytest.mark.asyncio
async def test_human_correction_resolves_signal_and_records_event() -> None:
    repository, ledger, inbox = _services()
    signal = await repository.save(
        _signal(
            signal_id="operator_signal:incorrect",
            signal_type=ProjectSignalType.CONFLICT,
            severity=SignalSeverity.HIGH,
        )
    )

    corrected = await inbox.correct_signal(
        "project:alpha",
        signal.id,
        SignalCorrectionRequest(
            corrected_summary="The accepted date is August 18.",
            explanation="The newer approved schedule supersedes the old date.",
            actor_id="user:project-manager",
        ),
    )

    assert corrected.status == ProjectSignalStatus.RESOLVED
    events = await ledger.list_events("project:alpha", signal.id)
    assert len(events) == 1
    assert events[0].event_type == ProjectEventType.HUMAN_CORRECTION_RECEIVED
    assert events[0].actor_type == EventActorType.HUMAN
    assert events[0].actor_id == "user:project-manager"
    assert events[0].new_state["corrected_summary"] == (
        "The accepted date is August 18."
    )


@pytest.mark.asyncio
async def test_recent_activity_is_newest_first() -> None:
    _repository, ledger, inbox = _services()
    first = await ledger.append(
        "project:alpha",
        ProjectEventCreate(
            entity_type="project_signal",
            entity_id="operator_signal:first",
            event_type=ProjectEventType.ACTION_PROPOSED,
            reason="First activity",
            actor_type=EventActorType.SYSTEM,
            actor_id="project-operator",
        ),
    )
    second = await ledger.append(
        "project:alpha",
        ProjectEventCreate(
            entity_type="project_signal",
            entity_id="operator_signal:second",
            event_type=ProjectEventType.ACTION_APPROVED,
            reason="Second activity",
            actor_type=EventActorType.HUMAN,
            actor_id="user:project-manager",
        ),
    )

    result = await inbox.build("project:alpha")

    assert [item.id for item in result.recent_activity] == [second.id, first.id]
