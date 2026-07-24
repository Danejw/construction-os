"""Fill arbitrary JSON Schema fields from uploaded file content via LLM."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ai_prompter import Prompter
from content_core import extract_content
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError as JsonSchemaValidationError
from loguru import logger

from construction_os.ai.structured import invoke_structured
from construction_os.domain.content_settings import ContentSettings
from construction_os.exceptions import InvalidInputError
from construction_os.knowledge.extractors.parse import split_text_windows
from construction_os.utils.error_classifier import classify_error

MAX_COMBINED_CHARS = 24_000


def _validate_schema(schema: Dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        raise InvalidInputError("schema must be a JSON object")
    if schema.get("type") not in (None, "object"):
        raise InvalidInputError("schema type must be object (or omitted)")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise InvalidInputError(f"Invalid JSON Schema: {exc.message}") from exc


def _validate_data(data: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise InvalidInputError("Model output must be a JSON object")
    try:
        Draft202012Validator(schema).validate(data)
    except JsonSchemaValidationError as exc:
        raise InvalidInputError(
            f"Filled data does not match schema: {exc.message}"
        ) from exc
    return data


async def _extract_file_text(file_path: str) -> str:
    content_settings = await ContentSettings.get_instance()
    content_state: Dict[str, Any] = {
        "file_path": file_path,
        "url_engine": content_settings.default_content_processing_engine_url or "auto",
        "document_engine": content_settings.default_content_processing_engine_doc
        or "auto",
        "output_format": "markdown",
    }
    processed = await extract_content(content_state)
    if processed.title == "Error" and (processed.content or "").startswith(
        "Failed to extract content:"
    ):
        raise InvalidInputError(
            "Could not extract content from this file. "
            "It may be unreachable, invalid, or unsupported."
        )
    text = (processed.content or "").strip()
    if not text:
        raise InvalidInputError(
            "Could not extract any text from this file. "
            "It may be empty or in an unsupported format."
        )
    return text


def _combine_texts(file_texts: Sequence[Tuple[str, str]]) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    parts: List[str] = []
    total = 0
    for filename, text in file_texts:
        header = f"# FILE: {filename}\n\n"
        chunk = header + text
        if total + len(chunk) > MAX_COMBINED_CHARS:
            remaining = MAX_COMBINED_CHARS - total
            if remaining > 200:
                parts.append(chunk[:remaining])
                warnings.append(
                    f"Truncated content from {filename} to fit model context."
                )
            else:
                warnings.append(f"Skipped remaining content from {filename}.")
            warnings.append(
                "Document text was truncated; some details may be missing from the fill."
            )
            break
        parts.append(chunk)
        total += len(chunk)

    combined = "\n\n---\n\n".join(parts)
    if len(combined) > MAX_COMBINED_CHARS:
        windows = split_text_windows(combined, window_size=MAX_COMBINED_CHARS, max_windows=1)
        combined = windows[0] if windows else combined[:MAX_COMBINED_CHARS]
        warnings.append("Combined text was windowed for the model.")
    return combined, warnings


async def _invoke_fill_llm(
    *,
    text: str,
    schema: Dict[str, Any],
    instructions: Optional[str],
    model_id: Optional[str],
) -> Dict[str, Any]:
    prompt = Prompter(prompt_template="tools/schema_autofill").render(
        data={
            "text": text,
            "instructions": (instructions or "").strip() or None,
        }
    )
    try:
        payload = await invoke_structured(
            prompt,
            schema,
            model_id=model_id,
            default_type="tools",
            max_tokens=4000,
        )
    except Exception as exc:
        raise InvalidInputError(f"Structured autofill failed: {exc}") from exc
    return _validate_data(payload, schema)


async def autofill_from_files(
    *,
    file_paths: Sequence[Tuple[str, str]],
    schema: Dict[str, Any],
    instructions: Optional[str] = None,
    model_id: Optional[str] = None,
    cleanup_files: bool = True,
) -> Dict[str, Any]:
    """Extract text from files and fill a caller-supplied JSON Schema.

    ``file_paths`` is a sequence of ``(filename, absolute_path)``.
    """

    _validate_schema(schema)
    if not file_paths:
        raise InvalidInputError("At least one file is required")

    file_texts: List[Tuple[str, str]] = []
    file_meta: List[Dict[str, Any]] = []
    warnings: List[str] = []

    try:
        for filename, path in file_paths:
            try:
                text = await _extract_file_text(path)
            except InvalidInputError as exc:
                warnings.append(f"{filename}: {exc}")
                continue
            file_texts.append((filename, text))
            file_meta.append({"filename": filename, "chars": len(text)})

        if not file_texts:
            raise InvalidInputError(
                "No extractable text found in the uploaded file(s)."
            )

        combined, truncate_warnings = _combine_texts(file_texts)
        warnings.extend(truncate_warnings)

        try:
            data = await _invoke_fill_llm(
                text=combined,
                schema=schema,
                instructions=instructions,
                model_id=model_id,
            )
        except InvalidInputError:
            raise
        except Exception as exc:
            exc_class, message = classify_error(exc)
            raise exc_class(message) from exc

        return {
            "data": data,
            "extracted_chars": len(combined),
            "files": file_meta,
            "warnings": warnings,
        }
    finally:
        if cleanup_files:
            for _filename, path in file_paths:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except OSError as cleanup_error:
                    logger.warning(
                        "Failed to delete temp autofill upload {}: {}",
                        path,
                        cleanup_error,
                    )
