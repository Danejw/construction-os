"""Temporal, fact-level current-state memory for Construction OS project chats.

Project memory remains separate from vector and graph retrieval. It stores compact,
project-scoped facts with server-owned timestamps so agents can reason about what is
current, what was superseded, and what was explicitly removed without trusting the
language model to generate dates.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator
from surreal_commands import submit_command

from construction_os.ai.structured import invoke_structured
from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.domain.project import Note, Source
from construction_os.utils.text_utils import extract_text_content

_CANDIDATE_MAX_CHARS = 16_000
_EVIDENCE_ITEM_MAX_CHARS = 6_000
_EVIDENCE_TOTAL_MAX_CHARS = 24_000
_MEMORY_ID_PREFIX = "project_memory"
_EVIDENCE_ID_RE = re.compile(r"\b(?:source|note):[A-Za-z0-9_-]+\b")
_TRIVIAL_CHAT_RE = re.compile(
    r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay|got it|yes|no|cool|great)[.!?\s]*$",
    re.IGNORECASE,
)

MemoryCategory = Literal[
    "status",
    "scope",
    "requirement",
    "decision",
    "deadline",
    "risk",
    "open_question",
    "next_action",
    "other",
]
MemoryStatus = Literal["active", "superseded", "deleted"]
MemoryOperationType = Literal["merge", "supersede", "delete"]


def _clip(value: Any, maximum: int) -> str:
    text = str(value or "").strip()
    if len(text) <= maximum:
        return text
    return text[: maximum - 15].rstrip() + "\n...[truncated]"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_server_timestamp(value: Optional[str] = None) -> str:
    """Return a timezone-aware UTC ISO timestamp or reject invalid input."""
    if value is None:
        return _utc_now()
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(normalize_server_timestamp(value))


class ProjectMemoryFact(BaseModel):
    """One temporal project fact with server-owned validity timestamps."""

    fact_id: str
    category: MemoryCategory = "other"
    subject: str
    value: str
    status: MemoryStatus = "active"
    valid_from: str
    valid_to: Optional[str] = None
    recorded_at: str
    updated_at: str
    evidence_ids: list[str] = Field(default_factory=list)
    supersedes_fact_id: Optional[str] = None
    last_operation: MemoryOperationType = "merge"

    @field_validator("fact_id", "subject", "value")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("fact fields cannot be empty")
        return normalized

    @field_validator("valid_from", "valid_to", "recorded_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: Optional[str]) -> Optional[str]:
        return normalize_server_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def validate_temporal_window(self) -> "ProjectMemoryFact":
        if self.status == "active" and self.valid_to is not None:
            raise ValueError("active facts cannot have valid_to")
        if self.status != "active" and self.valid_to is None:
            raise ValueError("inactive facts require valid_to")
        if self.valid_to and _timestamp_value(self.valid_to) < _timestamp_value(
            self.valid_from
        ):
            raise ValueError("valid_to cannot precede valid_from")
        return self


class ProjectMemorySnapshot(BaseModel):
    """One current fact collection for a project."""

    project_id: str
    facts: list[ProjectMemoryFact] = Field(default_factory=list)
    # Compatibility text for existing tools and pre-fact records. Facts are authoritative.
    content: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    revision: int = 0
    last_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_snapshot_timestamps(cls, value: Optional[str]) -> Optional[str]:
        return normalize_server_timestamp(value) if value is not None else None


class ProjectMemoryOperation(BaseModel):
    """One explicit fact-level change selected by the consolidator."""

    operation: MemoryOperationType
    target_fact_id: Optional[str] = None
    category: Optional[MemoryCategory] = None
    subject: Optional[str] = None
    value: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "ProjectMemoryOperation":
        if self.operation == "delete":
            if not self.target_fact_id:
                raise ValueError("delete requires target_fact_id")
            return self
        if self.operation == "supersede" and not self.target_fact_id:
            raise ValueError("supersede requires target_fact_id")
        if not self.category or not str(self.subject or "").strip() or not str(
            self.value or ""
        ).strip():
            raise ValueError(f"{self.operation} requires category, subject, and value")
        self.subject = str(self.subject).strip()
        self.value = str(self.value).strip()
        return self


class ProjectMemoryDecision(BaseModel):
    """Strict consolidator response containing zero or more explicit operations."""

    action: Literal["apply", "noop"]
    operations: list[ProjectMemoryOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision(self) -> "ProjectMemoryDecision":
        if self.action == "noop" and self.operations:
            raise ValueError("noop cannot contain operations")
        if self.action == "apply" and not self.operations:
            raise ValueError("apply requires at least one operation")
        return self


def project_memory_record_id(project_id: str) -> str:
    """Return a stable Surreal record ID without exposing the project ID as a key."""
    normalized = str(project_id or "").strip()
    if not normalized.startswith("project:"):
        raise ValueError("project_id must identify a project")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"{_MEMORY_ID_PREFIX}:{digest}"


def project_memory_fact_id(
    project_id: str,
    *,
    category: str,
    subject: str,
    value: str,
    event_at: str,
    ordinal: int,
) -> str:
    """Create a deterministic fact ID on the server for one consolidation event."""
    payload = "\0".join(
        [project_id, category, subject.strip().lower(), value.strip(), event_at, str(ordinal)]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"memory_fact:{digest}"


def extract_evidence_ids(text: str) -> list[str]:
    """Extract stable source/note IDs in first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _EVIDENCE_ID_RE.findall(text or ""):
        if match not in seen:
            seen.add(match)
            ordered.append(match)
    return ordered


def should_consolidate_chat(user_text: str, assistant_text: str) -> bool:
    """Skip only clearly trivial turns; the consolidator performs final no-op filtering."""
    user = str(user_text or "").strip()
    assistant = str(assistant_text or "").strip()
    if not user or not assistant:
        return False
    return not bool(_TRIVIAL_CHAT_RE.fullmatch(user))


def _legacy_fact(snapshot: ProjectMemorySnapshot) -> Optional[ProjectMemoryFact]:
    content = snapshot.content.strip()
    if not content:
        return None
    timestamp = normalize_server_timestamp(
        snapshot.updated_at or snapshot.created_at or _utc_now()
    )
    return ProjectMemoryFact(
        fact_id=project_memory_fact_id(
            snapshot.project_id,
            category="status",
            subject="Legacy consolidated project state",
            value=content,
            event_at=timestamp,
            ordinal=0,
        ),
        category="status",
        subject="Legacy consolidated project state",
        value=content,
        valid_from=timestamp,
        recorded_at=timestamp,
        updated_at=timestamp,
        evidence_ids=list(snapshot.evidence_ids),
        last_operation="merge",
    )


async def get_project_memory(project_id: str) -> Optional[ProjectMemorySnapshot]:
    """Load current project memory, upgrading a legacy text snapshot in memory."""
    memory_id = project_memory_record_id(project_id)
    rows = await repo_query(
        "SELECT * FROM $id",
        {"id": ensure_record_id(memory_id)},
    )
    if not rows:
        return None
    row = dict(rows[0])
    row.pop("id", None)
    try:
        snapshot = ProjectMemorySnapshot(**row)
        if not snapshot.facts:
            legacy = _legacy_fact(snapshot)
            if legacy:
                snapshot.facts = [legacy]
        return snapshot
    except Exception as exc:
        logger.warning("Ignoring invalid project memory {}: {}", memory_id, exc)
        return None


def _all_evidence_ids(facts: Sequence[ProjectMemoryFact]) -> list[str]:
    return list(
        dict.fromkeys(
            evidence_id
            for fact in facts
            for evidence_id in fact.evidence_ids
            if evidence_id
        )
    )


def _render_fact_line(fact: ProjectMemoryFact) -> str:
    evidence = ", ".join(fact.evidence_ids[:10]) or "none recorded"
    temporal = f"valid from {fact.valid_from}"
    if fact.valid_to:
        temporal += f" through {fact.valid_to}"
    return (
        f"- [{fact.fact_id}] [{fact.status}; {temporal}] "
        f"{fact.category} / {fact.subject}: {fact.value} "
        f"(evidence: {evidence})"
    )


def render_project_memory_content(facts: Sequence[ProjectMemoryFact]) -> str:
    """Render facts as compact text while preserving temporal history."""
    active = sorted(
        (fact for fact in facts if fact.status == "active"),
        key=lambda fact: (fact.category, fact.subject.lower(), fact.valid_from),
    )
    history = sorted(
        (fact for fact in facts if fact.status != "active"),
        key=lambda fact: fact.valid_to or fact.updated_at,
        reverse=True,
    )[:30]
    parts = ["## Active facts"]
    parts.extend(_render_fact_line(fact) for fact in active)
    if history:
        parts.extend(["", "## Recent superseded or deleted facts"])
        parts.extend(_render_fact_line(fact) for fact in history)
    return "\n".join(parts).strip()


async def save_project_memory(
    *,
    project_id: str,
    facts: Sequence[ProjectMemoryFact],
    revision: int,
    reason: str,
    created_at: Optional[str] = None,
) -> ProjectMemorySnapshot:
    """Upsert the single temporal fact collection for a project."""
    now = _utc_now()
    fact_list = list(facts)
    snapshot = ProjectMemorySnapshot(
        project_id=project_id,
        facts=fact_list,
        content=render_project_memory_content(fact_list),
        evidence_ids=_all_evidence_ids(fact_list),
        revision=max(1, int(revision)),
        last_reason=reason,
        created_at=created_at or now,
        updated_at=now,
    )
    await repo_query(
        "UPSERT $id CONTENT $memory",
        {
            "id": ensure_record_id(project_memory_record_id(project_id)),
            "memory": snapshot.model_dump(),
        },
    )
    return snapshot


async def delete_project_memory(project_id: str) -> None:
    """Delete a project's synthesized state. Intended for project cleanup flows."""
    await repo_query(
        "DELETE $id",
        {"id": ensure_record_id(project_memory_record_id(project_id))},
    )


def format_project_memory(snapshot: ProjectMemorySnapshot) -> str:
    """Render temporal memory for prompt injection as working state, not evidence."""
    return (
        "# CURRENT PROJECT STATE\n\n"
        "Facts below are a compact synthesized working state, not a replacement for "
        "source evidence. Timestamps are server-generated UTC values. Use active facts "
        "for current truth and historical facts for temporal questions. Verify "
        "consequential details against retrieved documents.\n\n"
        f"Revision: {snapshot.revision}\n"
        f"Updated: {snapshot.updated_at or 'unknown'}\n\n"
        f"{render_project_memory_content(snapshot.facts)}"
    )


async def inject_project_memory(
    payload: list[BaseMessage], *, project_id: str
) -> list[BaseMessage]:
    """Append current project state to the existing system prompt."""
    snapshot = await get_project_memory(project_id)
    if snapshot is None or not snapshot.facts:
        return list(payload)

    messages = list(payload)
    memory_block = format_project_memory(snapshot)
    for index, message in enumerate(messages):
        if isinstance(message, SystemMessage):
            base = extract_text_content(message.content).rstrip()
            messages[index] = message.model_copy(
                update={"content": f"{base}\n\n{memory_block}"}
            )
            return messages
    return [SystemMessage(content=memory_block), *messages]


async def _load_evidence(evidence_ids: Sequence[str]) -> str:
    blocks: list[str] = []
    total = 0
    for evidence_id in list(dict.fromkeys(evidence_ids))[:20]:
        try:
            if evidence_id.startswith("source:"):
                item = await Source.get(evidence_id)
                context = await item.get_context(context_size="long")
                title = context.get("title") or "Untitled source"
                content = context.get("full_text") or ""
            elif evidence_id.startswith("note:"):
                item = await Note.get(evidence_id)
                context = item.get_context(context_size="long")
                title = context.get("title") or "Untitled artifact"
                content = context.get("content") or ""
            else:
                continue
        except Exception as exc:
            logger.debug("Skipping memory evidence {}: {}", evidence_id, exc)
            continue

        block = (
            f"## {evidence_id} — {title}\n"
            f"{_clip(content, _EVIDENCE_ITEM_MAX_CHARS)}"
        ).strip()
        if not block:
            continue
        if total + len(block) > _EVIDENCE_TOTAL_MAX_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def _normalized_fact_key(category: str, subject: str, value: str) -> tuple[str, str, str]:
    return (
        category.strip().lower(),
        " ".join(subject.lower().split()),
        " ".join(value.lower().split()),
    )


def _bounded_evidence(
    requested: Sequence[str], previous: Sequence[str], proposed: Sequence[str]
) -> list[str]:
    allowed = set(requested) | set(previous)
    return list(dict.fromkeys(item for item in proposed if item in allowed))


def apply_project_memory_operations(
    *,
    project_id: str,
    previous_facts: Sequence[ProjectMemoryFact],
    operations: Sequence[ProjectMemoryOperation],
    requested_evidence_ids: Sequence[str],
    event_at: str,
) -> tuple[list[ProjectMemoryFact], bool]:
    """Apply explicit operations using only server-owned timestamps."""
    event_time = normalize_server_timestamp(event_at)
    recorded_at = _utc_now()
    facts = [fact.model_copy(deep=True) for fact in previous_facts]
    by_id = {fact.fact_id: fact for fact in facts}
    changed = False

    for ordinal, operation in enumerate(operations, start=1):
        target = by_id.get(operation.target_fact_id or "")
        if operation.operation in {"supersede", "delete"} and (
            target is None or target.status != "active"
        ):
            logger.warning(
                "Skipping {} operation with invalid active target {}",
                operation.operation,
                operation.target_fact_id,
            )
            continue

        if operation.operation == "delete":
            assert target is not None
            target.status = "deleted"
            target.valid_to = max(
                _timestamp_value(event_time), _timestamp_value(target.valid_from)
            ).isoformat()
            target.updated_at = recorded_at
            target.last_operation = "delete"
            target.evidence_ids = _bounded_evidence(
                requested_evidence_ids,
                target.evidence_ids,
                [*target.evidence_ids, *operation.evidence_ids],
            )
            changed = True
            continue

        assert operation.category is not None
        assert operation.subject is not None
        assert operation.value is not None
        proposed_evidence = _bounded_evidence(
            requested_evidence_ids,
            target.evidence_ids if target else [],
            operation.evidence_ids,
        )

        if operation.operation == "merge" and target is not None:
            if target.status != "active":
                logger.warning("Skipping merge into inactive fact {}", target.fact_id)
                continue
            target.category = operation.category
            target.subject = operation.subject
            target.value = operation.value
            target.evidence_ids = list(
                dict.fromkeys([*target.evidence_ids, *proposed_evidence])
            )
            target.updated_at = recorded_at
            target.last_operation = "merge"
            changed = True
            continue

        if operation.operation == "merge":
            key = _normalized_fact_key(
                operation.category, operation.subject, operation.value
            )
            duplicate = next(
                (
                    fact
                    for fact in facts
                    if fact.status == "active"
                    and _normalized_fact_key(fact.category, fact.subject, fact.value)
                    == key
                ),
                None,
            )
            if duplicate:
                merged_evidence = list(
                    dict.fromkeys([*duplicate.evidence_ids, *proposed_evidence])
                )
                if merged_evidence != duplicate.evidence_ids:
                    duplicate.evidence_ids = merged_evidence
                    duplicate.updated_at = recorded_at
                    duplicate.last_operation = "merge"
                    changed = True
                continue

        if operation.operation == "supersede":
            assert target is not None
            target.status = "superseded"
            target.valid_to = max(
                _timestamp_value(event_time), _timestamp_value(target.valid_from)
            ).isoformat()
            target.updated_at = recorded_at
            target.last_operation = "supersede"
            changed = True

        new_fact = ProjectMemoryFact(
            fact_id=project_memory_fact_id(
                project_id,
                category=operation.category,
                subject=operation.subject,
                value=operation.value,
                event_at=event_time,
                ordinal=ordinal,
            ),
            category=operation.category,
            subject=operation.subject,
            value=operation.value,
            valid_from=event_time,
            recorded_at=recorded_at,
            updated_at=recorded_at,
            evidence_ids=proposed_evidence,
            supersedes_fact_id=target.fact_id if target else None,
            last_operation=operation.operation,
        )
        facts.append(new_fact)
        by_id[new_fact.fact_id] = new_fact
        changed = True

    return facts, changed


async def consolidate_project_memory(
    *,
    project_id: str,
    reason: str,
    candidate_text: Optional[str] = None,
    evidence_ids: Optional[Sequence[str]] = None,
    model_id: Optional[str] = None,
    event_at: Optional[str] = None,
) -> tuple[ProjectMemorySnapshot | None, bool]:
    """Apply merge, supersede, or delete operations, or deliberately no-op."""
    trusted_event_at = normalize_server_timestamp(event_at)
    previous = await get_project_memory(project_id)
    previous_facts = previous.facts if previous else []
    requested_evidence = list(dict.fromkeys(evidence_ids or []))
    evidence_text = await _load_evidence(requested_evidence)
    previous_payload = [fact.model_dump() for fact in previous_facts]

    messages: list[BaseMessage] = [
        SystemMessage(
            content=(
                "You maintain fact-level memory for a construction project. Return only "
                "explicit operations. MERGE adds a compatible fact or enriches an active "
                "fact without changing its meaning. SUPERSEDE replaces an active fact "
                "whose current value changed while preserving its history. DELETE marks "
                "an incorrect or explicitly revoked active fact as deleted while preserving "
                "its audit history. NOOP means no durable project truth changed. Keep only "
                "current status, active scope and requirements, confirmed decisions, "
                "deadlines, risks, open questions, and next actions. Never invent facts, "
                "fact IDs, evidence IDs, or timestamps. You do not output timestamps; the "
                "server assigns and validates all temporal fields. target_fact_id must be "
                "an exact active fact ID from PREVIOUS FACTS. A single event may return "
                "multiple operations."
            )
        ),
        HumanMessage(
            content=(
                f"PROJECT ID\n{project_id}\n\n"
                f"SERVER EVENT TIME (for context only; do not return it)\n{trusted_event_at}\n\n"
                f"UPDATE REASON\n{reason}\n\n"
                "PREVIOUS FACTS\n"
                f"{json.dumps(previous_payload, ensure_ascii=False)}\n\n"
                "NEW EVENT OR CHAT RESULT\n"
                f"{_clip(candidate_text, _CANDIDATE_MAX_CHARS) or 'None supplied'}\n\n"
                "DIRECT SUPPORTING EVIDENCE\n"
                f"{evidence_text or 'No direct evidence text supplied.'}\n\n"
                "AVAILABLE EVIDENCE IDS\n"
                f"{json.dumps(requested_evidence, ensure_ascii=False)}"
            )
        ),
    ]

    decision = await invoke_structured(
        messages,
        ProjectMemoryDecision,
        model_id=model_id,
        default_type="chat",
        max_tokens=2200,
    )

    if decision.action == "noop":
        return previous, False

    facts, changed = apply_project_memory_operations(
        project_id=project_id,
        previous_facts=previous_facts,
        operations=decision.operations,
        requested_evidence_ids=requested_evidence,
        event_at=trusted_event_at,
    )
    if not changed:
        return previous, False

    snapshot = await save_project_memory(
        project_id=project_id,
        facts=facts,
        revision=(previous.revision if previous else 0) + 1,
        reason=reason,
        created_at=previous.created_at if previous else None,
    )
    return snapshot, True


def schedule_project_memory_consolidation(
    *,
    project_id: str,
    reason: str,
    candidate_text: Optional[str] = None,
    evidence_ids: Optional[Sequence[str]] = None,
    model_id: Optional[str] = None,
) -> Optional[str]:
    """Queue consolidation with an immutable server-generated UTC event timestamp."""
    try:
        command_id = submit_command(
            "construction_os",
            "consolidate_project_memory",
            {
                "project_id": project_id,
                "reason": reason,
                "candidate_text": _clip(candidate_text, _CANDIDATE_MAX_CHARS) or None,
                "evidence_ids": list(dict.fromkeys(evidence_ids or []))[:30],
                "model_id": model_id,
                "event_at": _utc_now(),
            },
        )
        return str(command_id)
    except Exception as exc:
        logger.warning(
            "Unable to queue project memory consolidation for {}: {}",
            project_id,
            exc,
        )
        return None
