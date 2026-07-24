"""Tests for MCP tool-call AG-UI progress events."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from construction_os.domain.mcp import ChatToolCall
from construction_os.mcp.progress import MCP_TOOL_CALL_EVENT, emit_mcp_tool_call


def test_emit_mcp_tool_call_dispatches_public_payload():
    audit = ChatToolCall(
        id="chat_tool_call:1",
        session_id="chat_session:abc",
        message_id="msg-1",
        tool_name="echo",
        connection_name="Fake",
        runtime_name="mcp__fake__echo",
        status="running",
        arguments={"text": "hi"},
    )

    with patch(
        "construction_os.tool_runtime.progress.dispatch_custom_event"
    ) as mock_dispatch:
        emit_mcp_tool_call(audit, config={"callbacks": []})

    mock_dispatch.assert_called_once()
    args, kwargs = mock_dispatch.call_args
    assert args[0] == MCP_TOOL_CALL_EVENT
    payload = args[1]
    assert payload["tool_name"] == "echo"
    assert payload["status"] == "running"
    assert payload["arguments"] == {"text": "hi"}
    assert "auth_config" not in payload
    assert kwargs.get("config") is not None


def test_emit_mcp_tool_call_noop_without_config():
    audit = MagicMock(spec=ChatToolCall)
    with patch(
        "construction_os.tool_runtime.progress.dispatch_custom_event"
    ) as mock_dispatch:
        emit_mcp_tool_call(audit, config=None)
    mock_dispatch.assert_not_called()
