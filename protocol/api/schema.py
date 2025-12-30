import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import strawberry

from ContexGo.protocol.api.sensor_registry import SensorEntry, get_sensor, list_sensors


@strawberry.type
class SensorNode:
    id: strawberry.ID
    name: str
    description: str
    status: str
    running: bool
    last_error: Optional[str]
    error_count: int

    @staticmethod
    def from_entry(entry: SensorEntry) -> "SensorNode":
        sensor = entry.sensor
        running = sensor.is_running()
        return SensorNode(
            id=strawberry.ID(entry.sensor_id),
            name=sensor._name,
            description=sensor._description,
            status="running" if running else "stopped",
            running=running,
            last_error=sensor._last_error,
            error_count=sensor._error_count,
        )


@strawberry.type
class SensorActionResult:
    status_code: int
    message: str
    error_stack: List[str]
    sensors: List[SensorNode]


@strawberry.type
class SensorStatusEvent:
    sensor_id: strawberry.ID
    status: str
    message: str
    timestamp: datetime


@strawberry.type
class SensorErrorEvent:
    sensor_id: strawberry.ID
    message: str
    error: str
    error_count: int
    timestamp: datetime


@dataclass
class _Subscriber:
    queue: asyncio.Queue[SensorStatusEvent]


@dataclass
class _ErrorSubscriber:
    queue: asyncio.Queue[SensorErrorEvent]


_SENSOR_SUBSCRIBERS: List[_Subscriber] = []
_SENSOR_ERROR_SUBSCRIBERS: List[_ErrorSubscriber] = []


def _publish_status(event: SensorStatusEvent) -> None:
    for subscriber in list(_SENSOR_SUBSCRIBERS):
        subscriber.queue.put_nowait(event)


def publish_sensor_error(sensor_id: str, message: str, error: str, error_count: int) -> None:
    event = SensorErrorEvent(
        sensor_id=strawberry.ID(sensor_id),
        message=message,
        error=error,
        error_count=error_count,
        timestamp=datetime.utcnow(),
    )
    for subscriber in list(_SENSOR_ERROR_SUBSCRIBERS):
        subscriber.queue.put_nowait(event)


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"

    @strawberry.field
    def sensors(self) -> List[SensorNode]:
        return [SensorNode.from_entry(entry) for entry in list_sensors()]


@strawberry.type
class Mutation:
    @strawberry.field(name="toggleSensor")
    def toggle_sensor(self, sensor_id: strawberry.ID, enable: Optional[bool] = None) -> SensorActionResult:
        sensor = get_sensor(str(sensor_id))
        if sensor is None:
            return SensorActionResult(
                status_code=404,
                message=f"Sensor '{sensor_id}' not found",
                error_stack=["sensor_not_found"],
                sensors=[],
            )

        desired_state = enable
        if desired_state is None:
            desired_state = not sensor.is_running()

        errors: List[str] = []
        if desired_state:
            if not sensor.start():
                errors.append("start_failed")
        else:
            if not sensor.stop(graceful=True):
                errors.append("stop_failed")

        status = "running" if sensor.is_running() else "stopped"
        message = "sensor updated" if not errors else "sensor update failed"
        event = SensorStatusEvent(
            sensor_id=sensor_id,
            status=status,
            message=message,
            timestamp=datetime.utcnow(),
        )
        _publish_status(event)

        return SensorActionResult(
            status_code=200 if not errors else 500,
            message=message,
            error_stack=errors,
            sensors=[SensorNode.from_entry(SensorEntry(sensor_id=str(sensor_id), sensor=sensor))],
        )

    @strawberry.field(name="bulkAction")
    def bulk_action(
        self, sensor_ids: Optional[List[strawberry.ID]] = None, enable: Optional[bool] = None
    ) -> SensorActionResult:
        if not sensor_ids:
            return SensorActionResult(
                status_code=400,
                message="No sensors provided",
                error_stack=["sensor_ids_empty"],
                sensors=[],
            )

        errors: List[str] = []
        updated: List[SensorNode] = []
        for sensor_id in sensor_ids:
            sensor = get_sensor(str(sensor_id))
            if sensor is None:
                errors.append(f"sensor_not_found:{sensor_id}")
                continue

            desired_state = enable
            if desired_state is None:
                desired_state = not sensor.is_running()

            if desired_state:
                if not sensor.start():
                    errors.append(f"start_failed:{sensor_id}")
            else:
                if not sensor.stop(graceful=True):
                    errors.append(f"stop_failed:{sensor_id}")

            status = "running" if sensor.is_running() else "stopped"
            message = "sensor updated" if sensor.is_running() == desired_state else "sensor update failed"
            _publish_status(
                SensorStatusEvent(
                    sensor_id=sensor_id,
                    status=status,
                    message=message,
                    timestamp=datetime.utcnow(),
                )
            )
            updated.append(SensorNode.from_entry(SensorEntry(sensor_id=str(sensor_id), sensor=sensor)))

        status_code = 200 if not errors else 207
        message = "sensors updated" if not errors else "sensors updated with errors"

        return SensorActionResult(
            status_code=status_code,
            message=message,
            error_stack=errors,
            sensors=updated,
        )


@strawberry.type
class Subscription:
    @strawberry.subscription(name="sensorStatus")
    async def sensor_status(self) -> AsyncGenerator[SensorStatusEvent, None]:
        queue: asyncio.Queue[SensorStatusEvent] = asyncio.Queue()
        subscriber = _Subscriber(queue=queue)
        _SENSOR_SUBSCRIBERS.append(subscriber)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            if subscriber in _SENSOR_SUBSCRIBERS:
                _SENSOR_SUBSCRIBERS.remove(subscriber)

    @strawberry.subscription(name="sensorErrors")
    async def sensor_errors(self) -> AsyncGenerator[SensorErrorEvent, None]:
        queue: asyncio.Queue[SensorErrorEvent] = asyncio.Queue()
        subscriber = _ErrorSubscriber(queue=queue)
        _SENSOR_ERROR_SUBSCRIBERS.append(subscriber)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            if subscriber in _SENSOR_ERROR_SUBSCRIBERS:
                _SENSOR_ERROR_SUBSCRIBERS.remove(subscriber)

    @strawberry.subscription
    async def ticker(self, interval: float = 1.0) -> AsyncGenerator[int, None]:
        counter = 0
        while True:
            yield counter
            counter += 1
            await asyncio.sleep(interval)


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
