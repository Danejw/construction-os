"""Parse and invoke helpers for knowledge extractors."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ai_prompter import Prompter
from loguru import logger

from construction_os.ai.structured import invoke_structured
from construction_os.domain.knowledge_graph import normalize_entity_key
from construction_os.knowledge.extractors.base import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedMention,
    ExtractedRelation,
    ExtractionPayload,
)
from construction_os.utils import clean_thinking_content

WINDOW_SIZE = 8000
WINDOW_OVERLAP = 500
MAX_WINDOWS = 3

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> str:
    """Pull a JSON object string from model output (fenced or bare).

    Kept for unit tests and non-LLM callers; live extraction uses structured outputs.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("parse_failed: empty model response")

    fence = _JSON_FENCE_RE.search(text)
    if fence:
        return fence.group(1).strip()

    # Prefer outermost object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]

    match = _JSON_OBJECT_RE.search(text)
    if match:
        return match.group(0)

    raise ValueError("parse_failed: no JSON object found in model response")


def parse_extraction_payload(raw: str) -> ExtractionPayload:
    """Parse model text into ExtractionPayload; raises ValueError on failure.

    Kept for unit tests; live extraction uses API structured outputs.
    """
    cleaned = clean_thinking_content(raw)
    json_str = extract_json_object(cleaned)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"parse_failed: invalid JSON ({e})") from e

    try:
        return ExtractionPayload.model_validate(data)
    except Exception as e:
        raise ValueError(f"parse_failed: schema validation ({e})") from e


def split_text_windows(
    text: str,
    *,
    window_size: int = WINDOW_SIZE,
    overlap: int = WINDOW_OVERLAP,
    max_windows: int = MAX_WINDOWS,
) -> List[str]:
    """Split text into overlapping windows (capped)."""
    content = text or ""
    if not content.strip():
        return []
    if len(content) <= window_size:
        return [content]

    windows: List[str] = []
    step = max(1, window_size - overlap)
    start = 0
    while start < len(content) and len(windows) < max_windows:
        end = min(len(content), start + window_size)
        windows.append(content[start:end])
        if end >= len(content):
            break
        start += step
    return windows


def merge_extraction_payloads(payloads: List[ExtractionPayload]) -> ExtractionPayload:
    """Merge window payloads with simple dedupe."""
    entities: List[ExtractedEntity] = []
    entity_keys: set[str] = set()
    mentions: List[ExtractedMention] = []
    mention_keys: set[str] = set()
    claims: List[ExtractedClaim] = []
    claim_keys: set[str] = set()
    relations: List[ExtractedRelation] = []
    relation_keys: set[str] = set()

    for payload in payloads:
        for ent in payload.entities:
            key = f"{ent.type}:{normalize_entity_key(ent.label)}"
            if key in entity_keys:
                continue
            entity_keys.add(key)
            entities.append(ent)

        for mention in payload.mentions:
            key = (
                f"{mention.entity_type_hint}:{normalize_entity_key(mention.text)}:"
                f"{mention.chunk_index}"
            )
            if key in mention_keys:
                continue
            mention_keys.add(key)
            mentions.append(mention)

        for claim in payload.claims:
            key = (
                f"{normalize_entity_key(claim.subject_label)}|{claim.predicate}|"
                f"{normalize_entity_key(claim.object_label or '')}|"
                f"{(claim.object_literal or '').strip().lower()}"
            )
            if key in claim_keys:
                continue
            claim_keys.add(key)
            claims.append(claim)

        for relation in payload.relations:
            key = (
                f"{relation.type}|"
                f"{normalize_entity_key(relation.from_label)}|"
                f"{normalize_entity_key(relation.to_label)}"
            )
            if key in relation_keys:
                continue
            relation_keys.add(key)
            relations.append(relation)

    return ExtractionPayload(
        entities=entities,
        mentions=mentions,
        claims=claims,
        relations=relations,
    )


def payload_stats(payload: ExtractionPayload) -> Dict[str, int]:
    return {
        "entities": len(payload.entities),
        "mentions": len(payload.mentions),
        "claims": len(payload.claims),
        "relations": len(payload.relations),
    }


def extraction_is_empty(payload: ExtractionPayload) -> bool:
    return (
        len(payload.entities) == 0
        and len(payload.claims) == 0
        and len(payload.relations) == 0
    )


def extraction_missing_expected_relations(
    payload: ExtractionPayload,
    text: str,
    extractor_id: str,
) -> Optional[str]:
    """
    Return an error message when drawing/spec text has callouts but no relations.

    Soft cases (entities without callouts) return None; callers may still warn.
    """
    from construction_os.knowledge.extractors.crossrefs import count_detected_callouts

    if extractor_id not in ("drawing", "spec"):
        return None
    if len(payload.relations) > 0:
        return None
    if count_detected_callouts(text or "") <= 0:
        return None
    return (
        "expected_relations_missing: document contains cross-reference callouts "
        "but extraction produced zero relations"
    )


def relations_warning_stats(
    payload: ExtractionPayload,
) -> Optional[str]:
    """Warn when many entities exist but no relations were extracted."""
    if len(payload.entities) >= 3 and len(payload.relations) == 0:
        return "entities_without_relations"
    return None


def stats_have_graph_content(stats: Optional[Dict[str, Any]]) -> bool:
    if not stats:
        return False
    return (
        int(stats.get("entities") or 0)
        + int(stats.get("claims") or 0)
        + int(stats.get("relations") or 0)
    ) > 0


async def invoke_extractor_llm(
    *,
    prompt_template: str,
    text: str,
    source_id: str,
    project_id: str,
    chunk_count: int = 0,
    extractor: Optional[str] = None,
    max_tokens: int = 4000,
) -> ExtractionPayload:
    """Render prompt and extract via API structured outputs."""
    data: Dict[str, Any] = {
        "text": text,
        "chunk_count": chunk_count,
        "source_id": source_id,
        "project_id": project_id,
    }
    if extractor:
        data["extractor"] = extractor

    prompt = Prompter(prompt_template=prompt_template).render(data=data)
    try:
        return await invoke_structured(
            prompt,
            ExtractionPayload,
            default_type="tools",
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise ValueError(f"structured_extract_failed: {exc}") from exc


async def extract_with_windows(
    *,
    prompt_template: str,
    full_text: str,
    source_id: str,
    project_id: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
    extractor: Optional[str] = None,
) -> ExtractionPayload:
    """Run windowed extraction and merge results. Raises on total failure."""
    chunks = chunks or []
    windows = split_text_windows(full_text)
    if not windows:
        raise ValueError("no_text: Source has no text content to extract")

    payloads: List[ExtractionPayload] = []
    last_error: Optional[Exception] = None
    for idx, window in enumerate(windows):
        try:
            payload = await invoke_extractor_llm(
                prompt_template=prompt_template,
                text=window,
                source_id=source_id,
                project_id=project_id,
                chunk_count=len(chunks),
                extractor=extractor,
            )
            payloads.append(payload)
        except ValueError as e:
            last_error = e
            logger.warning(
                "KG window {}/{} failed for {}: {}",
                idx + 1,
                len(windows),
                extractor or prompt_template,
                e,
            )

    if not payloads:
        raise ValueError(
            str(last_error)
            if last_error
            else "parse_failed: all extraction windows failed"
        )

    return merge_extraction_payloads(payloads)
