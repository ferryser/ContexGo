from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from ContexGo.chronicle.base_l1_sensor import BaseL1Sensor


@dataclass(frozen=True)
class SensorEntry:
    sensor_id: str
    sensor: BaseL1Sensor


_SENSOR_REGISTRY: Dict[str, BaseL1Sensor] = {}


def register_sensor(sensor: BaseL1Sensor, sensor_id: Optional[str] = None) -> str:
    resolved_id = sensor_id or sensor._name
    if resolved_id in _SENSOR_REGISTRY and _SENSOR_REGISTRY[resolved_id] is not sensor:
        raise ValueError(f"Sensor id '{resolved_id}' is already registered")
    _SENSOR_REGISTRY[resolved_id] = sensor
    return resolved_id


def unregister_sensor(sensor_id: str) -> Optional[BaseL1Sensor]:
    return _SENSOR_REGISTRY.pop(sensor_id, None)


def get_sensor(sensor_id: str) -> Optional[BaseL1Sensor]:
    return _SENSOR_REGISTRY.get(sensor_id)


def list_sensors() -> List[SensorEntry]:
    return [SensorEntry(sensor_id=key, sensor=value) for key, value in _SENSOR_REGISTRY.items()]
