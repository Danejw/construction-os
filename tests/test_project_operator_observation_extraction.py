from datetime import datetime, timezone

import pytest

from construction_os.project_operator.event_ledger import (
    InMemoryProjectEventRepository,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.observation_extraction import (
    ObservationCategory,
    ObservationExtractionService,
    RuleBasedObservationExtractor,
    SourceObservationRequest,
)
from construction_os.project_operator.operational_state import (
    InMemoryOperationalStateRepository,
    OperationalRecordType,
    OperationalStateService,
)


@pytest.mark.asyncio
async def test_extraction_creates_exact_evidence_and_ledger_event() -> None:
    state_repository = InMemoryOperationalStateRepository()
    state_service = OperationalStateService(state_repository)
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    service = ObservationExtractionService(state_service, ledger)

    records = await service.extract_and_store(
        "project:alpha",
        "source:email-one",
        SourceObservationRequest(
            source_type="email",
            content="Isaiah will deliver the architectural plans in about a week.",
            source_date=datetime(2026, 7, 29, tzinfo=timezone.utc),
        ),
    )

    assert len(records) == 1
    record = records[0]
    assert record.record_type == OperationalRecordType.OBSERVATION
    assert record.attributes["category"] == ObservationCategory.COMMITMENT.value
    assert record.attributes["expected_date"].startswith("2026-08-05")
    evidence = await state_repository.get_evidence(record.evidence_ids[0])
    assert evidence is not None
    assert evidence.quoted_text == "Isaiah will deliver the architectural plans in about a week."
    events = await ledger.list_events("project:alpha", record.id)
    assert events[0].event_type == ProjectEventType.OBSERVATION_DETECTED


@pytest.mark.asyncio
async def test_reprocessing_same_source_does_not_duplicate_observations() -> None:
    state_service = OperationalStateService(InMemoryOperationalStateRepository())
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    service = ObservationExtractionService(state_service, ledger)
    request = SourceObservationRequest(
        source_type="project_note",
        content="The mechanical drawing was revised and now supersedes the prior sheet.",
        source_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    first = await service.extract_and_store("project:alpha", "source:one", request)
    second = await service.extract_and_store("project:alpha", "source:one", request)

    assert len(first) == 1
    assert second == []


def test_rule_extractor_only_emits_explicit_supported_categories() -> None:
    extractor = RuleBasedObservationExtractor()
    request = SourceObservationRequest(
        source_type="meeting_note",
        content=(
            "Please confirm the grease interceptor manufacturer. "
            "The owner approved the tile selection. "
            "General discussion followed."
        ),
        source_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    observations = extractor.extract("source:meeting", request)

    assert [item.category for item in observations] == [
        ObservationCategory.REQUEST,
        ObservationCategory.DECISION,
    ]
    assert all(item.explicit for item in observations)
    assert all(item.quoted_text == item.statement for item in observations)


def test_relative_and_iso_dates_are_resolved_from_source_date() -> None:
    extractor = RuleBasedObservationExtractor()
    request = SourceObservationRequest(
        source_type="email",
        content=(
            "The architect will respond within 2 weeks. "
            "The permit response is due 2026-08-20."
        ),
        source_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    observations = extractor.extract("source:dates", request)

    assert observations[0].expected_date.isoformat().startswith("2026-08-14")
    assert observations[1].expected_date.isoformat().startswith("2026-08-20")
