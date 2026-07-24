"""Emit AG-UI-compatible agent progress custom events from LangGraph nodes."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from langchain_core.callbacks.manager import adispatch_custom_event, dispatch_custom_event
from langchain_core.runnables import RunnableConfig

AGENT_PROGRESS_EVENT = "agent_progress"
# AG-UI LangGraphAgent maps this to TEXT_MESSAGE_START/CONTENT/END.
MANUALLY_EMIT_MESSAGE_EVENT = "manually_emit_message"
# Citation deep-link focus map for the current retrieval turn (RAG-012).
EVIDENCE_FOCUS_EVENT = "evidence_focus"
# Cap removed IDs in progress detail so payloads stay small (RAG-015).
CITATION_REMOVED_IDS_CAP = 20

ProgressPhase = Literal["started", "progress", "completed"]

EMPTY_TOOL_TURN_FALLBACK = (
    "I finished using tools but did not produce a text reply. Please try again."
)


def emit_agent_progress(
    phase: ProgressPhase,
    step: str,
    detail: Optional[Dict[str, Any]] = None,
    config: Optional[RunnableConfig] = None,
) -> None:
    """Emit a sync custom event (for sync LangGraph nodes)."""
    if not config:
        return
    dispatch_custom_event(
        AGENT_PROGRESS_EVENT,
        {"phase": phase, "step": step, "detail": detail or {}},
        config=config,
    )


def emit_evidence_focus(
    items: list[Dict[str, Any]],
    config: Optional[RunnableConfig] = None,
) -> None:
    """Emit citation focus entries for PDF/text deep-links (RAG-012)."""
    if not config:
        return
    dispatch_custom_event(
        EVIDENCE_FOCUS_EVENT,
        {"items": items or []},
        config=config,
    )


def emit_citation_verify_progress(
    *,
    removed_ids: list[str],
    kept_ids: list[str],
    config: Optional[RunnableConfig] = None,
) -> None:
    """Emit citation strip metrics after RAG-002 verification (RAG-015)."""
    capped = list(removed_ids[:CITATION_REMOVED_IDS_CAP])
    emit_agent_progress(
        "completed",
        "verifying_citations",
        {
            "citationViolations": len(removed_ids),
            "removedCitationIds": capped,
            "keptCitationCount": len(kept_ids),
        },
        config,
    )


def emit_assistant_text_message(
    *,
    message_id: str,
    message: str,
    config: Optional[RunnableConfig] = None,
) -> bool:
    """Emit final assistant text for non-streaming model.invoke turns.

    AG-UI only streams TEXT_MESSAGE_* from OnChatModelStream; invoke-based
    tool loops need this so the client and queue see the answer.
    """
    text = (message or "").strip()
    if not text or not message_id or not config:
        return False
    dispatch_custom_event(
        MANUALLY_EMIT_MESSAGE_EVENT,
        {"message_id": message_id, "message": text},
        config=config,
    )
    return True


async def aemit_agent_progress(
    phase: ProgressPhase,
    step: str,
    detail: Optional[Dict[str, Any]] = None,
    config: Optional[RunnableConfig] = None,
) -> None:
    """Emit an async custom event (for async LangGraph nodes)."""
    if not config:
        return
    await adispatch_custom_event(
        AGENT_PROGRESS_EVENT,
        {"phase": phase, "step": step, "detail": detail or {}},
        config=config,
    )
