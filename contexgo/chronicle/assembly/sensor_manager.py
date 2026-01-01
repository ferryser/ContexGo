# -*- coding: utf-8 -*-
"""Sensor manager to orchestrate sensor lifecycle and health checks."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from contexgo.infra.logging_utils import get_logger
from contexgo.protocol.api.sensor_registry import list_sensors

logger = get_logger(__name__)

class SensorManager:
    def __init__(self) -> None:
        self._desired_running: set[str] = set()
        self._global_config: Dict[str, Any] = {}

    def apply_global_config(self, config: Dict[str, Any]) -> None:
        self._global_config = config.copy()
        for entry in list_sensors():
            entry.sensor.apply_global_config(self._global_config)

    def start_all(self) -> None:
        for entry in list_sensors():
            sensor = entry.sensor
            self._desired_running.add(entry.sensor_id)
            if not sensor.is_running():
                if not sensor.start():
                    logger.warning("Failed to start sensor '%s'", entry.sensor_id)

    def stop_all(self) -> None:
        for entry in list_sensors():
            sensor = entry.sensor
            if sensor.is_running():
                if not sensor.stop(graceful=True):
                    logger.warning("Failed to stop sensor '%s'", entry.sensor_id)
        self._desired_running.clear()

    def check_health(self) -> None:
        for entry in list_sensors():
            sensor_id = entry.sensor_id
            sensor = entry.sensor
            if sensor_id not in self._desired_running:
                continue
            if sensor.is_running():
                continue
            logger.warning("Sensor '%s' is not running; attempting restart", sensor_id)
            if not sensor.start():
                logger.error("Sensor '%s' restart failed", sensor_id)

    async def monitor_health(self, stop_event: asyncio.Event, interval: float = 10.0) -> None:
        while not stop_event.is_set():
            self.check_health()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
