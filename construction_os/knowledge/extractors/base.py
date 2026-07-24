"""Shared extraction schemas for knowledge extractors."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field


class ExtractedMention(BaseModel):
    text: str
    entity_type_hint: str = "Topic"
    confidence: float = 0.7
    chunk_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class ExtractedEntity(BaseModel):
    label: str
    type: str = "Topic"
    # str values only — free-form Dict[str, Any] breaks provider strict json_schema
    metadata: Dict[str, str] = Field(default_factory=dict)


class ExtractedClaim(BaseModel):
    subject_label: str
    subject_type: str = "Topic"
    predicate: str
    object_label: Optional[str] = None
    object_type: Optional[str] = None
    object_literal: Optional[str] = None
    confidence: float = 0.7
    chunk_index: Optional[int] = None


class ExtractedRelation(BaseModel):
    type: str
    from_label: str
    from_type: str = "Topic"
    to_label: str
    to_type: str = "Topic"
    confidence: float = 0.7
    chunk_index: Optional[int] = None


class ExtractionPayload(BaseModel):
    """Structured LLM output schema for knowledge extractors."""

    entities: List[ExtractedEntity] = Field(default_factory=list)
    mentions: List[ExtractedMention] = Field(default_factory=list)
    claims: List[ExtractedClaim] = Field(default_factory=list)
    relations: List[ExtractedRelation] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    extractor: str
    extractor_version: str
    payload: ExtractionPayload
    content_hash: str
    stats: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeExtractor(Protocol):
    id: str
    label: str
    version: str
    auto_run: bool

    async def extract(
        self,
        *,
        full_text: str,
        chunks: List[Dict[str, Any]],
        source_id: str,
        project_id: str,
        source_title: Optional[str] = None,
        file_path: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> ExtractionResult: ...
