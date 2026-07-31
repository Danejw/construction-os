"""Organization-level Project Operator aggregation and approval boundaries."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.operational_state import (
    OperationalRecord,
    OperationalRecordType,
    OperationalStateService,
    OperationalStatus,
)
from construction_os.project_operator.signal_detection import (
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
    SignalSeverity,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SharedPartyType(StrEnum):
    EMPLOYEE = "employee"
    SUBCONTRACTOR = "subcontractor"
    VENDOR = "vendor"
    CLIENT = "client"
    OTHER = "other"


class OrganizationInsightType(StrEnum):
    PROJECT_AT_RISK = "project_at_risk"
    COMMITMENT_DUE = "commitment_due"
    UNRESOLVED_DECISION = "unresolved_decision"
    RESOURCE_CONFLICT = "resource_conflict"
    REPEATED_PARTY_ISSUE = "repeated_party_issue"
    PROCUREMENT_OPPORTUNITY = "procurement_opportunity"
    DOCUMENT_CONTROL_PROBLEM = "document_control_problem"


class OrganizationActionType(StrEnum):
    REVIEW_COMPANY_RISK = "review_company_risk"
    RESOLVE_RESOURCE_CONFLICT = "resolve_resource_conflict"
    COORDINATE_PROCUREMENT = "coordinate_procurement"
    ESCALATE_REPEATED_PARTY_ISSUE = "escalate_repeated_party_issue"


class OrganizationActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class OrganizationCreate(BaseModel):
    name: str
    allowed_approval_roles: list[str] = Field(
        default_factory=lambda: ["organization_admin"]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("organization name cannot be empty")
        return normalized

    @field_validator("allowed_approval_roles")
    @classmethod
    def validate_roles(cls, values: list[str]) -> list[str]:
        normalized = sorted({str(value).strip() for value in values if str(value).strip()})
        if not normalized:
            raise ValueError("at least one organization approval role is required")
        return normalized


class Organization(OrganizationCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)


class OrganizationProjectAccessCreate(BaseModel):
    project_id: str
    can_view: bool = True
    can_operate: bool = False

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("project:"):
            raise ValueError("project_id must identify a project record")
        return normalized


class OrganizationProjectAccess(OrganizationProjectAccessCreate):
    id: str
    organization_id: str
    created_at: datetime = Field(default_factory=utc_now)


class SharedPartyCreate(BaseModel):
    name: str
    party_type: SharedPartyType
    email: str | None = None

    @field_validator("name")
    @classmethod
    def validate_party_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("party name cannot be empty")
        return normalized


class SharedParty(SharedPartyCreate):
    id: str
    organization_id: str
    normalized_key: str
    created_at: datetime = Field(default_factory=utc_now)


class ResourceAssignmentCreate(BaseModel):
    resource_key: str
    resource_name: str
    project_id: str
    starts_at: datetime
    ends_at: datetime

    @field_validator("resource_key", "resource_name")
    @classmethod
    def validate_resource_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("resource assignment fields cannot be empty")
        return normalized

    @field_validator("project_id")
    @classmethod
    def validate_assignment_project(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("project:"):
            raise ValueError("project_id must identify a project record")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> "ResourceAssignmentCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("resource assignment end must follow its start")
        return self


class ResourceAssignment(ResourceAssignmentCreate):
    id: str
    organization_id: str
    created_at: datetime = Field(default_factory=utc_now)


class OrganizationInsight(BaseModel):
    id: str
    insight_type: OrganizationInsightType
    severity: SignalSeverity
    summary: str
    why_it_matters: str
    project_ids: list[str]
    source_signal_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    recommended_response: str


class CrossProjectCommitment(BaseModel):
    project_id: str
    record_id: str
    title: str
    due_date: str | None
    responsible_party_id: str | None
    evidence_ids: list[str]


class OrganizationOverview(BaseModel):
    organization_id: str
    generated_at: datetime
    visible_project_ids: list[str]
    projects_at_risk: list[OrganizationInsight]
    commitments_due: list[CrossProjectCommitment]
    unresolved_decisions: list[OrganizationInsight]
    resource_conflicts: list[OrganizationInsight]
    repeated_party_issues: list[OrganizationInsight]
    procurement_opportunities: list[OrganizationInsight]
    document_control_problems: list[OrganizationInsight]


class OrganizationActionCreate(BaseModel):
    action_type: OrganizationActionType
    title: str
    reason: str
    project_ids: list[str] = Field(min_length=1)
    insight_id: str | None = None
    proposed_by: str = "organization-operator"

    @field_validator("title", "reason", "proposed_by")
    @classmethod
    def validate_action_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("organization action text cannot be empty")
        return normalized


class OrganizationAction(OrganizationActionCreate):
    id: str
    organization_id: str
    status: OrganizationActionStatus = OrganizationActionStatus.PROPOSED
    decided_by: str | None = None
    decided_role: str | None = None
    decision_reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OrganizationActionDecision(BaseModel):
    actor_id: str
    actor_role: str
    approved: bool
    reason: str | None = None

    @field_validator("actor_id", "actor_role")
    @classmethod
    def validate_decision_identity(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("organization action decision identity cannot be empty")
        return normalized


class OrganizationOperatorRepository(Protocol):
    async def save_organization(self, item: Organization) -> Organization: ...
    async def get_organization(self, item_id: str) -> Organization | None: ...
    async def save_access(
        self, item: OrganizationProjectAccess
    ) -> OrganizationProjectAccess: ...
    async def list_access(self, organization_id: str) -> list[OrganizationProjectAccess]: ...
    async def save_party(self, item: SharedParty) -> SharedParty: ...
    async def list_parties(self, organization_id: str) -> list[SharedParty]: ...
    async def save_assignment(self, item: ResourceAssignment) -> ResourceAssignment: ...
    async def list_assignments(self, organization_id: str) -> list[ResourceAssignment]: ...
    async def save_action(self, item: OrganizationAction) -> OrganizationAction: ...
    async def get_action(self, item_id: str) -> OrganizationAction | None: ...
    async def list_actions(self, organization_id: str) -> list[OrganizationAction]: ...


class InMemoryOrganizationOperatorRepository:
    def __init__(self) -> None:
        self._organizations: dict[str, Organization] = {}
        self._access: dict[str, OrganizationProjectAccess] = {}
        self._parties: dict[str, SharedParty] = {}
        self._assignments: dict[str, ResourceAssignment] = {}
        self._actions: dict[str, OrganizationAction] = {}
        self._lock = asyncio.Lock()

    async def save_organization(self, item: Organization) -> Organization:
        async with self._lock:
            self._organizations[item.id] = item.model_copy(deep=True)
            return item.model_copy(deep=True)

    async def get_organization(self, item_id: str) -> Organization | None:
        async with self._lock:
            item = self._organizations.get(item_id)
            return item.model_copy(deep=True) if item else None

    async def save_access(
        self, item: OrganizationProjectAccess
    ) -> OrganizationProjectAccess:
        async with self._lock:
            self._access[item.id] = item.model_copy(deep=True)
            return item.model_copy(deep=True)

    async def list_access(self, organization_id: str) -> list[OrganizationProjectAccess]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._access.values()
                if item.organization_id == organization_id
            ]

    async def save_party(self, item: SharedParty) -> SharedParty:
        async with self._lock:
            self._parties[item.id] = item.model_copy(deep=True)
            return item.model_copy(deep=True)

    async def list_parties(self, organization_id: str) -> list[SharedParty]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._parties.values()
                if item.organization_id == organization_id
            ]

    async def save_assignment(self, item: ResourceAssignment) -> ResourceAssignment:
        async with self._lock:
            self._assignments[item.id] = item.model_copy(deep=True)
            return item.model_copy(deep=True)

    async def list_assignments(self, organization_id: str) -> list[ResourceAssignment]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._assignments.values()
                if item.organization_id == organization_id
            ]

    async def save_action(self, item: OrganizationAction) -> OrganizationAction:
        async with self._lock:
            self._actions[item.id] = item.model_copy(deep=True)
            return item.model_copy(deep=True)

    async def get_action(self, item_id: str) -> OrganizationAction | None:
        async with self._lock:
            item = self._actions.get(item_id)
            return item.model_copy(deep=True) if item else None

    async def list_actions(self, organization_id: str) -> list[OrganizationAction]:
        async with self._lock:
            items = [
                item.model_copy(deep=True)
                for item in self._actions.values()
                if item.organization_id == organization_id
            ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)


class SurrealOrganizationOperatorRepository:
    async def _ensure_tables(self) -> None:
        await repo_query(
            "DEFINE TABLE IF NOT EXISTS operator_organization SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_org_project SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_org_party SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_org_assignment SCHEMALESS; "
            "DEFINE TABLE IF NOT EXISTS operator_org_action SCHEMALESS;"
        )

    async def _save(self, item: BaseModel, item_id: str) -> dict[str, object]:
        await self._ensure_tables()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(item_id),
                "data": item.model_dump(mode="json", exclude={"id"}),
            },
        )
        return result[0]

    async def save_organization(self, item: Organization) -> Organization:
        return Organization(id=item.id, **await self._save(item, item.id))

    async def get_organization(self, item_id: str) -> Organization | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;", {"id": ensure_record_id(item_id)}
        )
        return Organization(id=item_id, **result[0]) if result else None

    async def save_access(
        self, item: OrganizationProjectAccess
    ) -> OrganizationProjectAccess:
        return OrganizationProjectAccess(id=item.id, **await self._save(item, item.id))

    async def list_access(self, organization_id: str) -> list[OrganizationProjectAccess]:
        return [
            OrganizationProjectAccess(**item)
            for item in await self._list("operator_org_project", organization_id)
        ]

    async def save_party(self, item: SharedParty) -> SharedParty:
        return SharedParty(id=item.id, **await self._save(item, item.id))

    async def list_parties(self, organization_id: str) -> list[SharedParty]:
        return [
            SharedParty(**item)
            for item in await self._list("operator_org_party", organization_id)
        ]

    async def save_assignment(self, item: ResourceAssignment) -> ResourceAssignment:
        return ResourceAssignment(id=item.id, **await self._save(item, item.id))

    async def list_assignments(self, organization_id: str) -> list[ResourceAssignment]:
        return [
            ResourceAssignment(**item)
            for item in await self._list("operator_org_assignment", organization_id)
        ]

    async def save_action(self, item: OrganizationAction) -> OrganizationAction:
        return OrganizationAction(id=item.id, **await self._save(item, item.id))

    async def get_action(self, item_id: str) -> OrganizationAction | None:
        await self._ensure_tables()
        result = await repo_query(
            "SELECT * FROM $id;", {"id": ensure_record_id(item_id)}
        )
        return OrganizationAction(id=item_id, **result[0]) if result else None

    async def list_actions(self, organization_id: str) -> list[OrganizationAction]:
        return [
            OrganizationAction(**item)
            for item in await self._list(
                "operator_org_action", organization_id, "created_at DESC"
            )
        ]

    async def _list(
        self,
        table: str,
        organization_id: str,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        await self._ensure_tables()
        query = f"SELECT * FROM {table} WHERE organization_id = $organization_id"
        if order:
            query += f" ORDER BY {order}"
        return await repo_query(f"{query};", {"organization_id": organization_id})


class OrganizationOperatorService:
    """Aggregates authorized project state without modifying project records."""

    def __init__(
        self,
        repository: OrganizationOperatorRepository,
        state: OperationalStateService,
        signals: ProjectSignalDetectionService,
    ) -> None:
        self.repository = repository
        self.state = state
        self.signals = signals

    async def create_organization(self, body: OrganizationCreate) -> Organization:
        return await self.repository.save_organization(
            Organization(
                id=f"operator_organization:{uuid4().hex}",
                **body.model_dump(),
            )
        )

    async def add_project_access(
        self,
        organization_id: str,
        body: OrganizationProjectAccessCreate,
    ) -> OrganizationProjectAccess:
        await self._organization(organization_id)
        item_id = self._stable_id(
            "operator_org_project", organization_id, body.project_id
        )
        return await self.repository.save_access(
            OrganizationProjectAccess(
                id=item_id,
                organization_id=organization_id,
                **body.model_dump(),
            )
        )

    async def register_party(
        self,
        organization_id: str,
        body: SharedPartyCreate,
    ) -> SharedParty:
        await self._organization(organization_id)
        key = self._party_key(body)
        existing = await self.repository.list_parties(organization_id)
        for party in existing:
            if party.normalized_key == key:
                return party
        return await self.repository.save_party(
            SharedParty(
                id=self._stable_id("operator_org_party", organization_id, key),
                organization_id=organization_id,
                normalized_key=key,
                **body.model_dump(),
            )
        )

    async def assign_resource(
        self,
        organization_id: str,
        body: ResourceAssignmentCreate,
    ) -> ResourceAssignment:
        await self._require_project_access(organization_id, body.project_id)
        return await self.repository.save_assignment(
            ResourceAssignment(
                id=f"operator_org_assignment:{uuid4().hex}",
                organization_id=organization_id,
                **body.model_dump(),
            )
        )

    async def build_overview(self, organization_id: str) -> OrganizationOverview:
        await self._organization(organization_id)
        access = await self.repository.list_access(organization_id)
        visible_projects = sorted(
            {item.project_id for item in access if item.can_view}
        )
        project_signals: dict[str, list[ProjectSignal]] = {}
        project_records: dict[str, list[OperationalRecord]] = {}
        for project_id in visible_projects:
            project_signals[project_id] = [
                signal
                for signal in await self.signals.list_signals(project_id)
                if signal.status
                not in {ProjectSignalStatus.DISMISSED, ProjectSignalStatus.RESOLVED}
            ]
            project_records[project_id] = await self.state.list_records(project_id)

        return OrganizationOverview(
            organization_id=organization_id,
            generated_at=utc_now(),
            visible_project_ids=visible_projects,
            projects_at_risk=self._project_risks(project_signals),
            commitments_due=self._commitments(project_records),
            unresolved_decisions=self._unresolved_decisions(project_records),
            resource_conflicts=await self._resource_conflicts(
                organization_id, visible_projects
            ),
            repeated_party_issues=self._repeated_party_issues(project_records),
            procurement_opportunities=self._procurement_opportunities(project_records),
            document_control_problems=self._document_control(project_signals),
        )

    async def propose_action(
        self,
        organization_id: str,
        body: OrganizationActionCreate,
    ) -> OrganizationAction:
        await self._organization(organization_id)
        access = await self.repository.list_access(organization_id)
        operable = {item.project_id for item in access if item.can_operate}
        unauthorized = sorted(set(body.project_ids) - operable)
        if unauthorized:
            raise ValueError(
                f"organization cannot operate the requested projects: {unauthorized}"
            )
        return await self.repository.save_action(
            OrganizationAction(
                id=f"operator_org_action:{uuid4().hex}",
                organization_id=organization_id,
                **body.model_dump(),
            )
        )

    async def decide_action(
        self,
        organization_id: str,
        action_id: str,
        decision: OrganizationActionDecision,
    ) -> OrganizationAction:
        organization = await self._organization(organization_id)
        action = await self.repository.get_action(action_id)
        if action is None or action.organization_id != organization_id:
            raise ValueError("organization action is unavailable")
        if decision.actor_role not in organization.allowed_approval_roles:
            raise ValueError("role is not allowed by the organization approval policy")
        updated = action.model_copy(
            update={
                "status": (
                    OrganizationActionStatus.APPROVED
                    if decision.approved
                    else OrganizationActionStatus.REJECTED
                ),
                "decided_by": decision.actor_id,
                "decided_role": decision.actor_role,
                "decision_reason": decision.reason,
                "updated_at": utc_now(),
            }
        )
        return await self.repository.save_action(updated)

    async def list_actions(self, organization_id: str) -> list[OrganizationAction]:
        await self._organization(organization_id)
        return await self.repository.list_actions(organization_id)

    def _project_risks(
        self, project_signals: dict[str, list[ProjectSignal]]
    ) -> list[OrganizationInsight]:
        insights: list[OrganizationInsight] = []
        for project_id, signals in project_signals.items():
            severe = [
                signal
                for signal in signals
                if signal.severity in {SignalSeverity.HIGH, SignalSeverity.CRITICAL}
            ]
            if not severe:
                continue
            insights.append(
                self._insight(
                    OrganizationInsightType.PROJECT_AT_RISK,
                    max(severe, key=self._severity_rank).severity,
                    f"Project has {len(severe)} high-priority operational signal(s)",
                    "Multiple unresolved signals can threaten schedule, cost, or coordination.",
                    [project_id],
                    signals=severe,
                    response="Review the highest-severity signals and assign accountable owners.",
                )
            )
        return insights

    def _commitments(
        self, project_records: dict[str, list[OperationalRecord]]
    ) -> list[CrossProjectCommitment]:
        items: list[CrossProjectCommitment] = []
        for project_id, records in project_records.items():
            for record in records:
                if (
                    record.record_type == OperationalRecordType.COMMITMENT
                    and record.status == OperationalStatus.ACTIVE
                ):
                    due_date = record.attributes.get("due_date") or record.attributes.get(
                        "expected_date"
                    )
                    items.append(
                        CrossProjectCommitment(
                            project_id=project_id,
                            record_id=record.id,
                            title=record.title,
                            due_date=str(due_date) if due_date else None,
                            responsible_party_id=record.responsible_party_id,
                            evidence_ids=record.evidence_ids,
                        )
                    )
        return sorted(items, key=lambda item: item.due_date or "9999")

    def _unresolved_decisions(
        self, project_records: dict[str, list[OperationalRecord]]
    ) -> list[OrganizationInsight]:
        return [
            self._insight(
                OrganizationInsightType.UNRESOLVED_DECISION,
                SignalSeverity.MEDIUM,
                f"Unresolved decision: {record.title}",
                "The decision remains proposed and may block dependent project work.",
                [project_id],
                records=[record],
                response="Confirm the decision owner and deadline.",
            )
            for project_id, records in project_records.items()
            for record in records
            if record.record_type == OperationalRecordType.DECISION
            and record.status == OperationalStatus.PROPOSED
        ]

    async def _resource_conflicts(
        self,
        organization_id: str,
        visible_projects: list[str],
    ) -> list[OrganizationInsight]:
        assignments = [
            item
            for item in await self.repository.list_assignments(organization_id)
            if item.project_id in visible_projects
        ]
        insights: list[OrganizationInsight] = []
        for index, first in enumerate(assignments):
            for second in assignments[index + 1 :]:
                if (
                    first.resource_key == second.resource_key
                    and first.project_id != second.project_id
                    and first.starts_at < second.ends_at
                    and second.starts_at < first.ends_at
                ):
                    insights.append(
                        self._insight(
                            OrganizationInsightType.RESOURCE_CONFLICT,
                            SignalSeverity.HIGH,
                            f"Resource conflict: {first.resource_name}",
                            "The same resource is assigned to overlapping project windows.",
                            sorted({first.project_id, second.project_id}),
                            response="Confirm priority and revise one assignment before the overlap.",
                        )
                    )
        return insights

    def _repeated_party_issues(
        self, project_records: dict[str, list[OperationalRecord]]
    ) -> list[OrganizationInsight]:
        grouped: dict[str, list[tuple[str, OperationalRecord]]] = {}
        for project_id, records in project_records.items():
            for record in records:
                party_id = record.attributes.get("party_id")
                if record.record_type == OperationalRecordType.ISSUE and party_id:
                    grouped.setdefault(str(party_id), []).append((project_id, record))
        return [
            self._insight(
                OrganizationInsightType.REPEATED_PARTY_ISSUE,
                SignalSeverity.HIGH,
                f"Repeated issues associated with {party_id}",
                "The same party is linked to active issues on multiple projects.",
                sorted({project_id for project_id, _record in items}),
                records=[record for _project_id, record in items],
                response="Review the pattern and coordinate a company-level response.",
            )
            for party_id, items in grouped.items()
            if len({project_id for project_id, _record in items}) > 1
        ]

    def _procurement_opportunities(
        self, project_records: dict[str, list[OperationalRecord]]
    ) -> list[OrganizationInsight]:
        grouped: dict[str, list[tuple[str, OperationalRecord]]] = {}
        eligible = {
            OperationalRecordType.COMMITMENT,
            OperationalRecordType.REQUIREMENT,
            OperationalRecordType.TASK,
        }
        for project_id, records in project_records.items():
            for record in records:
                key = record.attributes.get("procurement_key")
                if record.record_type in eligible and key:
                    grouped.setdefault(str(key), []).append((project_id, record))
        return [
            self._insight(
                OrganizationInsightType.PROCUREMENT_OPPORTUNITY,
                SignalSeverity.LOW,
                f"Cross-project procurement opportunity: {key}",
                "Multiple projects require the same procurement category.",
                sorted({project_id for project_id, _record in items}),
                records=[record for _project_id, record in items],
                response="Compare timing and quantities for coordinated purchasing.",
            )
            for key, items in grouped.items()
            if len({project_id for project_id, _record in items}) > 1
        ]

    def _document_control(
        self, project_signals: dict[str, list[ProjectSignal]]
    ) -> list[OrganizationInsight]:
        insights: list[OrganizationInsight] = []
        for project_id, signals in project_signals.items():
            document_signals = [
                signal
                for signal in signals
                if signal.signal_type
                in {ProjectSignalType.CONFLICT, ProjectSignalType.DOCUMENT_REVISION}
            ]
            if document_signals:
                insights.append(
                    self._insight(
                        OrganizationInsightType.DOCUMENT_CONTROL_PROBLEM,
                        SignalSeverity.HIGH,
                        f"Document-control attention required on {project_id}",
                        "Revision or conflict signals require confirmation before state changes.",
                        [project_id],
                        signals=document_signals,
                        response="Review affected documents and confirm superseded information.",
                    )
                )
        return insights

    def _insight(
        self,
        insight_type: OrganizationInsightType,
        severity: SignalSeverity,
        summary: str,
        why_it_matters: str,
        project_ids: list[str],
        *,
        signals: list[ProjectSignal] | None = None,
        records: list[OperationalRecord] | None = None,
        response: str,
    ) -> OrganizationInsight:
        signal_items = signals or []
        record_items = records or []
        source_signal_ids = sorted({item.id for item in signal_items})
        source_record_ids = sorted({item.id for item in record_items})
        evidence_ids = sorted(
            {
                evidence_id
                for item in [*signal_items, *record_items]
                for evidence_id in item.evidence_ids
            }
        )
        insight_id = self._stable_id(
            "operator_org_insight",
            insight_type.value,
            *sorted(project_ids),
            *source_signal_ids,
            *source_record_ids,
        )
        return OrganizationInsight(
            id=insight_id,
            insight_type=insight_type,
            severity=severity,
            summary=summary,
            why_it_matters=why_it_matters,
            project_ids=project_ids,
            source_signal_ids=source_signal_ids,
            source_record_ids=source_record_ids,
            evidence_ids=evidence_ids,
            recommended_response=response,
        )

    async def _organization(self, organization_id: str) -> Organization:
        item = await self.repository.get_organization(organization_id)
        if item is None:
            raise ValueError("organization is unavailable")
        return item

    async def _require_project_access(
        self, organization_id: str, project_id: str
    ) -> OrganizationProjectAccess:
        await self._organization(organization_id)
        access = await self.repository.list_access(organization_id)
        for item in access:
            if item.project_id == project_id and item.can_view:
                return item
        raise ValueError("project is unavailable to this organization")

    @staticmethod
    def _party_key(body: SharedPartyCreate) -> str:
        email = str(body.email or "").strip().lower()
        name = " ".join(body.name.lower().split())
        return f"{body.party_type.value}|{email or name}"

    @staticmethod
    def _stable_id(prefix: str, *values: str) -> str:
        digest = hashlib.sha256("|".join(values).encode()).hexdigest()
        return f"{prefix}:{digest[:32]}"

    @staticmethod
    def _severity_rank(signal: ProjectSignal) -> int:
        return {
            SignalSeverity.INFO: 1,
            SignalSeverity.LOW: 2,
            SignalSeverity.MEDIUM: 3,
            SignalSeverity.HIGH: 4,
            SignalSeverity.CRITICAL: 5,
        }[signal.severity]
