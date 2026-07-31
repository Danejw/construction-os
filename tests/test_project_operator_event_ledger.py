import pytest

from construction_os.project_operator.event_ledger import (
    EventActorType,
    InMemoryProjectEventRepository,
    ProjectEventCreate,
    ProjectEventLedgerService,
    ProjectEventType,
    RecordTransitionRequest,
    StateReconciliationService,
)
from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    InMemoryOperationalStateRepository,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)


@pytest.mark.asyncio
async def test_event_sequences_are_append_only_and_replayable() -> None:
    repository = InMemoryProjectEventRepository()
    ledger = ProjectEventLedgerService(repository)

    first = await ledger.append(
        "project:alpha",
        ProjectEventCreate(
            entity_type="commitment",
            entity_id="operator_record:one",
            event_type=ProjectEventType.COMMITMENT_DETECTED,
            previous_state={"status": "proposed"},
            new_state={"status": "active", "due_date": "2026-08-10"},
            reason="Initial commitment confirmed",
            actor_type=EventActorType.HUMAN,
            actor_id="user:one",
        ),
    )
    second = await ledger.append(
        "project:alpha",
        ProjectEventCreate(
            entity_type="commitment",
            entity_id="operator_record:one",
            event_type=ProjectEventType.COMMITMENT_CHANGED,
            previous_state={"due_date": "2026-08-10"},
            new_state={"due_date": "2026-08-18"},
            reason="Approved schedule revision",
            actor_type=EventActorType.HUMAN,
            actor_id="user:one",
        ),
    )

    assert first.sequence == 1
    assert second.sequence == 2
    replayed = await ledger.replay_entity("project:alpha", "operator_record:one")
    assert replayed["status"] == "active"
    assert replayed["due_date"] == "2026-08-18"
    assert second.previous_state["due_date"] == "2026-08-10"


@pytest.mark.asyncio
async def test_human_correction_is_distinguishable() -> None:
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    event = await ledger.append(
        "project:alpha",
        ProjectEventCreate(
            entity_type="risk",
            entity_id="operator_record:risk",
            event_type=ProjectEventType.HUMAN_CORRECTION_RECEIVED,
            previous_state={"severity": "high"},
            new_state={"severity": "medium"},
            reason="Project manager corrected the severity",
            actor_type=EventActorType.HUMAN,
            actor_id="user:pm",
        ),
    )

    assert event.actor_type == EventActorType.HUMAN
    assert event.event_type == ProjectEventType.HUMAN_CORRECTION_RECEIVED


@pytest.mark.asyncio
async def test_transition_preserves_prior_record_state() -> None:
    state_repository = InMemoryOperationalStateRepository()
    state_service = OperationalStateService(state_repository)
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    reconciliation = StateReconciliationService(state_repository, ledger)

    evidence = await state_service.create_evidence(
        "project:alpha",
        EvidenceCreate(
            source_id="source:email",
            source_type="email",
            quoted_text="Plans are now due August 18.",
        ),
    )
    record = await state_service.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.COMMITMENT,
            title="Plans delivery",
            description="Plans due August 10.",
            status=OperationalStatus.ACTIVE,
            confidence=1.0,
            evidence_ids=[evidence.id],
            attributes={"due_date": "2026-08-10"},
        ),
    )

    updated, event = await reconciliation.transition(
        "project:alpha",
        record.id,
        RecordTransitionRequest(
            changes={
                "description": "Plans due August 18.",
                "attributes": {"due_date": "2026-08-18"},
            },
            event_type=ProjectEventType.COMMITMENT_CHANGED,
            reason="New approved delivery date",
            actor_type=EventActorType.HUMAN,
            actor_id="user:pm",
            evidence_ids=[evidence.id],
        ),
    )

    assert updated.attributes["due_date"] == "2026-08-18"
    assert event.previous_state["attributes"]["due_date"] == "2026-08-10"
    assert event.new_state["attributes"]["due_date"] == "2026-08-18"


@pytest.mark.asyncio
async def test_transition_rejects_uncontrolled_fields() -> None:
    state_repository = InMemoryOperationalStateRepository()
    state_service = OperationalStateService(state_repository)
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    reconciliation = StateReconciliationService(state_repository, ledger)
    evidence = await state_service.create_evidence(
        "project:alpha",
        EvidenceCreate(
            source_id="source:one",
            source_type="note",
            quoted_text="Issue recorded.",
        ),
    )
    record = await state_service.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.ISSUE,
            title="Issue",
            description="Open issue",
            confidence=1.0,
            evidence_ids=[evidence.id],
        ),
    )

    with pytest.raises(ValueError, match="unsupported state changes"):
        await reconciliation.transition(
            "project:alpha",
            record.id,
            RecordTransitionRequest(
                changes={"project_id": "project:beta"},
                event_type=ProjectEventType.ISSUE_RESOLVED,
                reason="Invalid project reassignment",
                actor_type=EventActorType.AGENT,
                actor_id="agent:test",
            ),
        )
