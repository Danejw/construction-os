"""Project-scoped text and vector search helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from construction_os.database.repository import ensure_record_id, repo_query
from construction_os.exceptions import DatabaseOperationError, InvalidInputError
from construction_os.utils.embedding import generate_embedding


async def get_project_scope_ids(
    project_id: str,
) -> Tuple[set[str], set[str]]:
    """Return (source_ids, note_ids) linked to a project via graph edges."""
    project_rid = ensure_record_id(project_id)
    sources = await repo_query(
        "SELECT VALUE in FROM reference WHERE out = $project_id",
        {"project_id": project_rid},
    )
    notes = await repo_query(
        "SELECT VALUE in FROM project_note WHERE out = $project_id",
        {"project_id": project_rid},
    )
    source_ids = {str(s) for s in (sources or []) if s is not None}
    note_ids = {str(n) for n in (notes or []) if n is not None}
    return source_ids, note_ids


def filter_search_results_by_project(
    results: Optional[List[Dict[str, Any]]],
    source_ids: set[str],
    note_ids: set[str],
) -> List[Dict[str, Any]]:
    """Keep search hits that belong to the given project membership sets."""
    filtered: List[Dict[str, Any]] = []
    for result in results or []:
        rid = str(result.get("id") or "")
        parent = str(result.get("parent_id") or "")
        if rid.startswith("note:") or parent.startswith("note:"):
            if rid in note_ids or parent in note_ids:
                filtered.append(result)
            continue
        if rid in source_ids or parent in source_ids:
            filtered.append(result)
    return filtered


async def text_search(
    keyword: str,
    results: int,
    source: bool = True,
    note: bool = True,
    project_id: Optional[str] = None,
):
    if not keyword:
        raise InvalidInputError("Search keyword cannot be empty")
    try:
        fetch_limit = results
        source_ids: set[str] = set()
        note_ids: set[str] = set()
        if project_id:
            source_ids, note_ids = await get_project_scope_ids(project_id)
            # Over-fetch so project filtering still returns enough hits.
            fetch_limit = max(results * 5, 50)

        search_results = await repo_query(
            """
            select *
            from fn::text_search($keyword, $results, $source, $note)
            """,
            {
                "keyword": keyword,
                "results": fetch_limit,
                "source": source,
                "note": note,
            },
        )
        if project_id:
            search_results = filter_search_results_by_project(
                search_results, source_ids, note_ids
            )[:results]
        return search_results
    except RuntimeError as e:
        # SurrealDB's search::highlight can compute a byte position that exceeds the
        # stored string length on large or multi-byte chunks, aborting the whole query
        # ("position overflow"). Fall back to vector search so the user still gets
        # results instead of a 500. See issue #648.
        if "position overflow" in str(e):
            logger.warning(
                f"Highlight position overflow, falling back to vector search: {str(e)}"
            )
            try:
                return await vector_search(
                    keyword, results, source, note, project_id=project_id
                )
            except Exception as ve:
                # Both search paths failed (e.g. no embedding model configured).
                # Surface the failure instead of returning [] — an empty list would
                # be indistinguishable from a legitimate "no matches" and mask a
                # total search outage from callers.
                logger.error(f"Vector search fallback also failed: {str(ve)}")
                logger.exception(ve)
                raise DatabaseOperationError(ve)
        logger.error(f"Error performing text search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)
    except Exception as e:
        logger.error(f"Error performing text search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)


async def vector_search(
    keyword: str,
    results: int,
    source: bool = True,
    note: bool = True,
    minimum_score=0.2,
    project_id: Optional[str] = None,
):
    if not keyword:
        raise InvalidInputError("Search keyword cannot be empty")
    try:
        fetch_limit = results
        source_ids: set[str] = set()
        note_ids: set[str] = set()
        if project_id:
            source_ids, note_ids = await get_project_scope_ids(project_id)
            fetch_limit = max(results * 5, 50)

        embed = await generate_embedding(keyword)
        search_results = await repo_query(
            """
            SELECT * FROM fn::vector_search($embed, $results, $source, $note, $minimum_score);
            """,
            {
                "embed": embed,
                "results": fetch_limit,
                "source": source,
                "note": note,
                "minimum_score": minimum_score,
            },
        )
        if project_id:
            search_results = filter_search_results_by_project(
                search_results, source_ids, note_ids
            )[:results]
        return search_results
    except Exception as e:
        logger.error(f"Error performing vector search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)
