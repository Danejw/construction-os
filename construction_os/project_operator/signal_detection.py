"""Rule-backed project signal detection for operational observations and state."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.operational_state import (
    OperationalRecord,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)


class ProjectSignalType(StrEnum):
    NEW_COMMITMENT = "new_commitment"
    CONFIRMATION = "confirmation"
    CONFLICT = "conflict"
    DOCUMENT_REVISION = "document_revision"
    OVERDUE_ITEM = "overdue_item"
    DEPENDENCY_RISK = "dependency_risk"
    MISSING_INFORMATION = "missing_information"
    UNRESOLVED_DECISION = "unresolved_decision"


class SignalSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectSignalStatus(StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    CONVERTED_TO_ACTION = "converted_to_action"


class ProjectSignalCreate(BaseModel):
    signal_type: ProjectSignalType
    severity: SignalSeverity
    summary: str
    why_it_matters: str
    affected_entity_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_response: str
    fingerprint: str


class ProjectSignal(ProjectSignalCreate):
    id: str
    project_id: str
    status: ProjectSignalStatus = ProjectSignalStatus.NEW
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ProjectSignalRepository(Protocol):
    async def save(self, signal: ProjectSignal) -> ProjectSignal: ...

    async def list_signals(
        self,
        project_id: str,
        status: ProjectSignalStatus | None = None,
    ) -> list[ProjectSignal]: ...

    async def get(self, signal_id: str) -> ProjectSignal | None: ...


class InMemoryProjectSignalRepository:
    def __init__(self) -> None:
        self._signals: dict[str, ProjectSignal] = {}
        self._lock = asyncio.Lock()

    async def save(self, signal: ProjectSignal) -> ProjectSignal:
        async with self._lock:
            self._signals[signal.id] = signal.model_copy(deep=True)
            return signal.model_copy(deep=True)

    async def list_signals(
        self,
        project_id: str,
        status: ProjectSignalStatus | None = None,
    ) -> list[ProjectSignal]:
        async with self._lock:
            signals = [
                signal.model_copy(deep=True)
                for signal in self._signals.values()
                if signal.project_id == project_id
            ]
        if status:
            signals = [signal for signal in signals if signal.status == status]
        return sorted(signals, key=lambda signal: signal.created_at, reverse=True)

    async def get(self, signal_id: str) -> ProjectSignal | None:
        async with self._lock:
            signal = self._signals.get(signal_id)
            return signal.model_copy(deep=True) if signal else None


class SurrealProjectSignalRepository:
    async def _ensure_table(self) -> None:
        await repo_query("DEFINE TABLE IF NOT EXISTS operator_signal SCHEMALESS;")

    async def save(self, signal: ProjectSignal) -> ProjectSignal:
        await self._ensure_table()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(signal.id),
                "data": signal.model_dump(mode="json", exclude={"id"}),
            },
        )
        return ProjectSignal(id=signal.id, **result[0])

    async def list_signals(
        self,
        project_id: str,
        status: ProjectSignalStatus | None = None,
    ) -> list[ProjectSignal]:
        await self._ensure_table()
        query = "SELECT * FROM operator_signal WHERE project_id = $project_id"
        variables: dict[str, object] = {"project_id": project_id}
        if status:
            query += " AND status = $status"
            variables["status"] = status.value
        result = await repo_query(f"{query} ORDER BY created_at DESC;", variables)
        return [ProjectSignal(**item) for item in result]

    async def get(self, signal_id: str) -> ProjectSignal | None:
        await self._ensure_table()
        result = await repo_query(
            "SELECT * FROM $id;", {"id": ensure_record_id(signal_id)}
        )
        return ProjectSignal(id=signal_id, **result[0]) if result else None


class ProjectSignalDetectionService:
    _stop_words = {
        "a",
        "an",
        "and",
        "are",
        "by",
        "for",
        "in",
        "is",
        "of",
        "on",
        "the",
        "to",
        "will",
    }

    def __init__(
        self,
        state_service: OperationalStateService,
        repository: ProjectSignalRepository,
    ) -> None:
        self.state_service = state_service
        self.repository = repository

    async def detect(
        self, project_id: str, *, now: datetime | None = None
    ) -> list[ProjectSignal]:
        current_time = now or datetime.now(timezone.utc)
        records = await self.state_service.list_records(project_id)
        existing = await self.repository.list_signals(project_id)
        fingerprints = {signal.fingerprint for signal in existing}
        candidates: list[ProjectSignalCreate] = []
        observations = [
            record
            for record in records
            if record.record_type == OperationalRecordType.OBSERVATION
            and record.status == OperationalStatus.PROPOSED
        ]
        accepted = [
            record
            for record in records
            if record.record_type != OperationalRecordType.OBSERVATION
            and record.status
            in {OperationalStatus.ACTIVE, OperationalStatus.PROPOSED}
        ]

        for observation in observations:
            candidate = self._signal_for_observation(observation, accepted)
            if candidate:
                candidates.append(candidate)

        for record in accepted:
            overdue = self._overdue_signal(record, current_time)
            if overdue:
                candidates.append(overdue)
            if (
                record.record_type == OperationalRecordType.DECISION
                and record.status == OperationalStatus.PROPOSED
            ):
                candidates.append(
                    self._candidate(
                        ProjectSignalType.UNRESOLVED_DECISION,
                        SignalSeverity.MEDIUM,
                        f"Decision remains unresolved: {record.title}",
                        "An unresolved decision can block dependent work and procurement.",
                        [record],
                        "Confirm the decision owner and required decision date.",
                    )
                )

        created: list[ProjectSignal] = []
        for candidate in candidates:
            if candidate.fingerprint in fingerprints:
                continue
            now_value = datetime.now(timezone.utc)
            signal = ProjectSignal(
                id=f"operator_signal:{uuid4().hex}",
                project_id=project_id,
                created_at=now_value,
                updated_at=now_value,
                **candidate.model_dump(),
            )
            created.append(await self.repository.save(signal))
            fingerprints.add(candidate.fingerprint)
        return created

    async def list_signals(
        self,
        project_id: str,
        status: ProjectSignalStatus | None = None,
    ) -> list[ProjectSignal]:
        return await self.repository.list_signals(project_id, status)

    async def update_status(
        self,
        project_id: str,
        signal_id: str,
        status: ProjectSignalStatus,
    ) -> ProjectSignal:
        signal = await self.repository.get(signal_id)
        if signal is None or signal.project_id != project_id:
            raise ValueError("signal is unavailable for this project")
        updated = signal.model_copy(
            update={"status": status, "updated_at": datetime.now(timezone.utc)}
        )
        return await self.repository.save(updated)

    def _signal_for_observation(
        self,
        observation: OperationalRecord,
        accepted: list[OperationalRecord],
    ) -> ProjectSignalCreate | None:
        category = str(observation.attributes.get("category") or "")
        if category == "request":
            return self._candidate(
                ProjectSignalType.MISSING_INFORMATION,
                SignalSeverity.MEDIUM,
                f"Information requested: {observation.title}",
                "The request remains unconfirmed in the accepted project state.",
                [observation],
                "Assign an owner and obtain the requested information.",
            )
        if category == "change":
            return self._candidate(
                ProjectSignalType.DOCUMENT_REVISION,
                SignalSeverity.MEDIUM,
                f"Potential project revision: {observation.title}",
                "A revision may supersede previously accepted project information.",
                [observation],
                "Review the revision and identify affected records before superseding them.",
            )
        if category in {"risk_statement", "dependency"}:
            return self._candidate(
                ProjectSignalType.DEPENDENCY_RISK,
                SignalSeverity.HIGH if category == "risk_statement" else SignalSeverity.MEDIUM,
                f"Project dependency or risk: {observation.title}",
                "The statement identifies a potential blocker or downstream impact.",
                [observation],
                "Confirm ownership, impact, and a mitigation or recovery action.",
            )
        if category not in {"commitment", "deadline"}:
            return None

        related = [record for record in accepted if self._related(observation, record)]
        if not related:
            return self._candidate(
                ProjectSignalType.NEW_COMMITMENT,
                SignalSeverity.MEDIUM,
                f"New commitment detected: {observation.title}",
                "The commitment is not represented in accepted project state.",
                [observation],
                "Confirm the responsible party and due date before accepting it.",
            )
        expected_date = observation.attributes.get("expected_date")
        for record in related:
            accepted_date = record.attributes.get("due_date") or record.attributes.get(
                "expected_date"
            )
            if expected_date and accepted_date and str(expected_date) != str(accepted_date):
                return self._candidate(
                    ProjectSignalType.CONFLICT,
                    SignalSeverity.HIGH,
                    f"Conflicting commitment date: {observation.title}",
                    "The new source states a date that differs from accepted project state.",
                    [observation, record],
                    "Request confirmation before changing the accepted date.",
                )
        return self._candidate(
            ProjectSignalType.CONFIRMATION,
            SignalSeverity.INFO,
            f"Existing commitment confirmed: {observation.title}",
            "The new source supports an existing accepted commitment.",
            [observation, related[0]],
            "No state change is required unless the supporting source should be attached.",
        )

    def _overdue_signal(
        self, record: OperationalRecord, now: datetime
    ) -> ProjectSignalCreate | None:
        if record.record_type not in {
            OperationalRecordType.COMMITMENT,
            OperationalRecordType.TASK,
        } or record.status != OperationalStatus.ACTIVE:
            return None
        raw_date = record.attributes.get("due_date") or record.attributes.get(
            "expected_date"
        )
        due_date = self._parse_datetime(raw_date)
        if due_date is None or due_date >= now:
            return None
        days_overdue = max((now - due_date).days, 0)
        severity = SignalSeverity.HIGH if days_overdue >= 7 else SignalSeverity.MEDIUM
        return self._candidate(
            ProjectSignalType.OVERDUE_ITEM,
            severity,
            f"Overdue item: {record.title}",
            f"The accepted due date passed {days_overdue} day(s) ago.",
            [record],
            "Confirm completion, obtain a revised date, or escalate the blocker.",
        )

    def _candidate(
        self,
        signal_type: ProjectSignalType,
        severity: SignalSeverity,
        summary: str,
        why_it_matters: str,
        records: list[OperationalRecord],
        recommended_response: str,
    ) -> ProjectSignalCreate:
        affected = sorted({record.id for record in records})
        evidence = sorted(
            {evidence_id for record in records for evidence_id in record.evidence_ids}
        )
        fingerprint = hashlib.sha256(
            f"{signal_type.value}|{'|'.join(affected)}|{summary.lower()}".encode()
        ).hexdigest()
        return ProjectSignalCreate(
            signal_type=signal_type,
            severity=severity,
            summary=summary,
            why_it_matters=why_it_matters,
            affected_entity_ids=affected,
            evidence_ids=evidence,
            confidence=min(record.confidence for record in records),
            recommended_response=recommended_response,
            fingerprint=fingerprint,
        )

    def _related(
        self, observation: OperationalRecord, record: OperationalRecord
    ) -> bool:
        if record.record_type not in {
            OperationalRecordType.COMMITMENT,
            OperationalRecordType.TASK,
            OperationalRecordType.REQUIREMENT,
        }:
            return False
        observation_tokens = self._tokens(observation.title)
        record_tokens = self._tokens(record.title)
        if not observation_tokens or not record_tokens:
            return False
        overlap = len(observation_tokens & record_tokens)
        return overlap / min(len(observation_tokens), len(record_tokens)) >= 0.5

    def _tokens(self, value: str) -> set[str]:
        return {
            token
            for token in "".join(
                character.lower() if character.isalnum() else " "
                for character in value
            ).split()
            if token not in self._stop_words and len(token) > 2
        }

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
