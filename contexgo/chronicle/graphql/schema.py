# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

import strawberry

from contexgo.chronicle.assembly.chronicle_gate import ChronicleGate


@strawberry.type
class ChronicleRecord:
    id: strawberry.ID
    timestamp: float
    source: Optional[str]
    content: Optional[str]
    blob_path: Optional[str]


@strawberry.input
class ChronicleInput:
    timestamp: Optional[float] = None
    source: Optional[str] = None
    content: Optional[str] = None
    blob_path: Optional[str] = None


def _to_record(payload: dict) -> ChronicleRecord:
    return ChronicleRecord(
        id=str(payload.get("id", "")),
        timestamp=float(payload.get("timestamp", 0.0)),
        source=payload.get("source"),
        content=payload.get("content"),
        blob_path=payload.get("blob_path"),
    )


@strawberry.type
class Query:
    @strawberry.field
    async def chronicle_by_id(
        self, info, object_id: strawberry.ID
    ) -> Optional[ChronicleRecord]:
        gate: ChronicleGate = info.context["chronicle"]
        payload = await gate.read_by_id(str(object_id))
        return _to_record(payload) if payload else None

    @strawberry.field
    async def chronicle_by_source(
        self, info, source: str
    ) -> List[ChronicleRecord]:
        gate: ChronicleGate = info.context["chronicle"]
        results = await gate.read_by_source(source)
        return [_to_record(item) for item in results]

    @strawberry.field
    async def chronicle_by_time(
        self, info, start_ts: float, end_ts: float
    ) -> List[ChronicleRecord]:
        gate: ChronicleGate = info.context["chronicle"]
        results = await gate.read_by_time_range(start_ts, end_ts)
        return [_to_record(item) for item in results]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_chronicle(
        self, info, input: ChronicleInput
    ) -> ChronicleRecord:
        gate: ChronicleGate = info.context["chronicle"]
        payload = await gate.append(input.__dict__)
        return _to_record(payload)


def build_schema() -> strawberry.Schema:
    return strawberry.Schema(query=Query, mutation=Mutation)
