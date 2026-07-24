"""API and service tests for persistent per-session chat queues."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from importlib import import_module
from importlib.util import find_spec
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from surrealdb import RecordID

from api.models import (
    ChatQueueItemEnqueueRequest,
    ChatQueueItemUpdateRequest,
    ChatQueueReorderRequest,
)
from construction_os.domain.chat_queue import (
    ChatQueue,
    ChatQueueItem,
    ChatQueueMutationError,
    ChatQueueRevisionConflict,
)


def _service_module():
    """Load Task 2's service only after asserting that it exists."""
    spec = find_spec("api.chat_queue_service")
    assert spec is not None, "api.chat_queue_service has not been implemented"
    return import_module("api.chat_queue_service")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _queue(**overrides) -> ChatQueue:
    values = {
        "id": "chat_queue:queue-a",
        "chat_session": "chat_session:session-a",
        "status": "active",
        "revision": 1,
        "next_position": 10,
        "runner_state": "idle",
        "runner_command_id": None,
        "scheduling_token": None,
        "scheduling_expires_at": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "created": _now(),
        "updated": _now(),
    }
    values.update(overrides)
    return ChatQueue(**values)


def _item(**overrides) -> ChatQueueItem:
    values = {
        "id": "chat_queue_item:item-a",
        "queue_id": "chat_queue:queue-a",
        "chat_session": "chat_session:session-a",
        "client_request_id": "request-a",
        "run_id": "run-a",
        "position": 10,
        "status": "pending",
        "visible": True,
        "prompt": "Summarize the project",
        "loop_count": 1,
        "current_loop": 0,
        "iteration_token": None,
        "execution_snapshot": {
            "model_id": "model:gpt",
            "skill_ids": [],
            "tool_ids": [],
            "html_template_id": None,
            "artifact_id": None,
            "context_config": {},
            "forwarded_props": {},
        },
        "runner_command_id": None,
        "runner_state": "idle",
        "stream_revision": 0,
        "stream_content": "",
        "stream_progress": None,
        "stream_activity": None,
        "error_type": None,
        "error_message": None,
        "error_details": None,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "created": _now(),
        "updated": _now(),
    }
    values.update(overrides)
    return ChatQueueItem(**values)


def _session(*, guest_key=None, **overrides):
    values = {
        "id": "chat_session:session-a",
        "guest_key": guest_key,
        "title": "Session",
        "model_override": None,
        "skill_ids": [],
        "collection_ids": [],
        "html_template_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(
        **values,
    )


class FakeRepository:
    """Small stateful repository double preserving queue mutation semantics."""

    queue = _queue()
    items = {"chat_queue_item:item-a": _item()}
    enqueue_calls = 0
    submit_reservations = 0
    cleanup_calls = 0
    conflict: Exception | None = None

    @classmethod
    def reset(cls, *, queue=None, items=None):
        """Reset repository state between tests."""
        cls.queue = queue or _queue()
        cls.items = items if items is not None else {"chat_queue_item:item-a": _item()}
        cls.enqueue_calls = 0
        cls.submit_reservations = 0
        cls.cleanup_calls = 0
        cls.conflict = None

    @classmethod
    async def get_or_create(cls, chat_session_id):
        cls.queue.chat_session = chat_session_id
        return cls.queue

    @classmethod
    async def get_for_session(cls, chat_session_id):
        if cls.queue.chat_session != chat_session_id:
            return None
        return cls.queue

    @classmethod
    async def list_visible_items(cls, queue_id):
        return sorted(
            [
                item
                for item in cls.items.values()
                if item.queue_id == queue_id and item.visible
            ],
            key=lambda item: item.position,
        )

    @classmethod
    async def get_current_item(cls, queue_id):
        return next(
            (
                item
                for item in cls.items.values()
                if item.queue_id == queue_id and item.status == "running"
            ),
            None,
        )

    @classmethod
    async def get_item_for_session(cls, item_id, *, queue_id, chat_session_id):
        item = cls.items.get(item_id)
        if (
            item is None
            or item.queue_id != queue_id
            or item.chat_session != chat_session_id
        ):
            return None
        return item

    @classmethod
    async def enqueue(cls, **kwargs):
        cls.enqueue_calls += 1
        existing = next(
            (
                item
                for item in cls.items.values()
                if item.client_request_id == kwargs["client_request_id"]
                and item.chat_session == kwargs["chat_session_id"]
            ),
            None,
        )
        if existing:
            return existing
        item = _item(
            id="chat_queue_item:item-new",
            chat_session=kwargs["chat_session_id"],
            client_request_id=kwargs["client_request_id"],
            position=cls.queue.next_position,
            prompt=kwargs["prompt"],
            loop_count=kwargs["loop_count"],
            execution_snapshot=kwargs["execution_snapshot"],
        )
        cls.queue.next_position += 10
        cls.queue.revision += 1
        item.stream_revision = cls.queue.revision
        cls.items[item.id] = item
        return item

    @classmethod
    async def set_runner_command(cls, *, queue_id, chat_session_id, command_id):
        if (
            cls.queue.id != queue_id
            or cls.queue.chat_session != chat_session_id
            or cls.queue.status != "active"
            or cls.queue.runner_state != "idle"
            or cls.queue.runner_command_id is not None
        ):
            raise ChatQueueMutationError("Queue runner is already scheduled or active")
        cls.submit_reservations += 1
        cls.queue.runner_state = "scheduled"
        cls.queue.runner_command_id = command_id
        return cls.queue

    @classmethod
    async def reserve_runner(
        cls,
        *,
        queue_id,
        chat_session_id,
        scheduling_token,
        ttl_seconds,
    ):
        now = datetime.now(timezone.utc)
        fresh = (
            cls.queue.runner_state == "scheduled"
            and cls.queue.scheduling_expires_at is not None
            and cls.queue.scheduling_expires_at > now
        )
        fresh_lease = (
            cls.queue.runner_state == "running"
            and cls.queue.lease_expires_at is not None
            and cls.queue.lease_expires_at > now
        )
        if (
            cls.queue.id != queue_id
            or cls.queue.chat_session != chat_session_id
            or cls.queue.status != "active"
            or fresh
            or fresh_lease
        ):
            raise ChatQueueMutationError("Queue runner is already scheduled or active")
        cls.submit_reservations += 1
        cls.queue.runner_state = "scheduled"
        cls.queue.runner_command_id = None
        cls.queue.scheduling_token = scheduling_token
        cls.queue.scheduling_expires_at = now + timedelta(seconds=ttl_seconds)
        cls.queue.lease_owner = None
        cls.queue.lease_expires_at = None
        cls.queue.revision += 1
        return cls.queue

    @classmethod
    async def replace_runner_command(
        cls,
        *,
        queue_id,
        chat_session_id,
        expected_command_id,
        command_id,
    ):
        if cls.queue.runner_command_id != expected_command_id:
            return None
        cls.queue.runner_command_id = command_id
        return cls.queue

    @classmethod
    async def confirm_runner_command(
        cls,
        *,
        queue_id,
        chat_session_id,
        scheduling_token,
        command_id,
    ):
        if (
            cls.queue.scheduling_token == scheduling_token
            and cls.queue.runner_state in {"scheduled", "running"}
        ):
            if cls.queue.runner_command_id is None:
                cls.queue.runner_command_id = command_id
                cls.queue.revision += 1
                return cls.queue
            if cls.queue.runner_command_id == command_id:
                return cls.queue
            return None
        if (
            cls.queue.runner_state == "idle"
            and cls.queue.runner_command_id is None
            and cls.queue.scheduling_token is None
            and cls.queue.lease_owner is None
        ):
            return cls.queue
        return None

    @classmethod
    async def reset_runner_command(
        cls, *, queue_id, chat_session_id, expected_command_id
    ):
        if cls.queue.runner_command_id != expected_command_id:
            return None
        cls.queue.runner_state = "idle"
        cls.queue.runner_command_id = None
        return cls.queue

    @classmethod
    async def reset_runner_reservation(
        cls, *, queue_id, chat_session_id, scheduling_token
    ):
        if cls.queue.scheduling_token != scheduling_token:
            return None
        cls.queue.runner_state = "idle"
        cls.queue.runner_command_id = None
        cls.queue.scheduling_token = None
        cls.queue.scheduling_expires_at = None
        cls.queue.revision += 1
        return cls.queue

    @classmethod
    async def clear_unleased_schedule(cls, *, queue_id, chat_session_id):
        now = datetime.now(timezone.utc)
        leased = (
            cls.queue.lease_owner is not None
            and cls.queue.lease_expires_at is not None
            and cls.queue.lease_expires_at > now
        )
        if (
            cls.queue.id != queue_id
            or cls.queue.chat_session != chat_session_id
            or cls.queue.status != "active"
            or cls.queue.runner_state != "scheduled"
            or leased
        ):
            return None
        cls.queue.runner_state = "idle"
        cls.queue.runner_command_id = None
        cls.queue.scheduling_token = None
        cls.queue.scheduling_expires_at = None
        cls.queue.revision += 1
        return cls.queue

    @classmethod
    async def pause(cls, queue_id):
        cls.queue.status = "paused"
        cls.queue.revision += 1
        return cls.queue

    @classmethod
    async def resume(cls, queue_id):
        cls.queue.status = "active"
        cls.queue.revision += 1
        return cls.queue

    @classmethod
    async def update_item(cls, item_id, **kwargs):
        if cls.conflict:
            raise cls.conflict
        item = cls.items[item_id]
        if item.status not in {"pending", "failed"}:
            raise ChatQueueMutationError("Item is immutable")
        if kwargs["prompt"] is not None:
            item.prompt = kwargs["prompt"]
        if kwargs["loop_count"] is not None:
            item.loop_count = kwargs["loop_count"]
        item.execution_snapshot.update(kwargs["selector_patch"])
        cls.queue.revision += 1
        item.stream_revision = cls.queue.revision
        return item

    @classmethod
    async def delete_item(cls, item_id, **kwargs):
        if cls.conflict:
            raise cls.conflict
        if cls.items[item_id].status not in {"pending", "failed"}:
            raise ChatQueueMutationError("Item is immutable")
        del cls.items[item_id]
        cls.queue.revision += 1

    @classmethod
    async def reorder_pending(
        cls, queue_id, *, chat_session_id, item_ids, expected_revision
    ):
        if cls.conflict:
            raise cls.conflict
        if cls.queue.revision != expected_revision:
            raise ChatQueueRevisionConflict("Queue revision is stale")
        for index, item_id in enumerate(item_ids, start=1):
            cls.items[item_id].position = index * 10
        cls.queue.revision += 1
        for item_id in item_ids:
            cls.items[item_id].stream_revision = cls.queue.revision
        return cls.queue

    @classmethod
    async def retry_failed(cls, *, item_id, queue_id, chat_session_id):
        if cls.conflict:
            raise cls.conflict
        item = cls.items[item_id]
        if item.status != "failed":
            raise ChatQueueMutationError("Only failed items may be retried")
        item.status = "pending"
        item.runner_state = "idle"
        cls.queue.revision += 1
        item.stream_revision = cls.queue.revision
        return item

    @classmethod
    async def list_revision_changes(cls, *, queue_id, chat_session_id, after_revision):
        queue = cls.queue if cls.queue.revision > after_revision else None
        items = [
            item for item in cls.items.values() if item.stream_revision > after_revision
        ]
        return queue, items

    @classmethod
    async def has_running_item(cls, chat_session_id):
        return any(
            item.chat_session == chat_session_id and item.status == "running"
            for item in cls.items.values()
        )

    @classmethod
    async def delete_for_session(cls, chat_session_id):
        cls.cleanup_calls += 1
        cls.items = {
            item_id: item
            for item_id, item in cls.items.items()
            if item.chat_session != chat_session_id
        }

    @classmethod
    async def delete_session_if_idle(cls, chat_session_id):
        if await cls.has_running_item(chat_session_id):
            raise ChatQueueMutationError("Queue item is running")
        await cls.delete_for_session(chat_session_id)
        return True


@pytest.fixture(autouse=True)
def reset_fake_repository():
    FakeRepository.reset()


@pytest.fixture
def service(monkeypatch):
    module = _service_module()
    monkeypatch.setattr(module.ChatSession, "get", AsyncMock(return_value=_session()))
    submitter = MagicMock(return_value="command:runner-a")
    return module.ChatQueueService(
        repository=FakeRepository,
        command_submitter=submitter,
        poll_interval_seconds=0,
        heartbeat_interval_seconds=0,
    )


@pytest.mark.asyncio
async def test_missing_and_guest_sessions_are_rejected(monkeypatch):
    module = _service_module()
    get_session = AsyncMock(side_effect=[None, _session(guest_key="guest-a")])
    monkeypatch.setattr(module.ChatSession, "get", get_session)
    queue_service = module.ChatQueueService(
        repository=FakeRepository,
        command_submitter=MagicMock(),
    )

    with pytest.raises(module.ChatQueueNotFoundError):
        await queue_service.get_queue("missing")
    with pytest.raises(module.ChatQueueForbiddenError):
        await queue_service.get_queue("session-a")

    assert get_session.await_args_list[0].args == ("chat_session:missing",)


@pytest.mark.asyncio
async def test_missing_or_foreign_item_is_not_found(service):
    module = _service_module()

    with pytest.raises(module.ChatQueueNotFoundError):
        await service.update_item(
            "session-a",
            "missing",
            ChatQueueItemUpdateRequest(prompt="Revised"),
        )


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_and_schedules_one_runner(service):
    request = ChatQueueItemEnqueueRequest(
        client_request_id="request-new",
        prompt="  Explain the estimate  ",
        loop_count=2,
        model_id="model:gpt",
        context_config={"source_ids": ["source:a"]},
    )

    first = await service.enqueue("session-a", request)
    repeated = await service.enqueue("chat_session:session-a", request)

    assert first.id == repeated.id
    assert first.prompt == "Explain the estimate"
    assert first.execution_snapshot.model_id == "model:gpt"
    assert service.command_submitter.call_count == 1
    assert service.command_submitter.call_args.args[:2] == (
        "construction_os",
        "drain_chat_queue",
    )
    assert FakeRepository.submit_reservations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["project", "source"])
async def test_enqueue_omitted_selectors_inherit_session_defaults(monkeypatch, scope):
    """Project and source queue items freeze effective session selectors."""
    module = _service_module()
    session = _session(
        model_override=f"model:{scope}",
        skill_ids=[f"skill:{scope}"],
        html_template_id=f"html_template:{scope}",
    )
    monkeypatch.setattr(module.ChatSession, "get", AsyncMock(return_value=session))
    queue_service = module.ChatQueueService(
        repository=FakeRepository,
        command_submitter=MagicMock(return_value="command:runner-a"),
    )

    item = await queue_service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id=f"defaults-{scope}",
            prompt=f"Use {scope} defaults",
            tool_ids=["mcp_tool:request-only"],
            artifact_id="artifact:request-only",
            context_config={"scope": scope},
        ),
    )

    assert item.execution_snapshot.model_id == f"model:{scope}"
    assert item.execution_snapshot.skill_ids == [f"skill:{scope}"]
    assert item.execution_snapshot.html_template_id == f"html_template:{scope}"
    assert item.execution_snapshot.tool_ids == ["mcp_tool:request-only"]
    assert item.execution_snapshot.artifact_id == "artifact:request-only"
    assert item.execution_snapshot.context_config == {"scope": scope}


@pytest.mark.asyncio
async def test_enqueue_explicit_null_or_empty_selectors_clear_session_defaults(
    monkeypatch,
):
    """Explicit selector clears remain distinct from omitted inherited values."""
    module = _service_module()
    session = _session(
        model_override="model:session",
        skill_ids=["skill:session"],
        html_template_id="html_template:session",
    )
    monkeypatch.setattr(module.ChatSession, "get", AsyncMock(return_value=session))
    queue_service = module.ChatQueueService(
        repository=FakeRepository,
        command_submitter=MagicMock(return_value="command:runner-a"),
    )

    item = await queue_service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="explicit-clears",
            prompt="Clear inherited selectors",
            model_id=None,
            skill_ids=None,
            html_template_id=None,
        ),
    )

    assert item.execution_snapshot.model_id is None
    assert item.execution_snapshot.skill_ids == []
    assert item.execution_snapshot.html_template_id is None


@pytest.mark.asyncio
async def test_enqueue_while_paused_does_not_schedule(service):
    FakeRepository.queue = _queue(status="paused")

    item = await service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="paused-request",
            prompt="Wait until resumed",
        ),
    )

    assert item.status == "pending"
    service.command_submitter.assert_not_called()
    assert FakeRepository.queue.runner_state == "idle"


@pytest.mark.asyncio
async def test_enqueue_can_defer_runner_scheduling(service):
    item = await service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="deferred-request",
            prompt="Hold until the live turn finishes",
            schedule_runner=False,
        ),
    )

    assert item.status == "pending"
    service.command_submitter.assert_not_called()
    assert FakeRepository.queue.runner_state == "idle"


@pytest.mark.asyncio
async def test_resume_unpauses_and_ensures_runner(service):
    FakeRepository.queue = _queue(status="paused")

    snapshot = await service.update_queue("session-a", "active")

    assert snapshot.status == "active"
    assert snapshot.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_resume_retries_failed_frontier_and_schedules(service):
    FakeRepository.queue = _queue(status="paused", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:failed": _item(
            id="chat_queue_item:failed",
            status="failed",
            position=10,
            error_message="boom",
        ),
        "chat_queue_item:pending": _item(
            id="chat_queue_item:pending",
            status="pending",
            position=20,
        ),
    }

    snapshot = await service.update_queue("session-a", "active")

    assert snapshot.status == "active"
    assert FakeRepository.items["chat_queue_item:failed"].status == "pending"
    assert snapshot.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_resume_clears_stale_schedule_and_resubmits(service):
    FakeRepository.queue = _queue(
        status="paused",
        runner_state="scheduled",
        scheduling_token="stale-token",
        scheduling_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        runner_command_id="command:stale",
    )

    snapshot = await service.update_queue("session-a", "active")

    assert snapshot.status == "active"
    assert snapshot.runner_state == "scheduled"
    assert FakeRepository.queue.scheduling_token != "stale-token"
    assert FakeRepository.queue.runner_command_id == "command:runner-a"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_runner_schedules_for_orphaned_running_item(service):
    FakeRepository.queue = _queue(status="active", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:item-a": _item(status="running", current_loop=2, loop_count=3)
    }

    result = await service._ensure_runner(FakeRepository.queue)

    assert result.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_get_queue_does_not_schedule_pending_work(service):
    FakeRepository.queue = _queue(status="active", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:pending": _item(status="pending", position=10)
    }

    snapshot = await service.get_queue("session-a")

    assert snapshot.status == "active"
    assert snapshot.runner_state == "idle"
    service.command_submitter.assert_not_called()


@pytest.mark.asyncio
async def test_get_queue_schedules_orphaned_running_item(service):
    FakeRepository.queue = _queue(status="active", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:running": _item(
            status="running", current_loop=1, loop_count=1, position=10
        )
    }

    snapshot = await service.get_queue("session-a")

    assert snapshot.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_runner_schedules_pending_despite_earlier_failed_item(service):
    FakeRepository.queue = _queue(status="active", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:failed": _item(
            id="chat_queue_item:failed",
            status="failed",
            position=10,
            error_message="Stream update rejected",
        ),
        "chat_queue_item:pending": _item(
            id="chat_queue_item:pending",
            status="pending",
            position=20,
        ),
    }

    result = await service._ensure_runner(FakeRepository.queue)

    assert result.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_runner_schedules_pending_before_later_failures(service):
    FakeRepository.queue = _queue(status="active", runner_state="idle")
    FakeRepository.items = {
        "chat_queue_item:pending": _item(
            id="chat_queue_item:pending",
            status="pending",
            position=10,
        ),
        "chat_queue_item:failed": _item(
            id="chat_queue_item:failed",
            status="failed",
            position=20,
            error_message="later failure",
        ),
    }

    result = await service._ensure_runner(FakeRepository.queue)

    assert result.runner_state == "scheduled"
    service.command_submitter.assert_called_once()


@pytest.mark.asyncio
async def test_submission_failure_returns_item_and_leaves_pending(service):
    service.command_submitter.side_effect = RuntimeError("worker unavailable")

    item = await service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="offline-request",
            prompt="Persist even if worker is offline",
        ),
    )

    assert item.status == "pending"
    assert item.prompt == "Persist even if worker is offline"
    queued = FakeRepository.items["chat_queue_item:item-new"]
    assert queued.status == "pending"
    assert FakeRepository.queue.runner_state == "idle"
    assert FakeRepository.queue.runner_command_id is None
    assert FakeRepository.queue.scheduling_token is None
    assert FakeRepository.queue.scheduling_expires_at is None


@pytest.mark.asyncio
async def test_uncertain_submission_retains_reservation_to_prevent_duplicates(service):
    module = _service_module()
    request = ChatQueueItemEnqueueRequest(
        client_request_id="uncertain-request",
        prompt="Do not submit this twice",
    )
    service.command_submitter.side_effect = TimeoutError("outcome unknown")

    with pytest.raises(module.ChatQueueSubmissionError) as raised:
        await service.enqueue("session-a", request)
    assert raised.value.uncertain is True
    retried = await service.enqueue("session-a", request)

    assert retried.client_request_id == "uncertain-request"
    assert service.command_submitter.call_count == 1
    assert FakeRepository.queue.runner_state == "scheduled"
    assert FakeRepository.queue.runner_command_id is None
    assert FakeRepository.queue.scheduling_token.startswith("chat-queue-schedule-")
    assert FakeRepository.queue.scheduling_expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_stale_reservation_recovers_while_fresh_reservation_excludes(service):
    request = ChatQueueItemEnqueueRequest(
        client_request_id="reservation-request",
        prompt="Recover bounded scheduling",
    )
    service.command_submitter.side_effect = TimeoutError("outcome unknown")

    with pytest.raises(_service_module().ChatQueueSubmissionError):
        await service.enqueue("session-a", request)
    await service.enqueue("session-a", request)
    assert service.command_submitter.call_count == 1

    FakeRepository.queue.scheduling_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    service.command_submitter.side_effect = None
    service.command_submitter.return_value = "command:recovered"
    recovered = await service.enqueue("session-a", request)

    assert recovered.status == "pending"
    assert service.command_submitter.call_count == 2
    assert FakeRepository.queue.runner_command_id == "command:recovered"
    assert FakeRepository.queue.scheduling_token is not None
    assert FakeRepository.queue.scheduling_expires_at is not None


@pytest.mark.asyncio
async def test_worker_offline_after_submission_keeps_pending_scheduled(service):
    item = await service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="accepted-request",
            prompt="Worker may pick this up later",
        ),
    )

    assert item.status == "pending"
    assert FakeRepository.queue.runner_state == "scheduled"
    assert FakeRepository.queue.runner_command_id == "command:runner-a"
    assert FakeRepository.queue.scheduling_token is not None


@pytest.mark.asyncio
async def test_record_id_command_submission_is_stringified(service):
    command_id = RecordID("command", "runner-record")
    service.command_submitter.return_value = command_id

    await service.enqueue(
        "session-a",
        ChatQueueItemEnqueueRequest(
            client_request_id="record-id-request",
            prompt="Accept the real command identifier type",
        ),
    )

    assert FakeRepository.queue.runner_command_id == str(command_id)


@pytest.mark.asyncio
async def test_finish_before_submit_confirmation_returns_latest_idle_queue(service):
    original = FakeRepository.queue

    def finish_runner_before_return(*args):
        FakeRepository.queue = _queue(
            revision=original.revision + 3,
            runner_state="idle",
            runner_command_id=None,
            scheduling_token=None,
            scheduling_expires_at=None,
            lease_owner=None,
            lease_expires_at=None,
        )
        return "command:finished"

    service.command_submitter.side_effect = finish_runner_before_return

    result = await service._ensure_runner(original)

    assert result.runner_state == "idle"
    assert result.runner_command_id is None
    assert result.scheduling_token is None
    assert result.lease_owner is None


def test_command_submitter_type_accepts_surreal_record_id():
    module = _service_module()

    assert "RecordID" in str(module.CommandResult)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "conflict"),
    [
        ("update", ChatQueueMutationError("running item")),
        ("delete", ChatQueueMutationError("running item")),
        ("reorder", ChatQueueRevisionConflict("stale revision")),
        ("retry", ChatQueueMutationError("not failed")),
    ],
)
async def test_mutation_conflicts_map_cleanly(service, operation, conflict):
    module = _service_module()
    FakeRepository.conflict = conflict

    with pytest.raises(module.ChatQueueConflictError):
        if operation == "update":
            await service.update_item(
                "session-a",
                "item-a",
                ChatQueueItemUpdateRequest(prompt="Revised"),
            )
        elif operation == "delete":
            await service.delete_item("session-a", "item-a")
        elif operation == "reorder":
            await service.reorder(
                "session-a",
                ChatQueueReorderRequest(
                    item_ids=["chat_queue_item:item-a"],
                    expected_revision=0,
                ),
            )
        else:
            FakeRepository.items["chat_queue_item:item-a"].status = "failed"
            await service.retry_item("session-a", "item-a")


@pytest.mark.asyncio
async def test_sse_initial_snapshot_and_reconnect_only_emit_newer_revisions(service):
    disconnected = AsyncMock(side_effect=[False, True])
    initial_events = [
        event
        async for event in service.stream_events(
            "session-a",
            after_revision=None,
            is_disconnected=disconnected,
        )
    ]
    assert initial_events[0].event == "snapshot"
    assert initial_events[0].queue is not None

    FakeRepository.queue.revision = 2
    FakeRepository.items["chat_queue_item:item-a"].stream_revision = 2
    reconnected = AsyncMock(side_effect=[False, True])
    reconnect_events = [
        event
        async for event in service.stream_events(
            "session-a",
            after_revision=1,
            is_disconnected=reconnected,
        )
    ]
    assert all(event.revision == 2 for event in reconnect_events)
    assert any(
        event.item is not None
        or (event.queue is not None and len(event.queue.items) > 0)
        for event in reconnect_events
    )


@pytest.mark.asyncio
async def test_sse_zero_cursor_immediately_hydrates_empty_revision(service):
    FakeRepository.queue.revision = 0
    disconnected = AsyncMock(return_value=True)
    stream = service.stream_events(
        "session-a",
        after_revision=0,
        is_disconnected=disconnected,
    )

    event = await anext(stream)

    assert event.event == "snapshot"
    assert event.revision == 0


@pytest.mark.asyncio
async def test_high_queue_revision_does_not_hide_new_item_event(service):
    FakeRepository.queue.revision = 100
    FakeRepository.items["chat_queue_item:item-a"].stream_revision = 100
    updated = await service.update_item(
        "session-a",
        "item-a",
        ChatQueueItemUpdateRequest(prompt="Global revision update"),
    )
    disconnected = AsyncMock(side_effect=[False, True])

    events = [
        event
        async for event in service.stream_events(
            "session-a",
            after_revision=100,
            is_disconnected=disconnected,
        )
    ]

    assert updated.stream_revision == 101
    assert FakeRepository.queue.revision == 101
    delivered = [
        item
        for event in events
        for item in (
            [event.item]
            if event.item is not None
            else (event.queue.items if event.queue is not None else [])
        )
    ]
    assert any(
        item.prompt == "Global revision update" and item.stream_revision == 101
        for item in delivered
    )


@pytest.mark.asyncio
async def test_live_global_revision_emits_full_queue_before_item_detail(
    service, monkeypatch
):
    FakeRepository.queue.revision = 100
    FakeRepository.items["chat_queue_item:item-a"].stream_revision = 100
    emitted = False

    async def mutate_once(cls, *, queue_id, chat_session_id, after_revision):
        nonlocal emitted
        if emitted:
            return None, []
        emitted = True
        cls.queue.revision = 101
        item = cls.items["chat_queue_item:item-a"]
        item.prompt = "Live update"
        item.stream_revision = 101
        return cls.queue, [item]

    monkeypatch.setattr(
        FakeRepository,
        "list_revision_changes",
        classmethod(mutate_once),
    )
    disconnected = AsyncMock(side_effect=[False, True])

    events = [
        event
        async for event in service.stream_events(
            "session-a",
            after_revision=100,
            is_disconnected=disconnected,
        )
    ]

    assert events[0].queue is not None
    assert events[0].revision == 101
    assert events[0].queue.items[0].prompt == "Live update"


@pytest.mark.asyncio
async def test_sse_emits_heartbeat_and_disconnect_has_no_execution_side_effect(
    service,
):
    FakeRepository.queue.revision = 0
    disconnected = AsyncMock(side_effect=[False, False, True])

    events = [
        event
        async for event in service.stream_events(
            "session-a",
            after_revision=0,
            is_disconnected=disconnected,
        )
    ]

    assert any(event.event == "heartbeat" for event in events)
    assert FakeRepository.queue.runner_state == "idle"
    assert FakeRepository.cleanup_calls == 0


@pytest.mark.asyncio
async def test_sse_cancellation_propagates_without_changing_queue(service):
    disconnected = AsyncMock(return_value=False)
    stream = service.stream_events(
        "session-a",
        after_revision=FakeRepository.queue.revision,
        is_disconnected=disconnected,
    )
    task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert FakeRepository.queue.runner_state == "idle"
    assert FakeRepository.cleanup_calls == 0


@pytest.mark.asyncio
async def test_session_deletion_guard_and_cleanup(service):
    module = _service_module()
    FakeRepository.items["chat_queue_item:item-a"].status = "running"

    with pytest.raises(module.ChatQueueConflictError):
        await service.delete_session("session-a")
    assert FakeRepository.cleanup_calls == 0

    FakeRepository.items["chat_queue_item:item-a"].status = "pending"
    await service.delete_session("session-a")
    assert FakeRepository.cleanup_calls == 1


def test_router_exposes_exact_queue_endpoints():
    spec = find_spec("api.routers.chat_queue")
    assert spec is not None, "api.routers.chat_queue has not been implemented"
    router_module = import_module("api.routers.chat_queue")
    routes = {
        (route.path, method)
        for route in router_module.router.routes
        for method in route.methods
    }

    assert routes == {
        ("/chat/sessions/{session_id}/queue", "GET"),
        ("/chat/sessions/{session_id}/queue/items", "POST"),
        ("/chat/sessions/{session_id}/queue", "PATCH"),
        ("/chat/sessions/{session_id}/queue/items/{item_id}", "PATCH"),
        ("/chat/sessions/{session_id}/queue/items/{item_id}", "DELETE"),
        ("/chat/sessions/{session_id}/queue/order", "PUT"),
        ("/chat/sessions/{session_id}/queue/items/{item_id}/retry", "POST"),
        ("/chat/sessions/{session_id}/queue/stream", "GET"),
    }


@pytest.mark.parametrize(
    ("after_revision", "last_event_id", "expected"),
    [
        (9, "3", 9),
        (0, "7", 0),
        (None, "7", 7),
        (None, None, 0),
    ],
)
def test_sse_cursor_precedence(after_revision, last_event_id, expected):
    module = _service_module()

    assert (
        module.resolve_stream_after_revision(after_revision, last_event_id) == expected
    )


@pytest.mark.parametrize("last_event_id", ["", "abc", "-1", "1.5"])
def test_sse_last_event_id_rejects_invalid_values(last_event_id):
    module = _service_module()

    with pytest.raises(module.ChatQueueValidationError):
        module.resolve_stream_after_revision(None, last_event_id)


@pytest.mark.asyncio
async def test_sse_router_sets_streaming_headers(monkeypatch):
    router_module = import_module("api.routers.chat_queue")
    snapshot = _service_module().ChatQueueService(
        repository=FakeRepository,
        command_submitter=MagicMock(),
    )
    monkeypatch.setattr(
        "api.chat_queue_service.ChatSession.get",
        AsyncMock(return_value=_session()),
    )
    monkeypatch.setattr(router_module, "chat_queue_service", snapshot)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    response = await router_module.stream_queue(
        "session-a",
        request,
        after_revision=None,
        last_event_id=None,
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_sse_router_uses_last_event_id_and_query_precedence(monkeypatch):
    router_module = import_module("api.routers.chat_queue")
    observed = []

    class StubService:
        async def get_queue(self, session_id):
            return _queue()

        async def stream_events(self, session_id, *, after_revision, is_disconnected):
            observed.append(after_revision)
            if False:
                yield None

    monkeypatch.setattr(router_module, "chat_queue_service", StubService())
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    header_response = await router_module.stream_queue(
        "session-a",
        request,
        after_revision=None,
        last_event_id="12",
    )
    async for _ in header_response.body_iterator:
        pass
    query_response = await router_module.stream_queue(
        "session-a",
        request,
        after_revision=4,
        last_event_id="not-an-integer",
    )
    async for _ in query_response.body_iterator:
        pass

    assert observed == [12, 4]


@pytest.mark.asyncio
async def test_sse_router_maps_invalid_last_event_id_to_400(monkeypatch):
    router_module = import_module("api.routers.chat_queue")
    monkeypatch.setattr(
        router_module.chat_queue_service,
        "get_queue",
        AsyncMock(return_value=_queue()),
    )
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    with pytest.raises(HTTPException) as caught:
        await router_module.stream_queue(
            "session-a",
            request,
            after_revision=None,
            last_event_id="-1",
        )

    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_project_session_deletion_guard_then_cleanup():
    module = _service_module()
    router = import_module("api.routers.chat")
    session = _session()
    session.delete = AsyncMock()
    queue_service = SimpleNamespace(
        delete_session=AsyncMock(
            side_effect=module.ChatQueueConflictError("Queue item is running")
        )
    )
    kwargs = {"session_id": "session-a", "x_guest_key": None}

    with patch.object(router.ChatSession, "get", AsyncMock(return_value=session)), patch.object(
        router, "chat_queue_service", queue_service
    ):
        with pytest.raises(HTTPException) as caught:
            await router.delete_session(**kwargs)
    assert caught.value.status_code == 409
    session.delete.assert_not_awaited()

    queue_service.delete_session.side_effect = None
    with patch.object(router.ChatSession, "get", AsyncMock(return_value=session)), patch.object(
        router, "chat_queue_service", queue_service
    ):
        await router.delete_session(**kwargs)
    queue_service.delete_session.assert_awaited()
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_result_maps_runtime_error_to_json_detail():
    router = import_module("api.routers.chat_queue")

    async def boom():
        raise RuntimeError("The query was not executed due to a failed transaction")

    with pytest.raises(HTTPException) as caught:
        await router._service_result(boom())

    assert caught.value.status_code == 500
    assert "failed transaction" in caught.value.detail
