"""Repository boundary for Project Operator configuration."""

from __future__ import annotations

import asyncio
from typing import Protocol

from construction_os.project_operator.models import OperatorConfig


class ProjectOperatorRepository(Protocol):
    """Persistence contract kept independent from any database implementation."""

    async def get_config(self, project_id: str) -> OperatorConfig | None: ...

    async def save_config(self, config: OperatorConfig) -> OperatorConfig: ...

    async def list_configs(self) -> list[OperatorConfig]: ...


class InMemoryProjectOperatorRepository:
    """Deterministic foundation repository used until persistent storage is added."""

    def __init__(self) -> None:
        self._configs: dict[str, OperatorConfig] = {}
        self._lock = asyncio.Lock()

    async def get_config(self, project_id: str) -> OperatorConfig | None:
        async with self._lock:
            config = self._configs.get(project_id)
            return config.model_copy(deep=True) if config else None

    async def save_config(self, config: OperatorConfig) -> OperatorConfig:
        async with self._lock:
            saved = config.model_copy(deep=True)
            self._configs[config.project_id] = saved
            return saved.model_copy(deep=True)

    async def list_configs(self) -> list[OperatorConfig]:
        async with self._lock:
            return [config.model_copy(deep=True) for config in self._configs.values()]
