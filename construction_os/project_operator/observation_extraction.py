"""Deterministic observation extraction with evidence and duplicate prevention."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from construction_os.project_operator.event_ledger import (
    EventActorType,
    ProjectEventCreate,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.operational_state import (
    EvidenceCreate,
    OperationalRecord,
    OperationalRecordCreate,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)


class ObservationCategory(StrEnum):
    DEADLINE = "deadline"
    COMMITMENT = "commitment"
    REQUEST = "request"
    DECISION = "decision"
    REQUIREMENT = "requirement"
    CHANGE = "change"
    DEPENDENCY = "dependency"
    RESPONSIBILITY = "responsibility"
    COST = "cost"
    RISK_STATEMENT = "risk_statement"
    COMPLETION_STATEMENT = "completion_statement"


class SourceObservationRequest(BaseModel):
    source_type: str
    content: str
    source_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source_location: str | None = None

    @field_validator("source_type", "content")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("source type and content cannot be empty")
        return normalized


class ExtractedObservation(BaseModel):
    category: ObservationCategory
    statement: str
    subject: str
    responsible_party: str | None = None
    expected_date: datetime | None = None
    explicit: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    quoted_text: str
    source_location: str
    fingerprint: str


class ObservationExtractor(Protocol):
    def extract(
        self,
        source_id: str,
        request: SourceObservationRequest,
    ) -> list[ExtractedObservation]: ...


class RuleBasedObservationExtractor:
    """A conservative baseline that only emits explicitly stated observations."""

    _category_rules: tuple[tuple[ObservationCategory, re.Pattern[str]], ...] = (
        (
            ObservationCategory.COMPLETION_STATEMENT,
            re.compile(r"\b(completed|finished|is done|has been installed)\b", re.I),
        ),
        (
            ObservationCategory.DECISION,
            re.compile(r"\b(approved|decided|selected|authorized)\b", re.I),
        ),
        (
            ObservationCategory.CHANGE,
            re.compile(r"\b(revised|changed|moved|now due|supersedes?)\b", re.I),
        ),
        (
            ObservationCategory.REQUEST,
            re.compile(r"\b(please|request(?:ed)?|confirm|provide|send us)\b", re.I),
        ),
        (
            ObservationCategory.REQUIREMENT,
            re.compile(r"\b(must|shall|required|needs? to)\b", re.I),
        ),
        (
            ObservationCategory.RISK_STATEMENT,
            re.compile(r"\b(risk|delay|concern|may affect|could impact|threat)\b", re.I),
        ),
        (
            ObservationCategory.COST,
            re.compile(r"(?:\$\s?\d|\b(cost|budget|price|allowance)\b)", re.I),
        ),
        (
            ObservationCategory.DEPENDENCY,
            re.compile(r"\b(depends? on|before|after|prerequisite|blocked by)\b", re.I),
        ),
        (
            ObservationCategory.RESPONSIBILITY,
            re.compile(r"\b(responsible for|assigned to|owner is)\b", re.I),
        ),
        (
            ObservationCategory.COMMITMENT,
            re.compile(r"\b(will|expects? to|committed to|should be ready)\b", re.I),
        ),
        (
            ObservationCategory.DEADLINE,
            re.compile(r"\b(due|deadline|no later than|by\s+[A-Z])\b", re.I),
        ),
    )

    _responsible_party = re.compile(
        r"^\s*([A-Z][A-Za-z0-9 .&'-]{1,60}?)\s+(?:will|must|shall|expects? to)\b"
    )

    def extract(
        self,
        source_id: str,
        request: SourceObservationRequest,
    ) -> list[ExtractedObservation]:
        observations: list[ExtractedObservation] = []
        for match in re.finditer(r"[^\n.!?]+[.!?]?", request.content):
            statement = match.group(0).strip()
            if len(statement) < 8:
                continue
            category = self._classify(statement)
            if category is None:
                continue
            fingerprint = hashlib.sha256(
                f"{source_id}|{category.value}|{statement.lower()}".encode()
            ).hexdigest()
            party_match = self._responsible_party.search(statement)
            subject = statement[:100].rstrip(" .")
            observations.append(
                ExtractedObservation(
                    category=category,
                    statement=statement,
                    subject=subject,
                    responsible_party=(
                        party_match.group(1).strip() if party_match else None
                    ),
                    expected_date=self._resolve_date(statement, request.source_date),
                    explicit=True,
                    confidence=0.9,
                    quoted_text=statement,
                    source_location=f"characters {match.start()}-{match.end()}",
                    fingerprint=fingerprint,
                )
            )
        return observations

    def _classify(self, statement: str) -> ObservationCategory | None:
        for category, pattern in self._category_rules:
            if pattern.search(statement):
                return category
        return None

    @staticmethod
    def _resolve_date(statement: str, source_date: datetime) -> datetime | None:
        normalized_source = (
            source_date
            if source_date.tzinfo
            else source_date.replace(tzinfo=timezone.utc)
        )
        relative = re.search(
            r"\b(?:in|within)\s+(?:about\s+)?(\d+|a|one)\s+(day|days|week|weeks)\b",
            statement,
            re.I,
        )
        if relative:
            raw_count = relative.group(1).lower()
            count = 1 if raw_count in {"a", "one"} else int(raw_count)
            days = count * (7 if relative.group(2).lower().startswith("week") else 1)
            return normalized_source + timedelta(days=days)

        iso_date = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", statement)
        if iso_date:
            return datetime(
                int(iso_date.group(1)),
                int(iso_date.group(2)),
                int(iso_date.group(3)),
                tzinfo=normalized_source.tzinfo,
            )
        return None


class ObservationExtractionService:
    def __init__(
        self,
        state_service: OperationalStateService,
        ledger_service: ProjectEventLedgerService,
        extractor: ObservationExtractor | None = None,
    ) -> None:
        self.state_service = state_service
        self.ledger_service = ledger_service
        self.extractor = extractor or RuleBasedObservationExtractor()

    async def extract_and_store(
        self,
        project_id: str,
        source_id: str,
        request: SourceObservationRequest,
    ) -> list[OperationalRecord]:
        extracted = self.extractor.extract(source_id, request)
        existing = await self.state_service.list_records(
            project_id, OperationalRecordType.OBSERVATION
        )
        fingerprints = {
            str(record.attributes.get("fingerprint"))
            for record in existing
            if record.attributes.get("fingerprint")
        }
        created: list[OperationalRecord] = []
        for observation in extracted:
            if observation.fingerprint in fingerprints:
                continue
            evidence = await self.state_service.create_evidence(
                project_id,
                EvidenceCreate(
                    source_id=source_id,
                    source_type=request.source_type,
                    source_location=(
                        f"{request.source_location}; {observation.source_location}"
                        if request.source_location
                        else observation.source_location
                    ),
                    quoted_text=observation.quoted_text,
                    retrieved_at=request.source_date,
                ),
            )
            record = await self.state_service.create_record(
                project_id,
                OperationalRecordCreate(
                    record_type=OperationalRecordType.OBSERVATION,
                    title=observation.subject,
                    description=observation.statement,
                    status=OperationalStatus.PROPOSED,
                    confidence=observation.confidence,
                    evidence_ids=[evidence.id],
                    source_type=request.source_type,
                    source_id=source_id,
                    attributes={
                        "category": observation.category.value,
                        "explicit": observation.explicit,
                        "responsible_party": observation.responsible_party,
                        "expected_date": (
                            observation.expected_date.isoformat()
                            if observation.expected_date
                            else None
                        ),
                        "fingerprint": observation.fingerprint,
                    },
                ),
            )
            await self.ledger_service.append(
                project_id,
                ProjectEventCreate(
                    entity_type="operational_record",
                    entity_id=record.id,
                    event_type=ProjectEventType.OBSERVATION_DETECTED,
                    new_state=record.model_dump(mode="json"),
                    reason="Structured observation extracted from an authorized source",
                    actor_type=EventActorType.SYSTEM,
                    actor_id="project-operator:observation-extractor",
                    evidence_ids=[evidence.id],
                ),
            )
            fingerprints.add(observation.fingerprint)
            created.append(record)
        return created
