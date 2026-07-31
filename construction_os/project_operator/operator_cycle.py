"""End-to-end Project Operator cycle orchestration and daily briefs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.project_operator.action_runtime import (
    ActionExecutionRequest,
    ActionRuntimeService,
    ActionStatus,
    OperatorActionType,
    ProposedActionCreate,
)
from construction_os.project_operator.observation_extraction import (
    ObservationExtractionService,
    SourceObservationRequest,
)
from construction_os.project_operator.permissions import ProjectOperatorPermissions
from construction_os.project_operator.service import ProjectOperatorService
from construction_os.project_operator.signal_detection import (
    ProjectSignal,
    ProjectSignalDetectionService,
    ProjectSignalStatus,
    ProjectSignalType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperatorRunTrigger(StrEnum):
    SOURCE_TRIGGERED = "source_triggered"
    SCHEDULED_PROJECT_REVIEW = "scheduled_project_review"
    MANUAL_OPERATOR_RUN = "manual_operator_run"


class OperatorRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class OperatorCycleSource(BaseModel):
    source_id: str
    source: SourceObservationRequest

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("source_id cannot be empty")
        return normalized


class OperatorRunRequest(BaseModel):
    trigger: OperatorRunTrigger = OperatorRunTrigger.MANUAL_OPERATOR_RUN
    sources: list[OperatorCycleSource] = Field(default_factory=list)
    generate_actions: bool = True
    execute_approved_action_ids: list[str] = Field(default_factory=list)
    actor_id: str = "project-operator"
    actor_role: str = "project_manager"
    analysis_time: datetime | None = None


class OperatorRun(BaseModel):
    id: str
    project_id: str
    trigger: OperatorRunTrigger
    status: OperatorRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    sources_processed: int = 0
    observation_ids: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    execution_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DailyProjectBrief(BaseModel):
    project_id: str
    generated_at: datetime
    important_changes: list[str]
    new_commitments: list[str]
    overdue_items: list[str]
    unresolved_decisions: list[str]
    emerging_risks: list[str]
    recommended_actions: list[str]
    executed_actions: list[str]
    failed_actions: list[str]


class OperatorRunRepository(Protocol):
    async def save(self, run: OperatorRun) -> OperatorRun: ...

    async def get(self, run_id: str) -> OperatorRun | None: ...

    async def list_runs(self, project_id: str) -> list[OperatorRun]: ...


class InMemoryOperatorRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, OperatorRun] = {}
        self._lock = asyncio.Lock()

    async def save(self, run: OperatorRun) -> OperatorRun:
        async with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)
            return run.model_copy(deep=True)

    async def get(self, run_id: str) -> OperatorRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None

    async def list_runs(self, project_id: str) -> list[OperatorRun]:
        async with self._lock:
            runs = [
                run.model_copy(deep=True)
                for run in self._runs.values()
                if run.project_id == project_id
            ]
        return sorted(runs, key=lambda item: item.started_at, reverse=True)


class SurrealOperatorRunRepository:
    async def _ensure_table(self) -> None:
        await repo_query("DEFINE TABLE IF NOT EXISTS operator_run SCHEMALESS;")

    async def save(self, run: OperatorRun) -> OperatorRun:
        await self._ensure_table()
        result = await repo_query(
            "UPSERT $id CONTENT $data RETURN AFTER;",
            {
                "id": ensure_record_id(run.id),
                "data": run.model_dump(mode="json", exclude={"id"}),
            },
        )
        return OperatorRun(id=run.id, **result[0])

    async def get(self, run_id: str) -> OperatorRun | None:
        await self._ensure_table()
        result = await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id(run_id)},
        )
        return OperatorRun(id=run_id, **result[0]) if result else None

    async def list_runs(self, project_id: str) -> list[OperatorRun]:
        await self._ensure_table()
        result = await repo_query(
            "SELECT * FROM operator_run WHERE project_id = $project_id "
            "ORDER BY started_at DESC;",
            {"project_id": project_id},
        )
        return [OperatorRun(**item) for item in result]


class OperatorCycleService:
    """Runs extraction, signal detection, recommendations, and verification."""

    def __init__(
        self,
        repository: OperatorRunRepository,
        operator: ProjectOperatorService,
        extraction: ObservationExtractionService,
        signals: ProjectSignalDetectionService,
        actions: ActionRuntimeService,
    ) -> None:
        self.repository = repository
        self.operator = operator
        self.extraction = extraction
        self.signals = signals
        self.actions = actions
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def run(
        self,
        project_id: str,
        request: OperatorRunRequest,
    ) -> OperatorRun:
        config = await self.operator.get_config(project_id)
        if not ProjectOperatorPermissions.can_observe(config):
            raise ValueError(
                "project operator configuration does not allow observation"
            )
        lock = await self._get_lock(project_id)
        if lock.locked():
            raise ValueError("an operator run is already active for this project")

        async with lock:
            run = OperatorRun(
                id=f"operator_run:{uuid4().hex}",
                project_id=project_id,
                trigger=request.trigger,
                status=OperatorRunStatus.RUNNING,
                started_at=utc_now(),
            )
            await self.repository.save(run)
            try:
                await self._process_sources(run, request.sources)
                await self._detect_signals(run, request.analysis_time)
                if request.generate_actions and (
                    ProjectOperatorPermissions.can_recommend(config)
                ):
                    await self._generate_actions(run)
                await self._execute_approved(run, request)
            except Exception as exc:  # defensive run-level boundary
                run.errors.append(f"operator cycle failed: {exc}")

            run.completed_at = utc_now()
            has_output = bool(
                run.observation_ids
                or run.signal_ids
                or run.action_ids
                or run.execution_ids
            )
            if run.errors and not has_output:
                run.status = OperatorRunStatus.FAILED
            elif run.errors:
                run.status = OperatorRunStatus.PARTIAL
            else:
                run.status = OperatorRunStatus.COMPLETED
            return await self.repository.save(run)

    async def list_runs(self, project_id: str) -> list[OperatorRun]:
        return await self.repository.list_runs(project_id)

    async def build_daily_brief(self, project_id: str) -> DailyProjectBrief:
        signals = await self.signals.list_signals(project_id)
        actions = await self.actions.list_actions(project_id)
        unresolved = [
            signal
            for signal in signals
            if signal.status
            not in {ProjectSignalStatus.DISMISSED, ProjectSignalStatus.RESOLVED}
        ]
        return DailyProjectBrief(
            project_id=project_id,
            generated_at=utc_now(),
            important_changes=self._summaries(
                unresolved,
                {
                    ProjectSignalType.DOCUMENT_REVISION,
                    ProjectSignalType.CONFLICT,
                    ProjectSignalType.CONFIRMATION,
                },
            ),
            new_commitments=self._summaries(
                unresolved,
                {ProjectSignalType.NEW_COMMITMENT},
            ),
            overdue_items=self._summaries(
                unresolved,
                {ProjectSignalType.OVERDUE_ITEM},
            ),
            unresolved_decisions=self._summaries(
                unresolved,
                {ProjectSignalType.UNRESOLVED_DECISION},
            ),
            emerging_risks=self._summaries(
                unresolved,
                {
                    ProjectSignalType.DEPENDENCY_RISK,
                    ProjectSignalType.MISSING_INFORMATION,
                },
            ),
            recommended_actions=[
                action.title
                for action in actions
                if action.status in {ActionStatus.PROPOSED, ActionStatus.APPROVED}
            ],
            executed_actions=[
                action.title
                for action in actions
                if action.status == ActionStatus.EXECUTED
            ],
            failed_actions=[
                action.title
                for action in actions
                if action.status == ActionStatus.FAILED
            ],
        )

    async def _process_sources(
        self,
        run: OperatorRun,
        sources: list[OperatorCycleSource],
    ) -> None:
        for item in sources:
            try:
                records = await self.extraction.extract_and_store(
                    run.project_id,
                    item.source_id,
                    item.source,
                )
                run.sources_processed += 1
                run.observation_ids.extend(record.id for record in records)
            except Exception as exc:
                run.errors.append(f"source {item.source_id}: {exc}")
        await self.repository.save(run)

    async def _detect_signals(
        self,
        run: OperatorRun,
        analysis_time: datetime | None,
    ) -> None:
        try:
            signals = await self.signals.detect(
                run.project_id,
                now=analysis_time,
            )
            run.signal_ids.extend(signal.id for signal in signals)
        except Exception as exc:
            run.errors.append(f"signal detection: {exc}")
        await self.repository.save(run)

    async def _generate_actions(self, run: OperatorRun) -> None:
        for signal_id in run.signal_ids:
            signal = await self.signals.repository.get(signal_id)
            if signal is None:
                run.errors.append(f"signal {signal_id}: unavailable")
                continue
            proposal = self._action_for_signal(signal)
            if proposal is None:
                continue
            try:
                action = await self.actions.propose(run.project_id, proposal)
                run.action_ids.append(action.id)
                await self.signals.update_status(
                    run.project_id,
                    signal.id,
                    ProjectSignalStatus.CONVERTED_TO_ACTION,
                )
            except Exception as exc:
                run.errors.append(f"action for signal {signal.id}: {exc}")
        await self.repository.save(run)

    async def _execute_approved(
        self,
        run: OperatorRun,
        request: OperatorRunRequest,
    ) -> None:
        for action_id in request.execute_approved_action_ids:
            try:
                execution = await self.actions.execute(
                    run.project_id,
                    action_id,
                    ActionExecutionRequest(
                        actor_id=request.actor_id,
                        actor_role=request.actor_role,
                        idempotency_key=f"{run.id}:{action_id}",
                    ),
                )
                run.execution_ids.append(execution.id)
            except Exception as exc:
                run.errors.append(f"execution {action_id}: {exc}")
        await self.repository.save(run)

    @staticmethod
    def _action_for_signal(
        signal: ProjectSignal,
    ) -> ProposedActionCreate | None:
        common = {
            "title": signal.summary,
            "reason": signal.why_it_matters,
            "evidence_ids": signal.evidence_ids,
            "signal_id": signal.id,
        }
        if signal.signal_type in {
            ProjectSignalType.CONFLICT,
            ProjectSignalType.DOCUMENT_REVISION,
        }:
            return ProposedActionCreate(
                action_type=OperatorActionType.GENERATE_RFI_DRAFT,
                inputs={
                    "subject": signal.summary,
                    "question": signal.recommended_response,
                    "background": signal.why_it_matters,
                },
                **common,
            )
        if signal.signal_type == ProjectSignalType.MISSING_INFORMATION:
            return ProposedActionCreate(
                action_type=OperatorActionType.REQUEST_INFORMATION,
                inputs={
                    "recipient": "project-team",
                    "request": signal.recommended_response,
                },
                **common,
            )
        if signal.signal_type in {
            ProjectSignalType.OVERDUE_ITEM,
            ProjectSignalType.DEPENDENCY_RISK,
            ProjectSignalType.UNRESOLVED_DECISION,
            ProjectSignalType.NEW_COMMITMENT,
        }:
            return ProposedActionCreate(
                action_type=OperatorActionType.CREATE_INTERNAL_TASK,
                inputs={
                    "title": signal.summary,
                    "description": signal.recommended_response,
                },
                **common,
            )
        return None

    async def _get_lock(self, project_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            return self._locks.setdefault(project_id, asyncio.Lock())

    @staticmethod
    def _summaries(
        signals: list[ProjectSignal],
        signal_types: set[ProjectSignalType],
    ) -> list[str]:
        return [
            signal.summary
            for signal in signals
            if signal.signal_type in signal_types
        ]
