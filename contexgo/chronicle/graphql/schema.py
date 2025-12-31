# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

import strawberry

from contexgo.chronicle.assembly.chronicle_gate import ChronicleGate


@strawberry.type
class ChronicleEvent:
    object_id: strawberry.ID
    context_type: Optional[str]
    content_type: Optional[str]
    create_time: Optional[str]
    content_path: Optional[str]
    content_text: Optional[str]


@strawberry.input
class ChronicleInput:
    context_type: Optional[str] = None
    content_type: Optional[str] = None
    content_text: Optional[str] = None
    content_path: Optional[str] = None
    create_time: Optional[str] = None


def _to_event(payload: dict) -> ChronicleEvent:
    return ChronicleEvent(
        object_id=str(payload.get("object_id", "")),
        context_type=payload.get("context_type"),
        content_type=payload.get("content_type"),
        create_time=str(payload.get("create_time")) if payload.get("create_time") else None,
        content_path=payload.get("content_path"),
        content_text=payload.get("content_text"),
    )


@strawberry.type
class Query:
    @strawberry.field
    async def chronicle_by_id(
        self, info, object_id: strawberry.ID
    ) -> Optional[ChronicleEvent]:
        gate: ChronicleGate = info.context["chronicle"]
        payload = await gate.read_by_id(str(object_id))
        return _to_event(payload) if payload else None

    @strawberry.field
    async def chronicle_by_type(
        self, info, context_type: str
    ) -> List[ChronicleEvent]:
        gate: ChronicleGate = info.context["chronicle"]
        results = await gate.read_by_type(context_type)
        return [_to_event(item) for item in results]

    @strawberry.field
    async def chronicle_by_time(
        self, info, start_ts: float, end_ts: float
    ) -> List[ChronicleEvent]:
        gate: ChronicleGate = info.context["chronicle"]
        results = await gate.read_by_time_range(start_ts, end_ts)
        return [_to_event(item) for item in results]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_chronicle(
        self, info, input: ChronicleInput
    ) -> ChronicleEvent:
        gate: ChronicleGate = info.context["chronicle"]
        payload = await gate.create(input.__dict__)
        return _to_event(payload)


def build_schema() -> strawberry.Schema:
    return strawberry.Schema(query=Query, mutation=Mutation)
