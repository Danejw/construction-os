from datetime import datetime, timezone

import pytest

from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    InMemoryOperationalStateRepository,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)
from construction_os.project_operator.signal_detection import (
    InMemoryProjectSignalRepository,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
    SignalSeverity,
)


async def _evidence(state: OperationalStateService, source_id: str) -> str:
    item = await state.create_evidence(
        "project:alpha",
        EvidenceCreate(
            source_id=source_id,
            source_type="email",
            quoted_text="Supporting project evidence.",
        ),
    )
    return item.id


@pytest.mark.asyncio
async def test_conflicting_commitment_date_creates_high_signal() -> None:
    state = OperationalStateService(InMemoryOperationalStateRepository())
    evidence_id = await _evidence(state, "source:commitment")
    await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.COMMITMENT,
            title="Hood shop drawings",
            description="Accepted shop drawing commitment.",
            status=OperationalStatus.ACTIVE,
            confidence=1.0,
            evidence_ids=[evidence_id],
            attributes={"due_date": "2026-08-10T00:00:00+00:00"},
        ),
    )
    observation = await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.OBSERVATION,
            title="Hood shop drawings will be due August 18",
            description="A later date was stated.",
            confidence=0.9,
            evidence_ids=[evidence_id],
            attributes={
                "category": "commitment",
                "expected_date": "2026-08-18T00:00:00+00:00",
            },
        ),
    )
    service = ProjectSignalDetectionService(
        state, InMemoryProjectSignalRepository()
    )

    signals = await service.detect("project:alpha")

    conflict = next(
        signal for signal in signals if signal.signal_type == ProjectSignalType.CONFLICT
    )
    assert conflict.severity == SignalSeverity.HIGH
    assert observation.id in conflict.affected_entity_ids
    assert conflict.evidence_ids == [evidence_id]


@pytest.mark.asyncio
async def test_overdue_commitment_uses_explicit_severity_rules() -> None:
    state = OperationalStateService(InMemoryOperationalStateRepository())
    evidence_id = await _evidence(state, "source:schedule")
    await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.COMMITMENT,
            title="Permit response",
            description="Permit response is due.",
            status=OperationalStatus.ACTIVE,
            confidence=1.0,
            evidence_ids=[evidence_id],
            attributes={"due_date": "2026-07-15T00:00:00+00:00"},
        ),
    )
    service = ProjectSignalDetectionService(
        state, InMemoryProjectSignalRepository()
    )

    signals = await service.detect(
        "project:alpha", now=datetime(2026, 7, 31, tzinfo=timezone.utc)
    )

    overdue = next(
        signal
        for signal in signals
        if signal.signal_type == ProjectSignalType.OVERDUE_ITEM
    )
    assert overdue.severity == SignalSeverity.HIGH
    assert "16 day(s)" in overdue.why_it_matters


@pytest.mark.asyncio
async def test_equivalent_signals_are_not_duplicated() -> None:
    state = OperationalStateService(InMemoryOperationalStateRepository())
    evidence_id = await _evidence(state, "source:request")
    await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.OBSERVATION,
            title="Please confirm the grease interceptor manufacturer",
            description="Manufacturer confirmation requested.",
            confidence=0.9,
            evidence_ids=[evidence_id],
            attributes={"category": "request"},
        ),
    )
    repository = InMemoryProjectSignalRepository()
    service = ProjectSignalDetectionService(state, repository)

    first = await service.detect("project:alpha")
    second = await service.detect("project:alpha")

    assert len(first) == 1
    assert second == []
    assert len(await service.list_signals("project:alpha")) == 1


@pytest.mark.asyncio
async def test_signal_review_status_is_project_scoped() -> None:
    state = OperationalStateService(InMemoryOperationalStateRepository())
    evidence_id = await _evidence(state, "source:risk")
    await state.create_record(
        "project:alpha",
        OperationalRecordCreate(
            record_type=OperationalRecordType.OBSERVATION,
            title="Material delay may affect the schedule",
            description="Explicit risk statement.",
            confidence=0.8,
            evidence_ids=[evidence_id],
            attributes={"category": "risk_statement"},
        ),
    )
    service = ProjectSignalDetectionService(
        state, InMemoryProjectSignalRepository()
    )
    signal = (await service.detect("project:alpha"))[0]

    reviewed = await service.update_status(
        "project:alpha", signal.id, ProjectSignalStatus.REVIEWED
    )

    assert reviewed.status == ProjectSignalStatus.REVIEWED
    with pytest.raises(ValueError, match="unavailable for this project"):
        await service.update_status(
            "project:beta", signal.id, ProjectSignalStatus.DISMISSED
        )
