"""Evidence-backed operational state for Construction OS projects."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from construction_os.database.repository import ensure_record_id, repo_query


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperationalRecordType(StrEnum):
    OBSERVATION = "observation"
    FACT = "fact"
    COMMITMENT = "commitment"
    REQUIREMENT = "requirement"
    DECISION = "decision"
    ISSUE = "issue"
    RISK = "risk"
    TASK = "task"


class OperationalStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class EvidenceCreate(BaseModel):
    source_id: str
    source_type: str
    source_location: str | None = None
    quoted_text: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    email_message_id: str | None = None
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)

    @field_validator("source_id", "source_type")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("evidence source fields cannot be empty")
        return normalized

    @model_validator(mode="after")
    def require_precise_location(self) -> "EvidenceCreate":
        if not any(
            [
                self.quoted_text,
                self.source_location,
                self.page_number,
                self.section,
                self.email_message_id,
                self.source_url,
            ]
        ):
            raise ValueError("evidence requires quoted text or a precise source location")
        return self


class EvidenceRecord(EvidenceCreate):
    id: str
    project_id: str
    created_at: datetime = Field(default_factory=utc_now)


class OperationalRecordCreate(BaseModel):
    record_type: OperationalRecordType
    title: str
    description: str
    status: OperationalStatus = OperationalStatus.PROPOSED
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    created_by: str = "system"
    source_type: str | None = None
    source_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    responsible_party_id: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)

    @field_validator("title", "description", "created_by")
    @classmethod
    def required_record_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("operational record text cannot be empty")
        return normalized

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if not normalized:
            raise ValueError("operational records require evidence")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_validity_window(self) -> "OperationalRecordCreate":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot precede valid_from")
        if self.record_type == OperationalRecordType.FACT and self.status == OperationalStatus.PROPOSED:
            raise ValueError("facts must be explicitly active, rejected, or superseded")
        return self


class OperationalRecord(OperationalRecordCreate):
    id: str
    project_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OperationalStateRepository(Protocol):
    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord: ...

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...

    async def save_record(self, record: OperationalRecord) -> OperationalRecord: ...

    async def get_record(self, record_id: str) -> OperationalRecord | None: ...

    async def list_records(
        self,
        project_id: str,
        record_type: OperationalRecordType | None = None,
        status: OperationalStatus | None = None,
    ) -> list[OperationalRecord]: ...


class InMemoryOperationalStateRepository:
    def __init__(self) -> None:
        self._evidence: dict[str, EvidenceRecord] = {}
        self._records: dict[str, OperationalRecord] = {}
        self._lock = asyncio.Lock()

    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        async with self._lock:
            self._evidence[evidence.id] = evidence.model_copy(deep=True)
            return evidence.model_copy(deep=True)

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        async with self._lock:
            item = self._evidence.get(evidence_id)
            return item.model_copy(deep=True) if item else None

    async def save_record(self, record: OperationalRecord) -> OperationalRecord:
        async with self._lock:
            self._records[record.id] = record.model_copy(deep=True)
            return record.model_copy(deep=True)

    async def get_record(self, record_id: str) -> OperationalRecord | None:
        async with self._lock:
            item = self._records.get(record_id)
            return item.model_copy(deep=True) if item else None

    async def list_records(
        self,
        project_id: str,
        record_type: OperationalRecordType | None = None,
        status: OperationalStatus | None = None,
    ) -> list[OperationalRecord]:
        async with self._lock:
            items = [
                item.model_copy(deep=True)
                for item in self._records.values()
                if item.project_id == project_id
            ]
        if record_type:
            items = [item for item in items if item.record_type == record_type]
        if status:
            items = [item for item in items if item.status == status]
        return sorted(items, key=lambda item: item.created_at, reverse=True)


class SurrealOperationalStateRepository:
    """SurrealDB persistence with schemaless tables and typed application models."""

    async def _ensure_tables(self) -> None:
        await repo_query(
            "DEFINE TABLE IF NOT EXISTS operator_evidence SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_record SCHEMALESS;"
        )

    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        await self._ensure_tables()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(evidence.id),
                "data": evidence.model_dump(mode="json", exclude={"id"}),
            },
        )
        return EvidenceRecord(id=evidence.id, **result[0])

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;", {"id": ensure_record_id(evidence_id)}
        )
        return EvidenceRecord(id=evidence_id, **result[0]) if result else None

    async def save_record(self, record: OperationalRecord) -> OperationalRecord:
        await self._ensure_tables()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(record.id),
                "data": record.model_dump(mode="json", exclude={"id"}),
            },
        )
        return OperationalRecord(id=record.id, **result[0])

    async def get_record(self, record_id: str) -> OperationalRecord | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;", {"id": ensure_record_id(record_id)}
        )
        return OperationalRecord(id=record_id, **result[0]) if result else None

    async def list_records(
        self,
        project_id: str,
        record_type: OperationalRecordType | None = None,
        status: OperationalStatus | None = None,
    ) -> list[OperationalRecord]:
        await self._ensure_tables()
        conditions = ["project_id = $project_id"]
        variables: dict[str, object] = {"project_id": project_id}
        if record_type:
            conditions.append("record_type = $record_type")
            variables["record_type"] = record_type.value
        if status:
            conditions.append("status = $status")
            variables["status"] = status.value
        result = await repo_query(
            f"SELECT * FROM operator_record WHERE {' AND '.join(conditions)} ORDER BY created_at DESC;",
            variables,
        )
        return [OperationalRecord(**item) for item in result]


class OperationalStateService:
    def __init__(self, repository: OperationalStateRepository) -> None:
        self.repository = repository

    async def create_evidence(
        self, project_id: str, body: EvidenceCreate
    ) -> EvidenceRecord:
        self._validate_project_id(project_id)
        evidence = EvidenceRecord(
            id=f"operator_evidence:{uuid4().hex}",
            project_id=project_id,
            **body.model_dump(),
        )
        return await self.repository.save_evidence(evidence)

    async def create_record(
        self, project_id: str, body: OperationalRecordCreate
    ) -> OperationalRecord:
        self._validate_project_id(project_id)
        for evidence_id in body.evidence_ids:
            evidence = await self.repository.get_evidence(evidence_id)
            if evidence is None or evidence.project_id != project_id:
                raise ValueError(f"evidence {evidence_id} is unavailable for this project")
        now = utc_now()
        record = OperationalRecord(
            id=f"operator_record:{uuid4().hex}",
            project_id=project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        return await self.repository.save_record(record)

    async def list_records(
        self,
        project_id: str,
        record_type: OperationalRecordType | None = None,
        status: OperationalStatus | None = None,
    ) -> list[OperationalRecord]:
        self._validate_project_id(project_id)
        return await self.repository.list_records(project_id, record_type, status)

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not str(project_id or "").startswith("project:"):
            raise ValueError("project_id must identify a project record")
