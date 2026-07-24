"""Focused tests for temporal, fact-level project memory behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from construction_os.services.project_memory import (
    ProjectMemoryDecision,
    ProjectMemoryFact,
    ProjectMemoryOperation,
    ProjectMemorySnapshot,
    apply_project_memory_operations,
    consolidate_project_memory,
    extract_evidence_ids,
    inject_project_memory,
    normalize_server_timestamp,
    project_memory_record_id,
    render_project_memory_content,
    schedule_project_memory_consolidation,
    should_consolidate_chat,
)

EVENT_AT = "2026-07-21T20:00:00+00:00"


def _fact(
    *,
    fact_id: str = "memory_fact:budget-old",
    category: str = "requirement",
    subject: str = "Budget ceiling",
    value: str = "$180,000",
    valid_from: str = "2026-07-20T10:00:00+00:00",
    evidence_ids: list[str] | None = None,
) -> ProjectMemoryFact:
    return ProjectMemoryFact(
        fact_id=fact_id,
        category=category,
        subject=subject,
        value=value,
        valid_from=valid_from,
        recorded_at=valid_from,
        updated_at=valid_from,
        evidence_ids=evidence_ids or ["source:spec1"],
        last_operation="merge",
    )


def _snapshot() -> ProjectMemorySnapshot:
    fact = _fact(
        fact_id="memory_fact:status",
        category="status",
        subject="Estimating",
        value="Estimating is active.",
    )
    return ProjectMemorySnapshot(
        project_id="project:abc",
        facts=[fact],
        content=render_project_memory_content([fact]),
        evidence_ids=["source:spec1"],
        revision=2,
        updated_at="2026-07-21T10:00:00+00:00",
    )


def test_project_memory_record_id_is_stable_and_project_scoped():
    first = project_memory_record_id("project:abc")
    second = project_memory_record_id("project:abc")
    other = project_memory_record_id("project:def")

    assert first == second
    assert first.startswith("project_memory:")
    assert first != other
    with pytest.raises(ValueError):
        project_memory_record_id("source:abc")


def test_extract_evidence_ids_deduplicates_in_order():
    text = "source:a note:b source:a and source:c"
    assert extract_evidence_ids(text) == ["source:a", "note:b", "source:c"]


def test_trivial_chat_is_not_scheduled():
    assert not should_consolidate_chat("Thanks!", "You are welcome.")
    assert should_consolidate_chat(
        "Move the bid deadline to August 8.",
        "The current bid deadline is now August 8.",
    )


def test_server_timestamp_validation_rejects_ai_style_invalid_dates():
    assert normalize_server_timestamp("2026-07-21T10:00:00Z").endswith("+00:00")
    with pytest.raises(ValueError):
        normalize_server_timestamp("July 42, sometime")
    with pytest.raises(ValueError):
        normalize_server_timestamp("2026-07-21T10:00:00")


def test_fact_requires_valid_timezone_aware_temporal_window():
    with pytest.raises(ValueError):
        _fact(valid_from="2026-07-21T10:00:00")
    with pytest.raises(ValueError):
        ProjectMemoryFact(
            fact_id="memory_fact:bad-window",
            category="decision",
            subject="Framing",
            value="Wood",
            status="superseded",
            valid_from="2026-07-22T10:00:00+00:00",
            valid_to="2026-07-21T10:00:00+00:00",
            recorded_at="2026-07-21T10:00:00+00:00",
            updated_at="2026-07-21T10:00:00+00:00",
            last_operation="supersede",
        )


@pytest.mark.asyncio
async def test_inject_project_memory_includes_temporal_active_state():
    payload = [
        SystemMessage(content="Existing grounded prompt"),
        HumanMessage(content="What is next?"),
    ]
    with patch(
        "construction_os.services.project_memory.get_project_memory",
        new_callable=AsyncMock,
        return_value=_snapshot(),
    ):
        result = await inject_project_memory(payload, project_id="project:abc")

    assert len(result) == 2
    assert "Existing grounded prompt" in result[0].content
    assert "CURRENT PROJECT STATE" in result[0].content
    assert "Estimating is active" in result[0].content
    assert "valid from 2026-07-20T10:00:00+00:00" in result[0].content
    assert payload[0].content == "Existing grounded prompt"


def test_merge_adds_new_fact_with_server_owned_timestamp():
    operations = [
        ProjectMemoryOperation(
            operation="merge",
            category="deadline",
            subject="Bid deadline",
            value="August 8, 2026",
            evidence_ids=["source:addendum", "source:not-available"],
        )
    ]

    facts, changed = apply_project_memory_operations(
        project_id="project:abc",
        previous_facts=[],
        operations=operations,
        requested_evidence_ids=["source:addendum"],
        event_at=EVENT_AT,
    )

    assert changed is True
    assert len(facts) == 1
    assert facts[0].status == "active"
    assert facts[0].valid_from == EVENT_AT
    assert facts[0].valid_to is None
    assert facts[0].evidence_ids == ["source:addendum"]


def test_merge_deduplicates_identical_active_fact():
    existing = _fact(evidence_ids=["source:spec1"])
    operations = [
        ProjectMemoryOperation(
            operation="merge",
            category="requirement",
            subject="Budget ceiling",
            value="$180,000",
            evidence_ids=["note:budget"],
        )
    ]

    facts, changed = apply_project_memory_operations(
        project_id="project:abc",
        previous_facts=[existing],
        operations=operations,
        requested_evidence_ids=["note:budget"],
        event_at=EVENT_AT,
    )

    assert changed is True
    assert len(facts) == 1
    assert facts[0].evidence_ids == ["source:spec1", "note:budget"]


def test_supersede_closes_old_fact_and_creates_temporal_replacement():
    existing = _fact()
    operations = [
        ProjectMemoryOperation(
            operation="supersede",
            target_fact_id=existing.fact_id,
            category="requirement",
            subject="Budget ceiling",
            value="$210,000",
            evidence_ids=["note:approved-budget"],
        )
    ]

    facts, changed = apply_project_memory_operations(
        project_id="project:abc",
        previous_facts=[existing],
        operations=operations,
        requested_evidence_ids=["note:approved-budget"],
        event_at=EVENT_AT,
    )

    assert changed is True
    assert len(facts) == 2
    old, new = facts
    assert old.status == "superseded"
    assert old.valid_to == EVENT_AT
    assert new.status == "active"
    assert new.valid_from == EVENT_AT
    assert new.supersedes_fact_id == old.fact_id
    assert new.value == "$210,000"


def test_delete_preserves_tombstone_for_temporal_reasoning():
    existing = _fact()
    operations = [
        ProjectMemoryOperation(
            operation="delete",
            target_fact_id=existing.fact_id,
            evidence_ids=["note:correction"],
        )
    ]

    facts, changed = apply_project_memory_operations(
        project_id="project:abc",
        previous_facts=[existing],
        operations=operations,
        requested_evidence_ids=["note:correction"],
        event_at=EVENT_AT,
    )

    assert changed is True
    assert len(facts) == 1
    assert facts[0].status == "deleted"
    assert facts[0].valid_to == EVENT_AT
    assert "note:correction" in facts[0].evidence_ids
    rendered = render_project_memory_content(facts)
    assert "Recent superseded or deleted facts" in rendered


@pytest.mark.asyncio
async def test_consolidation_applies_operations_and_increments_revision():
    decision = ProjectMemoryDecision(
        action="apply",
        operations=[
            ProjectMemoryOperation(
                operation="merge",
                category="deadline",
                subject="Bid deadline",
                value="August 8, 2026",
                evidence_ids=["source:addendum"],
            )
        ],
    )

    saved = ProjectMemorySnapshot(
        project_id="project:abc",
        facts=[],
        revision=1,
    )

    with (
        patch(
            "construction_os.services.project_memory.get_project_memory",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "construction_os.services.project_memory._load_evidence",
            new_callable=AsyncMock,
            return_value="Addendum evidence",
        ),
        patch(
            "construction_os.services.project_memory.invoke_structured",
            new_callable=AsyncMock,
            return_value=decision,
        ),
        patch(
            "construction_os.services.project_memory.save_project_memory",
            new_callable=AsyncMock,
            return_value=saved,
        ) as save_memory,
    ):
        snapshot, updated = await consolidate_project_memory(
            project_id="project:abc",
            reason="source_updated",
            candidate_text="The deadline moved.",
            evidence_ids=["source:addendum"],
            event_at=EVENT_AT,
        )

    assert updated is True
    assert snapshot == saved
    save_memory.assert_awaited_once()
    kwargs = save_memory.await_args.kwargs
    assert kwargs["revision"] == 1
    assert kwargs["facts"][0].valid_from == EVENT_AT


@pytest.mark.asyncio
async def test_consolidation_noop_preserves_previous_memory():
    previous = _snapshot()
    decision = ProjectMemoryDecision(action="noop")

    with (
        patch(
            "construction_os.services.project_memory.get_project_memory",
            new_callable=AsyncMock,
            return_value=previous,
        ),
        patch(
            "construction_os.services.project_memory._load_evidence",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "construction_os.services.project_memory.invoke_structured",
            new_callable=AsyncMock,
            return_value=decision,
        ),
        patch(
            "construction_os.services.project_memory.save_project_memory",
            new_callable=AsyncMock,
        ) as save_memory,
    ):
        snapshot, updated = await consolidate_project_memory(
            project_id="project:abc",
            reason="project_chat_completed",
            candidate_text="No durable change.",
            event_at=EVENT_AT,
        )

    assert updated is False
    assert snapshot == previous
    save_memory.assert_not_awaited()


def test_scheduler_persists_server_generated_event_timestamp():
    with patch(
        "construction_os.services.project_memory.submit_command",
        return_value="command:123",
    ) as submit:
        result = schedule_project_memory_consolidation(
            project_id="project:abc",
            reason="project_chat_completed",
            candidate_text="Budget changed.",
        )

    assert result == "command:123"
    payload = submit.call_args.args[2]
    assert normalize_server_timestamp(payload["event_at"]) == payload["event_at"]
