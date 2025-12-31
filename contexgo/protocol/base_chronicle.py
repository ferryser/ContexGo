# -*- coding: utf-8 -*-
from __future__ import annotations

import abc
from typing import Any, Iterable, Optional


class BaseChronicle(abc.ABC):
    """Chronicle 抽象协议：纯增量写入与查询接口。"""

    @abc.abstractmethod
    async def append(self, payload: Any) -> Any:
        """Append a chronicle record."""

    @abc.abstractmethod
    async def append_many(self, payloads: Iterable[Any]) -> Iterable[Any]:
        """Append chronicle records in batch."""

    @abc.abstractmethod
    async def read_by_time_range(
        self, start_ts: float, end_ts: float
    ) -> Iterable[Any]:
        """Read chronicle records by time range (timestamp seconds)."""

    @abc.abstractmethod
    async def read_by_id(self, object_id: str) -> Optional[Any]:
        """Read a chronicle record by object id."""

    @abc.abstractmethod
    async def read_by_source(self, source: str) -> Iterable[Any]:
        """Read chronicle records by source."""

    @abc.abstractmethod
    async def flush(self) -> None:
        """Force flush buffered writes."""

    async def gql_query_by_id(self, info: Any, object_id: str) -> Optional[Any]:
        """GraphQL resolver-compatible query entry."""
        _ = info
        return await self.read_by_id(object_id)
