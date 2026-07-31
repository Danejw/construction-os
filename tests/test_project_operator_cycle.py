import asyncio
from datetime import datetime, timezone

import pytest

from construction_os.project_operator.action_runtime import (
    ActionRuntimeService,
    InMemoryActionRepository,
)
from construction_os.project_operator.event_ledger import (
    InMemoryProjectEventRepository,
    ProjectEventLedgerService,
)
from construction_os.project_operator.models import (
    OperatorAutomationLevel,
    OperatorConfigUpdate,
    OperatorMode,
)
from construction_os.project_operator.observation_extraction import (
    ObservationExtractionService,
    SourceObservationRequest,
)
from construction_os.project_operator.operational_state import (
    InMemoryOperationalStateRepository,
    OperationalStateService,
)
from construction_os.project_operator.operator_cycle import (
    InMemoryOperatorRunRepository,
    OperatorCycleService,
    OperatorCycleSource,
    OperatorRunRequest,
    OperatorRunStatus,
    OperatorRunTrigger,
)
from construction_os.project_operator.repository import (
    InMemoryProjectOperatorRepository,
)
from construction_os.project_operator.service import ProjectOperatorService
from construction_os.project_operator.signal_detection import (
    InMemoryProjectSignalRepository,
    ProjectSignalDetectionService,
)


async def _cycle(
    level: OperatorAutomationLevel = OperatorAutomationLevel.RECOMMEND,
) -> OperatorCycleService:
    operator = ProjectOperatorService(InMemoryProjectOperatorRepository())
    await operator.update_config(
        "project:alpha",
        OperatorConfigUpdate(
            enabled=True,
            mode=OperatorMode.MANUAL,
            automation_level=level,
        ),
    )
    state = OperationalStateService(InMemoryOperationalStateRepository())
    ledger = ProjectEventLedgerService(InMemoryProjectEventRepository())
    extraction = ObservationExtractionService(state, ledger)
    signals = ProjectSignalDetectionService(
        state,
        InMemoryProjectSignalRepository(),
    )
    actions = ActionRuntimeService(
        InMemoryActionRepository(),
        operator,
        ledger,
    )
    return OperatorCycleService(
        InMemoryOperatorRunRepository(),
        operator,
        extraction,
        signals,
        actions,
    )


def _request() -> OperatorRunRequest:
    return OperatorRunRequest(
        trigger=OperatorRunTrigger.SOURCE_TRIGGERED,
        sources=[
            OperatorCycleSource(
                source_id="source:lead-time-email",
                source=SourceObservationRequest(
                    source_type="email",
                    content=(
                        "Please confirm the grease interceptor manufacturer and "
                        "delivery date."
                    ),
                    source_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
                ),
            )
        ],
    )


@pytest.mark.asyncio
async def test_cycle_runs_extraction_signals_and_action_generation() -> None:
    cycle = await _cycle()

    run = await cycle.run("project:alpha", _request())

    assert run.status == OperatorRunStatus.COMPLETED
    assert run.sources_processed == 1
    assert len(run.observation_ids) == 1
    assert len(run.signal_ids) == 1
    assert len(run.action_ids) == 1
    assert run.execution_ids == []
    assert run.errors == []


@pytest.mark.asyncio
async def test_cycle_rerun_is_duplicate_safe() -> None:
    cycle = await _cycle()

    first = await cycle.run("project:alpha", _request())
    second = await cycle.run("project:alpha", _request())

    assert len(first.observation_ids) == 1
    assert len(first.signal_ids) == 1
    assert len(first.action_ids) == 1
    assert second.observation_ids == []
    assert second.signal_ids == []
    assert second.action_ids == []
    assert second.status == OperatorRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_observe_only_cycle_never_proposes_actions() -> None:
    cycle = await _cycle(OperatorAutomationLevel.OBSERVE_ONLY)

    run = await cycle.run("project:alpha", _request())

    assert len(run.observation_ids) == 1
    assert len(run.signal_ids) == 1
    assert run.action_ids == []
    assert run.status == OperatorRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_execution_failure_is_recorded_without_corrupting_run() -> None:
    cycle = await _cycle(OperatorAutomationLevel.EXECUTE_APPROVED)
    request = _request().model_copy(
        update={
            "execute_approved_action_ids": ["operator_action:missing"],
        }
    )

    run = await cycle.run("project:alpha", request)

    assert run.status == OperatorRunStatus.PARTIAL
    assert len(run.observation_ids) == 1
    assert len(run.signal_ids) == 1
    assert len(run.action_ids) == 1
    assert any("operator_action:missing" in error for error in run.errors)


@pytest.mark.asyncio
async def test_daily_brief_only_surfaces_active_operational_items() -> None:
    cycle = await _cycle()
    await cycle.run("project:alpha", _request())

    brief = await cycle.build_daily_brief("project:alpha")

    assert len(brief.emerging_risks) == 1
    assert "Information requested" in brief.emerging_risks[0]
    assert len(brief.recommended_actions) == 1
    assert brief.executed_actions == []
    assert brief.failed_actions == []


class SlowExtractionService:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def extract_and_store(
        self,
        project_id: str,
        source_id: str,
        source: SourceObservationRequest,
    ) -> list[object]:
        del project_id, source_id, source
        self.started.set()
        await self.release.wait()
        return []


@pytest.mark.asyncio
async def test_overlapping_runs_for_same_project_are_rejected() -> None:
    cycle = await _cycle(OperatorAutomationLevel.OBSERVE_ONLY)
    slow = SlowExtractionService()
    cycle.extraction = slow  # type: ignore[assignment]

    first_task = asyncio.create_task(cycle.run("project:alpha", _request()))
    await slow.started.wait()

    with pytest.raises(ValueError, match="already active"):
        await cycle.run("project:alpha", _request())

    slow.release.set()
    first = await first_task
    assert first.status == OperatorRunStatus.COMPLETED
