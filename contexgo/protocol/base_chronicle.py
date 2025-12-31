# -*- coding: utf-8 -*-
from __future__ import annotations

import abc
from typing import Any, Iterable, Optional


class BaseChronicle(abc.ABC):
    """Chronicle 抽象协议：统一本地 CRUD 与 GraphQL Resolver 适配接口。"""

    @abc.abstractmethod
    async def create(self, payload: Any) -> Any:
        """Create a chronicle record."""

    @abc.abstractmethod
    async def read_by_id(self, object_id: str) -> Optional[Any]:
        """Read a chronicle record by object id."""

    @abc.abstractmethod
    async def read_by_time_range(
        self, start_ts: float, end_ts: float
    ) -> Iterable[Any]:
        """Read chronicle records by time range (timestamp seconds)."""

    @abc.abstractmethod
    async def read_by_type(self, context_type: str) -> Iterable[Any]:
        """Read chronicle records by type."""

    @abc.abstractmethod
    async def update(self, object_id: str, payload: Any) -> Any:
        """Update chronicle record."""

    @abc.abstractmethod
    async def delete(self, object_id: str) -> bool:
        """Delete chronicle record."""

    async def gql_query_by_id(self, info: Any, object_id: str) -> Optional[Any]:
        """GraphQL resolver-compatible query entry."""
        _ = info
        return await self.read_by_id(object_id)
