"""Append-only Project Operator event ledger and state reconciliation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.operational_state import (
    OperationalRecord,
    OperationalStateRepository,
    OperationalStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectEventType(StrEnum):
    OBSERVATION_DETECTED = "ObservationDetected"
    OBSERVATION_REJECTED = "ObservationRejected"
    FACT_PROPOSED = "FactProposed"
    FACT_CONFIRMED = "FactConfirmed"
    FACT_SUPERSEDED = "FactSuperseded"
    COMMITMENT_DETECTED = "CommitmentDetected"
    COMMITMENT_CONFIRMED = "CommitmentConfirmed"
    COMMITMENT_CHANGED = "CommitmentChanged"
    COMMITMENT_COMPLETED = "CommitmentCompleted"
    ISSUE_DETECTED = "IssueDetected"
    ISSUE_RESOLVED = "IssueResolved"
    RISK_DETECTED = "RiskDetected"
    RISK_CHANGED = "RiskChanged"
    ACTION_PROPOSED = "ActionProposed"
    ACTION_APPROVED = "ActionApproved"
    ACTION_REJECTED = "ActionRejected"
    ACTION_EXECUTED = "ActionExecuted"
    ACTION_FAILED = "ActionFailed"
    HUMAN_CORRECTION_RECEIVED = "HumanCorrectionReceived"


class EventActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"


class ProjectEventCreate(BaseModel):
    entity_type: str
    entity_id: str
    event_type: ProjectEventType
    previous_state: dict[str, object] = Field(default_factory=dict)
    new_state: dict[str, object] = Field(default_factory=dict)
    reason: str
    actor_type: EventActorType
    actor_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    correlation_id: str | None = None

    @field_validator("entity_type", "entity_id", "reason", "actor_id")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("event identity and reason fields cannot be empty")
        return normalized


class ProjectEvent(ProjectEventCreate):
    id: str
    project_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=utc_now)


class RecordTransitionRequest(BaseModel):
    changes: dict[str, object]
    event_type: ProjectEventType
    reason: str
    actor_type: EventActorType
    actor_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    correlation_id: str | None = None


class ProjectEventRepository(Protocol):
    async def append(self, event: ProjectEvent) -> ProjectEvent: ...

    async def list_events(
        self, project_id: str, entity_id: str | None = None
    ) -> list[ProjectEvent]: ...

    async def next_sequence(self, project_id: str) -> int: ...


class InMemoryProjectEventRepository:
    def __init__(self) -> None:
        self._events: list[ProjectEvent] = []
        self._lock = asyncio.Lock()

    async def append(self, event: ProjectEvent) -> ProjectEvent:
        async with self._lock:
            if any(item.id == event.id for item in self._events):
                raise ValueError("project events are append-only and IDs must be unique")
            self._events.append(event.model_copy(deep=True))
            return event.model_copy(deep=True)

    async def list_events(
        self, project_id: str, entity_id: str | None = None
    ) -> list[ProjectEvent]:
        async with self._lock:
            events = [
                item.model_copy(deep=True)
                for item in self._events
                if item.project_id == project_id
                and (entity_id is None or item.entity_id == entity_id)
            ]
        return sorted(events, key=lambda item: item.sequence)

    async def next_sequence(self, project_id: str) -> int:
        events = await self.list_events(project_id)
        return (events[-1].sequence + 1) if events else 1


class SurrealProjectEventRepository:
    async def _ensure_table(self) -> None:
        await repo_query("DEFINE TABLE IF NOT EXISTS operator_event SCHEMALESS;")

    async def append(self, event: ProjectEvent) -> ProjectEvent:
        await self._ensure_table()
        existing = await repo_query(
            "SELECT id FROM $id;", {"id": ensure_record_id(event.id)}
        )
        if existing:
            raise ValueError("project events are append-only and cannot be replaced")
        result = await repo_query(
            "CREATE $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(event.id),
                "data": event.model_dump(mode="json", exclude={"id"}),
            },
        )
        return ProjectEvent(id=event.id, **result[0])

    async def list_events(
        self, project_id: str, entity_id: str | None = None
    ) -> list[ProjectEvent]:
        await self._ensure_table()
        query = "SELECT * FROM operator_event WHERE project_id = $project_id"
        variables: dict[str, object] = {"project_id": project_id}
        if entity_id:
            query += " AND entity_id = $entity_id"
            variables["entity_id"] = entity_id
        result = await repo_query(f"{query} ORDER BY sequence ASC;", variables)
        return [ProjectEvent(**item) for item in result]

    async def next_sequence(self, project_id: str) -> int:
        await self._ensure_table()
        result = await repo_query(
            "SELECT math::max(sequence) AS sequence FROM operator_event "
            "WHERE project_id = $project_id GROUP ALL;",
            {"project_id": project_id},
        )
        maximum = result[0].get("sequence") if result else None
        return int(maximum or 0) + 1


class ProjectEventLedgerService:
    def __init__(self, repository: ProjectEventRepository) -> None:
        self.repository = repository

    async def append(
        self, project_id: str, body: ProjectEventCreate
    ) -> ProjectEvent:
        self._validate_project_id(project_id)
        sequence = await self.repository.next_sequence(project_id)
        event = ProjectEvent(
            id=f"operator_event:{uuid4().hex}",
            project_id=project_id,
            sequence=sequence,
            timestamp=utc_now(),
            correlation_id=body.correlation_id or uuid4().hex,
            **body.model_dump(exclude={"correlation_id"}),
        )
        return await self.repository.append(event)

    async def list_events(
        self, project_id: str, entity_id: str | None = None
    ) -> list[ProjectEvent]:
        self._validate_project_id(project_id)
        return await self.repository.list_events(project_id, entity_id)

    async def replay_entity(
        self, project_id: str, entity_id: str
    ) -> dict[str, object]:
        events = await self.list_events(project_id, entity_id)
        if not events:
            return {}
        state = dict(events[0].previous_state)
        for event in events:
            state.update(event.new_state)
        return state

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not str(project_id or "").startswith("project:"):
            raise ValueError("project_id must identify a project record")


class StateReconciliationService:
    """Changes current state only while preserving an explanatory ledger event."""

    _mutable_fields = {
        "title",
        "description",
        "status",
        "confidence",
        "valid_from",
        "valid_until",
        "responsible_party_id",
        "attributes",
    }

    def __init__(
        self,
        state_repository: OperationalStateRepository,
        ledger: ProjectEventLedgerService,
    ) -> None:
        self.state_repository = state_repository
        self.ledger = ledger

    async def transition(
        self,
        project_id: str,
        record_id: str,
        request: RecordTransitionRequest,
    ) -> tuple[OperationalRecord, ProjectEvent]:
        record = await self.state_repository.get_record(record_id)
        if record is None or record.project_id != project_id:
            raise ValueError("operational record is unavailable for this project")
        unsupported = set(request.changes) - self._mutable_fields
        if unsupported:
            raise ValueError(f"unsupported state changes: {sorted(unsupported)}")

        previous_state = record.model_dump(mode="json")
        changes = dict(request.changes)
        if "status" in changes:
            changes["status"] = OperationalStatus(str(changes["status"]))
        updated = record.model_copy(update={**changes, "updated_at": utc_now()})
        updated = OperationalRecord.model_validate(updated.model_dump())

        event = await self.ledger.append(
            project_id,
            ProjectEventCreate(
                entity_type="operational_record",
                entity_id=record_id,
                event_type=request.event_type,
                previous_state=previous_state,
                new_state=updated.model_dump(mode="json"),
                reason=request.reason,
                actor_type=request.actor_type,
                actor_id=request.actor_id,
                evidence_ids=request.evidence_ids,
                correlation_id=request.correlation_id,
            ),
        )
        saved = await self.state_repository.save_record(updated)
        return saved, event
