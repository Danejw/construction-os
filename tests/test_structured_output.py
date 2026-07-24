"""Tests for API-level structured output helper."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, Field

from construction_os.ai.structured import invoke_structured, with_structured_output_bound
from construction_os.knowledge.extractors.base import ExtractionPayload


class _SampleOut(BaseModel):
    value: str = Field(default="")


@pytest.mark.asyncio
async def test_invoke_structured_returns_pydantic_instance():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=_SampleOut(value="ok"))
    model = MagicMock()
    model.with_structured_output.return_value = structured

    result = await invoke_structured(
        "fill the value",
        _SampleOut,
        model=model,
    )

    assert isinstance(result, _SampleOut)
    assert result.value == "ok"
    model.with_structured_output.assert_called()
    call_kwargs = model.with_structured_output.call_args
    # Prefer json_schema when the binding accepts method=
    assert call_kwargs.args[0] is _SampleOut


@pytest.mark.asyncio
async def test_invoke_structured_retries_once_then_raises():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=[RuntimeError("boom"), RuntimeError("boom2")])
    model = MagicMock()
    model.with_structured_output.return_value = structured

    with pytest.raises(RuntimeError, match="boom2"):
        await invoke_structured("x", _SampleOut, model=model)

    assert structured.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_invoke_structured_coerces_dict_to_pydantic():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value={"value": "from-dict"})
    model = MagicMock()
    model.with_structured_output.return_value = structured

    result = await invoke_structured("x", _SampleOut, model=model)
    assert result.value == "from-dict"


def test_with_structured_output_bound_falls_back_without_method():
    model = MagicMock()
    calls: list[tuple] = []

    def bind(schema, **kwargs):
        calls.append((schema, kwargs))
        if "method" in kwargs:
            raise TypeError("no method")
        return "bound-ok"

    model.with_structured_output.side_effect = bind
    assert with_structured_output_bound(model, _SampleOut) == "bound-ok"
    assert len(calls) == 2
    assert calls[0][1].get("method") == "json_schema"
    assert "method" not in calls[1][1]


def test_knowledge_prompts_omit_format_instructions_and_json_schema_dumps():
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts" / "knowledge"
    for path in sorted(prompts_dir.glob("*.jinja")):
        text = path.read_text(encoding="utf-8")
        assert "format_instructions" not in text, path.name
        assert "Output JSON only" not in text, path.name
        assert "```json" not in text, path.name
        assert '{"type"' not in text, path.name


def test_schema_autofill_prompt_omits_embedded_schema():
    path = (
        Path(__file__).resolve().parents[1] / "prompts" / "tools" / "schema_autofill.jinja"
    )
    text = path.read_text(encoding="utf-8")
    assert "schema_json" not in text
    assert "Output JSON only" not in text
    assert "# JSON SCHEMA" not in text


def test_extraction_payload_metadata_is_string_map():
    payload = ExtractionPayload(
        entities=[{"label": "AHU-1", "type": "Topic", "metadata": {"seed": "title"}}]
    )
    assert payload.entities[0].metadata == {"seed": "title"}
