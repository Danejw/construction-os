"""Shared API-level structured output helper (no schema-in-prompt)."""

from __future__ import annotations

from typing import Any, Optional, Sequence, Type, TypeVar, Union, cast, overload

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel

from construction_os.ai.provision import provision_langchain_model

T = TypeVar("T", bound=BaseModel)
StructuredSchema = Union[Type[BaseModel], dict[str, Any]]
MessageInput = Union[str, Sequence[BaseMessage]]


def _content_for_provision(messages: MessageInput) -> str:
    if isinstance(messages, str):
        return messages
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def with_structured_output_bound(model: BaseChatModel, schema: StructuredSchema) -> Any:
    """Bind structured output preferring provider json_schema when supported."""
    bind = model.with_structured_output
    try:
        return bind(schema, method="json_schema")
    except TypeError:
        return bind(schema)


def _coerce_result(result: Any, schema: StructuredSchema) -> Any:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        if isinstance(result, schema):
            return result
        if isinstance(result, BaseModel):
            return schema.model_validate(result.model_dump())
        if isinstance(result, dict):
            return schema.model_validate(result)
        return schema.model_validate(result)

    if isinstance(result, BaseModel):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    raise TypeError(
        f"Structured output expected a dict for JSON Schema, got {type(result).__name__}"
    )


@overload
async def invoke_structured(
    messages: MessageInput,
    schema: Type[T],
    *,
    model: Optional[BaseChatModel] = None,
    model_id: Optional[str] = None,
    default_type: str = "tools",
    max_tokens: Optional[int] = None,
    config: Optional[RunnableConfig] = None,
    **provision_kwargs: Any,
) -> T: ...


@overload
async def invoke_structured(
    messages: MessageInput,
    schema: dict[str, Any],
    *,
    model: Optional[BaseChatModel] = None,
    model_id: Optional[str] = None,
    default_type: str = "tools",
    max_tokens: Optional[int] = None,
    config: Optional[RunnableConfig] = None,
    **provision_kwargs: Any,
) -> dict[str, Any]: ...


async def invoke_structured(
    messages: MessageInput,
    schema: StructuredSchema,
    *,
    model: Optional[BaseChatModel] = None,
    model_id: Optional[str] = None,
    default_type: str = "tools",
    max_tokens: Optional[int] = None,
    config: Optional[RunnableConfig] = None,
    **provision_kwargs: Any,
) -> Any:
    """Provision (optional) and invoke via API structured outputs.

    Does not paste schemas into prompts or ask the model to "return JSON".
    On failure, retries the structured call once, then raises.
    """
    chat_model = model
    if chat_model is None:
        provision_args: dict[str, Any] = dict(provision_kwargs)
        if max_tokens is not None:
            provision_args["max_tokens"] = max_tokens
        chat_model = await provision_langchain_model(
            _content_for_provision(messages),
            model_id,
            default_type,
            **provision_args,
        )

    structured = with_structured_output_bound(chat_model, schema)

    async def _once() -> Any:
        if config is None:
            return await structured.ainvoke(messages)
        return await structured.ainvoke(messages, config=config)

    try:
        result = await _once()
    except Exception as first_error:
        logger.warning(
            "Structured output call failed ({}); retrying once",
            first_error,
        )
        try:
            result = await _once()
        except Exception as second_error:
            raise second_error from first_error

    return cast(Any, _coerce_result(result, schema))
