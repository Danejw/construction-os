"""Multimodal vision client for drawing extraction (configurable Gemini)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from loguru import logger

from construction_os.drawing.config import DrawingExtractionConfig


class VisionClient(Protocol):
    async def structured_extract(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        image_paths: list[str],
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...


class MockVisionClient:
    """Deterministic mock for unit tests — no network calls."""

    def __init__(self, responses: Optional[Dict[str, Dict[str, Any]]] = None):
        self.responses = responses or {}
        self.calls: list[Dict[str, Any]] = []

    async def structured_extract(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        image_paths: list[str],
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "prompt": prompt[:200],
                "schema_title": schema.get("title") or schema.get("name"),
                "image_paths": image_paths,
                "model": model,
                "provider": provider,
            }
        )
        key = str(schema.get("title") or schema.get("name") or "default")
        if key in self.responses:
            return self.responses[key]
        # Empty but schema-valid-ish stub
        return {"is_drawing": True, "confidence": 0.5, "items": []}


class GeminiVisionClient:
    """Gemini multimodal structured JSON via langchain-google-genai when available."""

    def __init__(self, config: DrawingExtractionConfig):
        self.config = config

    async def structured_extract(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        image_paths: list[str],
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        model_name = model or self.config.extraction_model
        provider_name = (provider or self.config.extraction_provider).lower()

        # Ensure Google key is available for langchain
        if provider_name in {"google", "gemini"} and not os.getenv("GOOGLE_API_KEY"):
            from construction_os.ai.key_provider import provision_provider_keys

            await provision_provider_keys("google")

        try:
            from langchain_core.messages import HumanMessage
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-google-genai is required for vision extraction"
            ) from exc

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
        )
        structured = llm.with_structured_output(schema)
        content_parts: list[Any] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            data = Path(path).read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": f"data:image/png;base64,{b64}",
                }
            )
        try:
            result = await structured.ainvoke(
                [HumanMessage(content=content_parts)]
            )
        except Exception as exc:
            logger.warning(
                "Structured vision call failed (model={}): {}", model_name, exc
            )
            raise RuntimeError(
                f"Structured vision extraction failed for model {model_name}: {exc}"
            ) from exc
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        raise TypeError(
            f"Structured vision output must be a dict, got {type(result).__name__}"
        )


_VISION_OVERRIDE: Optional[VisionClient] = None


def set_vision_client_override(client: Optional[VisionClient]) -> None:
    """Test hook to inject a mock vision client."""
    global _VISION_OVERRIDE
    _VISION_OVERRIDE = client


def get_vision_client(config: DrawingExtractionConfig) -> VisionClient:
    if _VISION_OVERRIDE is not None:
        return _VISION_OVERRIDE
    if not config.use_vision:
        return MockVisionClient()
    return GeminiVisionClient(config)


CLASSIFICATION_SCHEMA: Dict[str, Any] = {
    "title": "PageClassification",
    "type": "object",
    "properties": {
        "is_drawing": {"type": "boolean"},
        "discipline": {"type": "string"},
        "sheet_number": {"type": ["string", "null"]},
        "sheet_title": {"type": ["string", "null"]},
        "drawing_types": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "major_regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "region_type": {"type": "string"},
                    "bbox_norm": {
                        "type": "object",
                        "properties": {
                            "x0": {"type": "number"},
                            "y0": {"type": "number"},
                            "x1": {"type": "number"},
                            "y1": {"type": "number"},
                        },
                    },
                    "confidence": {"type": "number"},
                },
            },
        },
    },
    "required": ["is_drawing", "confidence"],
}
