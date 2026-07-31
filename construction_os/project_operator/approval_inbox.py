"""Human-review projection for Project Operator signals and activity."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from construction_os.project_operator.event_ledger import (
    EventActorType,
    ProjectEventCreate,
    ProjectEventLedgerService,
    ProjectEventType,
)
from construction_os.project_operator.signal_detection import (
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
    SignalSeverity,
)


class InboxSection(StrEnum):
    WHAT_CHANGED = "what_changed"
    NEEDS_ATTENTION = "needs_attention"
    RECOMMENDED_ACTIONS = "recommended_actions"


class OperatorInboxItem(BaseModel):
    id: str
    section: InboxSection
    title: str
    severity: SignalSeverity
    why_it_matters: str
    recommended_action: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]
    affected_entity_ids: list[str]
    status: ProjectSignalStatus
    created_at: datetime


class OperatorActivityItem(BaseModel):
    id: str
    event_type: str
    entity_id: str
    reason: str
    actor_type: str
    actor_id: str
    timestamp: datetime


class OperatorApprovalInbox(BaseModel):
    project_id: str
    what_changed: list[OperatorInboxItem]
    needs_attention: list[OperatorInboxItem]
    recommended_actions: list[OperatorInboxItem]
    recent_activity: list[OperatorActivityItem]


class SignalCorrectionRequest(BaseModel):
    corrected_summary: str
    explanation: str
    actor_id: str

    @field_validator("corrected_summary", "explanation", "actor_id")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("correction fields cannot be empty")
        return normalized


class ApprovalInboxService:
    _change_types = {
        ProjectSignalType.NEW_COMMITMENT,
        ProjectSignalType.CONFIRMATION,
        ProjectSignalType.DOCUMENT_REVISION,
    }
    _attention_types = {
        ProjectSignalType.CONFLICT,
        ProjectSignalType.OVERDUE_ITEM,
        ProjectSignalType.DEPENDENCY_RISK,
        ProjectSignalType.MISSING_INFORMATION,
        ProjectSignalType.UNRESOLVED_DECISION,
    }

    def __init__(
        self,
        signals: ProjectSignalDetectionService,
        ledger: ProjectEventLedgerService,
    ) -> None:
        self.signals = signals
        self.ledger = ledger

    async def build(self, project_id: str) -> OperatorApprovalInbox:
        signals = await self.signals.list_signals(project_id)
        visible = [
            signal
            for signal in signals
            if signal.status
            not in {ProjectSignalStatus.DISMISSED, ProjectSignalStatus.RESOLVED}
        ]
        events = await self.ledger.list_events(project_id)
        changes = [
            self._item(signal, InboxSection.WHAT_CHANGED)
            for signal in visible
            if signal.signal_type in self._change_types
        ]
        attention = [
            self._item(signal, InboxSection.NEEDS_ATTENTION)
            for signal in visible
            if signal.signal_type in self._attention_types
        ]
        recommended = [
            self._item(signal, InboxSection.RECOMMENDED_ACTIONS)
            for signal in visible
            if signal.status
            in {ProjectSignalStatus.NEW, ProjectSignalStatus.REVIEWED}
        ]
        activity = [
            OperatorActivityItem(
                id=event.id,
                event_type=event.event_type.value,
                entity_id=event.entity_id,
                reason=event.reason,
                actor_type=event.actor_type.value,
                actor_id=event.actor_id,
                timestamp=event.timestamp,
            )
            for event in reversed(events[-20:])
        ]
        return OperatorApprovalInbox(
            project_id=project_id,
            what_changed=self._sort(changes),
            needs_attention=self._sort(attention),
            recommended_actions=self._sort(recommended),
            recent_activity=activity,
        )

    async def correct_signal(
        self,
        project_id: str,
        signal_id: str,
        request: SignalCorrectionRequest,
    ) -> ProjectSignal:
        signal = await self.signals.repository.get(signal_id)
        if signal is None or signal.project_id != project_id:
            raise ValueError("signal is unavailable for this project")
        await self.ledger.append(
            project_id,
            ProjectEventCreate(
                entity_type="project_signal",
                entity_id=signal.id,
                event_type=ProjectEventType.HUMAN_CORRECTION_RECEIVED,
                previous_state=signal.model_dump(mode="json"),
                new_state={
                    "corrected_summary": request.corrected_summary,
                    "status": ProjectSignalStatus.RESOLVED.value,
                },
                reason=request.explanation,
                actor_type=EventActorType.HUMAN,
                actor_id=request.actor_id,
                evidence_ids=signal.evidence_ids,
            ),
        )
        return await self.signals.update_status(
            project_id, signal_id, ProjectSignalStatus.RESOLVED
        )

    @staticmethod
    def _item(
        signal: ProjectSignal, section: InboxSection
    ) -> OperatorInboxItem:
        return OperatorInboxItem(
            id=signal.id,
            section=section,
            title=signal.summary,
            severity=signal.severity,
            why_it_matters=signal.why_it_matters,
            recommended_action=signal.recommended_response,
            confidence=signal.confidence,
            evidence_ids=signal.evidence_ids,
            affected_entity_ids=signal.affected_entity_ids,
            status=signal.status,
            created_at=signal.created_at,
        )

    @staticmethod
    def _sort(items: list[OperatorInboxItem]) -> list[OperatorInboxItem]:
        severity_order = {
            SignalSeverity.CRITICAL: 5,
            SignalSeverity.HIGH: 4,
            SignalSeverity.MEDIUM: 3,
            SignalSeverity.LOW: 2,
            SignalSeverity.INFO: 1,
        }
        return sorted(
            items,
            key=lambda item: (severity_order[item.severity], item.created_at),
            reverse=True,
        )
