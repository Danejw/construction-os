"""Runtime contracts and deterministic rendering for user HTML templates."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger

from construction_os.ai.structured import invoke_structured
from construction_os.domain.html_document import HtmlTemplate
from construction_os.utils.html_media import expand_image_tokens
from construction_os.utils.text_utils import extract_text_content

_PLACEHOLDER_RE = re.compile(
    r"{{\s*(?!image\s*:)(?P<target>[A-Za-z][A-Za-z0-9_.:-]*)\s*}}",
    re.IGNORECASE,
)
_EXPLICIT_ELEMENT_RE = re.compile(
    r"""
    <(?P<tag>[A-Za-z][\w:-]*)
    (?P<attrs>
        [^>]*?
        \b(?P<attr>data-cos-field|data-bind|data-field|data-template-field)
        \s*=\s*
        (?P<quote>["'])
        (?P<target>[^"']+)
        (?P=quote)
        [^>]*
    )
    >
    (?P<content>[\s\S]*?)
    </(?P=tag)\s*>
    """,
    re.IGNORECASE | re.VERBOSE,
)
_SPAN_RE = re.compile(
    r"<span\b(?P<attrs>[^>]*)>(?P<content>[\s\S]*?)</span\s*>",
    re.IGNORECASE,
)
_LEAF_RE = re.compile(
    r"<(?P<tag>h[1-6]|p|td|th|li|label|strong|em|small|div)\b"
    r"(?P<attrs>[^>]*)>(?P<content>[^<>]*)</(?P=tag)\s*>",
    re.IGNORECASE,
)
_HTML_FENCE_RE = re.compile(r"```html\s*[\s\S]*?```", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

_MAX_GROUNDING_CHARS = 60_000
_MAX_ASSISTANT_CHARS = 24_000
_SCHEMA_BATCH_SIZE = 40


@dataclass(frozen=True)
class HtmlTemplateSlot:
    """One text value that can be bound into an uploaded HTML template."""

    slot_id: str
    kind: str
    target: str
    current_value: str
    context_hint: str


@dataclass(frozen=True)
class HtmlTemplateContract:
    """Runtime contract derived from HTML that was unknown at build time."""

    html_body: str
    slots: tuple[HtmlTemplateSlot, ...]


def _plain_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value or "")
    return _SPACE_RE.sub(" ", html.unescape(without_tags)).strip()


def _context_hint(html_body: str, start: int, end: int) -> str:
    snippet = html_body[max(0, start - 180) : min(len(html_body), end + 180)]
    return _plain_text(snippet)[:320]


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(
        start < occupied_end and end > occupied_start
        for occupied_start, occupied_end in occupied
    )


def compile_html_template_contract(html_body: str) -> HtmlTemplateContract:
    """
    Derive a runtime slot contract without knowing the user's HTML beforehand.

    Precedence is explicit data attributes, named ``{{placeholders}}``, plain
    ``span`` elements, then leaf text elements as a compatibility fallback.
    """
    body = html_body or ""
    slots: list[HtmlTemplateSlot] = []
    occupied: list[tuple[int, int]] = []
    seen_semantic_targets: set[tuple[str, str]] = set()

    def add_slot(
        *,
        kind: str,
        target: str,
        current_value: str,
        start: int,
        end: int,
        dedupe_semantic: bool = False,
    ) -> None:
        semantic_key = (kind, target)
        occupied.append((start, end))
        if dedupe_semantic and semantic_key in seen_semantic_targets:
            return
        seen_semantic_targets.add(semantic_key)
        slots.append(
            HtmlTemplateSlot(
                slot_id=f"slot_{len(slots) + 1:03d}",
                kind=kind,
                target=target,
                current_value=_plain_text(current_value),
                context_hint=_context_hint(body, start, end),
            )
        )

    for match in _EXPLICIT_ELEMENT_RE.finditer(body):
        add_slot(
            kind="element",
            target=match.group("target").strip(),
            current_value=match.group("content"),
            start=match.start(),
            end=match.end(),
            dedupe_semantic=True,
        )

    for match in _PLACEHOLDER_RE.finditer(body):
        if _overlaps(match.start(), match.end(), occupied):
            continue
        add_slot(
            kind="placeholder",
            target=match.group("target").strip(),
            current_value="",
            start=match.start(),
            end=match.end(),
            dedupe_semantic=True,
        )

    span_index = 0
    for match in _SPAN_RE.finditer(body):
        span_index += 1
        if _overlaps(match.start(), match.end(), occupied):
            continue
        # Avoid flattening nested markup that the user intentionally designed.
        if "<" in match.group("content"):
            continue
        add_slot(
            kind="span",
            target=str(span_index),
            current_value=match.group("content"),
            start=match.start(),
            end=match.end(),
        )

    leaf_index = 0
    for match in _LEAF_RE.finditer(body):
        leaf_index += 1
        if _overlaps(match.start(), match.end(), occupied):
            continue
        current = _plain_text(match.group("content"))
        if not current:
            continue
        add_slot(
            kind="leaf",
            target=str(leaf_index),
            current_value=current,
            start=match.start(),
            end=match.end(),
        )

    return HtmlTemplateContract(html_body=body, slots=tuple(slots))


def _schema_for_slots(
    slots: Iterable[HtmlTemplateSlot], batch_index: int
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for slot in slots:
        existing = slot.current_value or "(empty)"
        hint = slot.context_hint or "(no nearby text)"
        properties[slot.slot_id] = {
            "type": "string",
            "description": (
                f"Text for template field '{slot.target}' ({slot.kind}). "
                f"Existing value: {existing!r}. Nearby template text: {hint!r}. "
                "Preserve static labels; use grounded content or TBD when unknown."
            ),
        }
        required.append(slot.slot_id)
    return {
        "title": f"HtmlTemplateBindingsBatch{batch_index}",
        "description": "Validated text bindings for one user-uploaded HTML template.",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _clip(value: str, limit: int) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    head = int(limit * 0.75)
    tail = limit - head
    return f"{text[:head]}\n\n[content clipped]\n\n{text[-tail:]}"


def _messages_to_grounding(messages: list[BaseMessage]) -> str:
    parts: list[str] = []
    for message in messages:
        role = getattr(message, "type", message.__class__.__name__)
        content = extract_text_content(getattr(message, "content", ""))
        if content:
            parts.append(f"[{role}]\n{content}")
    return _clip("\n\n".join(parts), _MAX_GROUNDING_CHARS)


async def _generate_binding_batch(
    *,
    model: Any,
    slots: list[HtmlTemplateSlot],
    grounding: str,
    assistant_text: str,
    config: Optional[RunnableConfig],
    batch_index: int,
) -> dict[str, Any]:
    schema = _schema_for_slots(slots, batch_index)
    slot_manifest = [
        {
            "slot_id": slot.slot_id,
            "field": slot.target,
            "kind": slot.kind,
            "existing_value": slot.current_value,
            "nearby_text": slot.context_hint,
        }
        for slot in slots
    ]
    messages: list[BaseMessage] = [
        SystemMessage(
            content=(
                "You fill an arbitrary user-uploaded HTML document through a strict "
                "runtime schema. Provide text values for the requested slots. "
                "Use the assistant result and grounding context as the source of truth. "
                "Do not return HTML. Preserve headings, labels, legal boilerplate, and "
                "other static copy when they are not data fields. Never invent facts. "
                "Use TBD for an empty field when the required value is unavailable."
            )
        ),
        HumanMessage(
            content=(
                "GROUNDING CONTEXT\n"
                f"{grounding}\n\n"
                "CANONICAL ASSISTANT RESULT\n"
                f"{_clip(assistant_text, _MAX_ASSISTANT_CHARS)}\n\n"
                "TEMPLATE SLOT MANIFEST\n"
                f"{json.dumps(slot_manifest, ensure_ascii=False, indent=2)}"
            )
        ),
    ]

    return await invoke_structured(
        messages,
        schema,
        model=model,
        config=config,
    )


def _normalized_bindings(
    contract: HtmlTemplateContract,
    generated: dict[str, Any],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for slot in contract.slots:
        raw = generated.get(slot.slot_id)
        if raw is None or not str(raw).strip():
            normalized[slot.slot_id] = slot.current_value or "TBD"
        else:
            normalized[slot.slot_id] = str(raw).strip()
    return normalized


def apply_html_template_bindings(
    contract: HtmlTemplateContract,
    bindings: dict[str, str],
) -> str:
    """Apply validated text bindings while retaining the uploaded HTML structure."""
    value_by_semantic: dict[tuple[str, str], str] = {}
    value_by_occurrence: dict[tuple[str, int], str] = {}
    for slot in contract.slots:
        value = html.escape(
            bindings.get(slot.slot_id, slot.current_value or "TBD"), quote=True
        )
        if slot.kind in {"placeholder", "element"}:
            value_by_semantic[(slot.kind, slot.target)] = value
        else:
            value_by_occurrence[(slot.kind, int(slot.target))] = value

    rendered = contract.html_body
    leaf_index = 0

    def replace_leaf(match: re.Match[str]) -> str:
        nonlocal leaf_index
        leaf_index += 1
        value = value_by_occurrence.get(("leaf", leaf_index))
        if value is None:
            return match.group(0)
        tag = match.group("tag")
        return f"<{tag}{match.group('attrs')}>{value}</{tag}>"

    rendered = _LEAF_RE.sub(replace_leaf, rendered)

    span_index = 0

    def replace_span(match: re.Match[str]) -> str:
        nonlocal span_index
        span_index += 1
        value = value_by_occurrence.get(("span", span_index))
        if value is None:
            return match.group(0)
        return f"<span{match.group('attrs')}>{value}</span>"

    rendered = _SPAN_RE.sub(replace_span, rendered)

    def replace_explicit(match: re.Match[str]) -> str:
        value = value_by_semantic.get(("element", match.group("target").strip()))
        if value is None:
            return match.group(0)
        return (
            f"<{match.group('tag')}{match.group('attrs')}>"
            f"{value}</{match.group('tag')}>"
        )

    rendered = _EXPLICIT_ELEMENT_RE.sub(replace_explicit, rendered)
    return _PLACEHOLDER_RE.sub(
        lambda match: value_by_semantic.get(
            ("placeholder", match.group("target").strip()),
            match.group(0),
        ),
        rendered,
    )


async def render_selected_html_template(
    *,
    template_id: str,
    assistant_text: str,
    grounding_messages: list[BaseMessage],
    model_id: Optional[str],
    provision_model: Callable[..., Any],
    config: Optional[RunnableConfig] = None,
) -> str:
    """
    Fill a selected user template in parallel with the normal assistant/A2UI turn.

    The primary model produces canonical domain content. This second constrained
    pass produces only slot values, then the server applies them to the original
    HTML. A failure preserves the exact uploaded template instead of dropping it.
    """
    template = await HtmlTemplate.get(template_id)
    html_body = await expand_image_tokens(template.html_body)
    contract = compile_html_template_contract(html_body)
    if not contract.slots:
        return html_body

    grounding = _messages_to_grounding(grounding_messages)
    model = await provision_model(
        f"{grounding}\n{assistant_text}",
        model_id,
        "chat",
        max_tokens=8192,
    )

    generated: dict[str, Any] = {}
    try:
        for offset in range(0, len(contract.slots), _SCHEMA_BATCH_SIZE):
            batch = list(contract.slots[offset : offset + _SCHEMA_BATCH_SIZE])
            batch_result = await _generate_binding_batch(
                model=model,
                slots=batch,
                grounding=grounding,
                assistant_text=assistant_text,
                config=config,
                batch_index=(offset // _SCHEMA_BATCH_SIZE) + 1,
            )
            generated.update(batch_result)
    except Exception as error:
        logger.error(
            "HTML template binding failed for {}. Preserving original template: {}",
            template_id,
            error,
        )

    return apply_html_template_bindings(
        contract,
        _normalized_bindings(contract, generated),
    )


def attach_rendered_html(assistant_text: str, rendered_html: str) -> str:
    """Attach one completed HTML document to the assistant message for chat preview."""
    text_without_old_html = _HTML_FENCE_RE.sub("", assistant_text or "").strip()
    html_block = f"```html\n{rendered_html.strip()}\n```"
    if not text_without_old_html:
        return html_block
    return f"{text_without_old_html}\n\n{html_block}"
