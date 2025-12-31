# -*- coding: utf-8 -*-
"""Sensor manager to orchestrate sampling and persistence."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from contexgo.chronicle.assembly.chronicle_gate import ChronicleGate
from contexgo.protocol.api.sensor_registry import list_sensors
from contexgo.protocol.context import RawContextProperties


class SensorManager:
    def __init__(self, gate: Optional[ChronicleGate] = None) -> None:
        self._gate = gate or ChronicleGate()

    async def sample_all(self) -> None:
        payloads: List[Dict[str, Any]] = []
        for entry in list_sensors():
            sensor = entry.sensor
            if not sensor.is_running():
                continue
            for raw in sensor.capture():
                payloads.append(self._raw_to_payload(raw))

        if payloads:
            await self._gate.append_many(payloads)

    @staticmethod
    def _raw_to_payload(raw: RawContextProperties) -> Dict[str, Any]:
        if hasattr(raw, "model_dump"):
            payload = raw.model_dump()
        else:
            payload = raw.dict()  # type: ignore[call-arg]
        payload.setdefault("source", payload.get("context_type"))
        payload.setdefault("timestamp", payload.get("create_time"))
        return payload
