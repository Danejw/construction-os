"""Deterministic entity bootstrap when LLM returns empty or sparse graphs.

Seeds Reference/Topic entities from construction drawing structure and source
metadata so non-empty text never yields a zero-entity graph when meaningful
tokens exist (sheet IDs, equipment tags, room labels, headings, titles).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from construction_os.knowledge.extractors.base import (
    ExtractedEntity,
    ExtractionPayload,
)

_BOOTSTRAP_CONFIDENCE = 0.75

# Sheet IDs with construction discipline prefixes (hyphen optional)
_SHEET_DISC = (
    r"(?:FP|FA|FS|EL|PL|ME|ID|AV|LA|IR|A|S|M|E|P|C|L|T|G|H|D|W|N|K)"
)
_SHEET_ID_RE = re.compile(
    rf"\b(?P<sheet>{_SHEET_DISC}(?:-\d{{2,4}}|\d{{2,4}}))\b"
)

# Equipment / asset tags
_EQUIP_RE = re.compile(
    r"\b(?P<tag>(?:AHU|FCU|VAV|EF|SF|RF|RTU|MAU|DOAS|WSHP|CUH|UH|"
    r"EQ|TAG|WH|HW|CW|FD|CO|EF)\s*-?\s*\d{1,4}[A-Z]?)\b",
    re.IGNORECASE,
)

# Room numbers: Room 201, R-201, RM 108
_ROOM_RE = re.compile(
    r"\b(?:ROOM|RM|R)\s*-?\s*(?P<room>\d{2,4}[A-Z]?)\b",
    re.IGNORECASE,
)

# YAML / frontmatter sheet: P001
_FRONTMATTER_SHEET_RE = re.compile(
    rf"(?im)^\s*sheet\s*:\s*[\"']?(?P<sheet>{_SHEET_DISC}-?\d{{2,4}})[\"']?\s*$"
)

# Markdown headings
_HEADING_RE = re.compile(r"(?m)^#{1,3}\s+(?P<h>.+?)\s*$")

# Sheet index table rows: | P201 | TITLE |
_INDEX_ROW_RE = re.compile(
    rf"(?im)^\s*\|\s*(?P<sheet>{_SHEET_DISC}-?\d{{2,4}})\s*\|\s*(?P<title>[^|\n]{{3,80}})\|"
)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "sheet",
        "page",
        "plan",
        "notes",
        "general",
        "source",
        "file",
        "pdf",
        "extracted",
        "document",
        "type",
        "project",
        "name",
        "address",
        "date",
        "none",
        "true",
        "false",
        "null",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")


def _add_entity(
    entities: List[ExtractedEntity],
    keys: Set[str],
    label: str,
    entity_type: str,
    *,
    metadata: Optional[Dict[str, str]] = None,
) -> None:
    canon = re.sub(r"\s+", " ", (label or "").strip())
    if not canon or len(canon) < 2:
        return
    key = f"{entity_type}:{canon.lower()}"
    if key in keys:
        return
    keys.add(key)
    entities.append(
        ExtractedEntity(
            label=canon,
            type=entity_type,
            metadata={
                "extraction_method": "bootstrap",
                **(metadata or {}),
            },
        )
    )


def _title_tokens(title: str) -> List[str]:
    parts = re.split(r"[_\-\s./]+", title or "")
    out: List[str] = []
    for part in parts:
        cleaned = part.strip()
        if len(cleaned) < 3:
            continue
        if cleaned.lower() in _STOPWORDS:
            continue
        if cleaned.isdigit():
            continue
        out.append(cleaned)
    return out


def _filename_stem(file_path: Optional[str]) -> str:
    if not file_path:
        return ""
    try:
        return Path(str(file_path).replace("\\", "/")).stem
    except Exception:
        return str(file_path)


def bootstrap_entities(
    text: str,
    *,
    title: Optional[str] = None,
    file_path: Optional[str] = None,
    topics: Optional[Sequence[str]] = None,
    max_keyword_entities: int = 8,
) -> ExtractionPayload:
    """Extract grounded entities from text + source metadata without an LLM."""
    content = text or ""
    entities: List[ExtractedEntity] = []
    keys: Set[str] = set()

    # Metadata seeds — always, even if body is weak OCR
    if title:
        _add_entity(
            entities,
            keys,
            title,
            "Reference",
            metadata={"seed": "title"},
        )
        for tok in _title_tokens(title):
            # Prefer sheet-like tokens as Reference
            if _SHEET_ID_RE.fullmatch(tok.upper().replace("_", "")) or re.fullmatch(
                r"[A-Z]-?\d{2,4}", tok.upper()
            ):
                _add_entity(entities, keys, tok.upper().replace("_", ""), "Reference")
            elif tok[0].isupper() or len(tok) >= 4:
                _add_entity(entities, keys, tok.replace("_", " "), "Topic")

    stem = _filename_stem(file_path)
    if stem and stem != (title or ""):
        _add_entity(
            entities,
            keys,
            stem,
            "Reference",
            metadata={"seed": "filename"},
        )
        for tok in _title_tokens(stem):
            if re.fullmatch(r"[A-Za-z]-?\d{2,4}", tok, re.IGNORECASE):
                _add_entity(
                    entities, keys, tok.upper().replace("_", ""), "Reference"
                )

    for topic in topics or []:
        if topic and str(topic).strip():
            _add_entity(
                entities,
                keys,
                str(topic).strip(),
                "Topic",
                metadata={"seed": "topic"},
            )

    if not content.strip() and entities:
        return ExtractionPayload(entities=entities)

    for m in _FRONTMATTER_SHEET_RE.finditer(content):
        _add_entity(entities, keys, m.group("sheet").upper(), "Reference")

    for m in _INDEX_ROW_RE.finditer(content):
        sheet = m.group("sheet").upper()
        _add_entity(entities, keys, sheet, "Reference")
        title_cell = (m.group("title") or "").strip()
        if title_cell and title_cell.lower() not in ("title", "sheet", "---"):
            # Keep sheet entity; optionally note title as Topic if distinctive
            if len(title_cell) >= 8 and not title_cell.startswith("-"):
                _add_entity(
                    entities,
                    keys,
                    title_cell.title() if title_cell.isupper() else title_cell,
                    "Topic",
                    metadata={"sheet": sheet, "seed": "sheet_index"},
                )

    for m in _SHEET_ID_RE.finditer(content.upper()):
        sheet = m.group("sheet")
        # Skip lone letters / noise like "A" from OCR keyboards — already require digits
        _add_entity(entities, keys, sheet, "Reference")

    for m in _EQUIP_RE.finditer(content):
        raw = re.sub(r"\s+", "", m.group("tag")).upper()
        tag = re.sub(r"^([A-Z]+)[-]?(\d)", r"\1-\2", raw)
        _add_entity(entities, keys, tag, "Topic", metadata={"kind": "equipment"})

    for m in _ROOM_RE.finditer(content):
        room = f"Room {m.group('room')}"
        _add_entity(entities, keys, room, "Location")

    for m in _HEADING_RE.finditer(content):
        heading = m.group("h").strip()
        # Skip very long headings / frontmatter noise
        if 4 <= len(heading) <= 80 and not heading.startswith("---"):
            # Prefer sheet mentions inside headings
            sheet_in_h = _SHEET_ID_RE.search(heading.upper())
            if sheet_in_h:
                _add_entity(entities, keys, sheet_in_h.group("sheet"), "Reference")
            else:
                _add_entity(entities, keys, heading, "Topic", metadata={"seed": "heading"})

    # Top keywords from body when still sparse
    if len(entities) < 3 and content.strip():
        tokens = [
            t.lower()
            for t in _TOKEN_RE.findall(content)
            if t.lower() not in _STOPWORDS and not t.isdigit()
        ]
        for word, _count in Counter(tokens).most_common(max_keyword_entities):
            if len(word) < 4:
                continue
            label = word.upper() if word.isupper() else word.capitalize()
            _add_entity(
                entities,
                keys,
                label,
                "Topic",
                metadata={"seed": "keyword"},
            )

    return ExtractionPayload(entities=entities)


def merge_bootstrap(
    llm_payload: ExtractionPayload,
    text: str,
    *,
    title: Optional[str] = None,
    file_path: Optional[str] = None,
    topics: Optional[Iterable[str]] = None,
) -> ExtractionPayload:
    """Merge LLM payload with bootstrap entities (bootstrap first for stable labels)."""
    from construction_os.knowledge.extractors.parse import merge_extraction_payloads

    boot = bootstrap_entities(
        text or "",
        title=title,
        file_path=file_path,
        topics=list(topics) if topics else None,
    )
    return merge_extraction_payloads([boot, llm_payload])
