from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from ContexGo.chronicle.base_l1_sensor import BaseL1Sensor
from ContexGo.chronicle.sensors.window_focus import WindowFocusSensor


@dataclass(frozen=True)
class SensorEntry:
    sensor_id: str
    sensor: BaseL1Sensor


_SENSOR_REGISTRY: Dict[str, BaseL1Sensor] = {}
_SENSOR_FACTORY: Dict[str, Type[BaseL1Sensor]] = {
    "window_focus": WindowFocusSensor,
}


def get_sensor_factory() -> Dict[str, Type[BaseL1Sensor]]:
    return dict(_SENSOR_FACTORY)


def create_sensor(
    sensor_type: str,
    *,
    sensor_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> SensorEntry:
    if not sensor_type:
        raise ValueError("sensor_type is required")
    normalized_type = sensor_type.strip().lower()
    if normalized_type not in _SENSOR_FACTORY:
        raise ValueError(f"Unknown sensor type '{sensor_type}'")
    sensor_cls = _SENSOR_FACTORY[normalized_type]
    sensor = sensor_cls()
    resolved_config = config or {}
    if not isinstance(resolved_config, dict):
        raise ValueError("config must be a dictionary")
    if not sensor.initialize(resolved_config):
        raise RuntimeError(f"Failed to initialize sensor '{sensor_type}'")
    resolved_id = register_sensor(sensor, sensor_id=sensor_id)
    return SensorEntry(sensor_id=resolved_id, sensor=sensor)


def register_sensors_from_config(configs: List[Dict[str, Any]]) -> List[SensorEntry]:
    entries: List[SensorEntry] = []
    for item in configs:
        if not isinstance(item, dict):
            raise ValueError("Sensor configuration entries must be dictionaries")
        sensor_type = item.get("sensor_type")
        if not sensor_type:
            raise ValueError("sensor_type is required in sensor configuration")
        sensor_id = item.get("sensor_id")
        sensor_config = item.get("config") or {}
        entries.append(
            create_sensor(
                sensor_type=str(sensor_type),
                sensor_id=str(sensor_id) if sensor_id is not None else None,
                config=sensor_config,
            )
        )
    return entries


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
