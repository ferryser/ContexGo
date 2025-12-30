import asyncio
import os
import signal
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from chronicle.sensors.window_focus import WindowFocusSensor
from protocol.api.schema import schema
from protocol.api.sensor_registry import list_sensors, register_sensor

CONTROL_QUEUE: Optional[asyncio.Queue[str]] = None
STOP_EVENT: Optional[asyncio.Event] = None


def submit_control(command: str) -> None:
    if CONTROL_QUEUE is None:
        raise RuntimeError("Control queue not initialized")
    CONTROL_QUEUE.put_nowait(command)


def request_shutdown() -> None:
    if STOP_EVENT is None:
        raise RuntimeError("Stop event not initialized")
    STOP_EVENT.set()


@dataclass
class InstanceLock:
    socket: Optional[socket.socket] = None
    lock_file: Optional[object] = None


def acquire_instance_lock(host: str, port: int) -> InstanceLock:
    if os.name == "nt":
        return _acquire_windows_lock()
    return _acquire_socket_lock(host, port)


def _acquire_socket_lock(host: str, port: int) -> InstanceLock:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind((host, port))
        lock_socket.listen(1)
    except OSError:
        lock_socket.close()
        print("Instance collision", file=sys.stderr)
        sys.exit(1)
    return InstanceLock(socket=lock_socket)


def _acquire_windows_lock() -> InstanceLock:
    import msvcrt

    lock_path = Path(os.getenv("CONTEXGO_LOCK_FILE", "contexgo.lock")).resolve()
    lock_file = open(lock_path, "a+")
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        print("Instance collision", file=sys.stderr)
        sys.exit(1)
    return InstanceLock(lock_file=lock_file)


def build_app() -> FastAPI:
    app = FastAPI()
    graphql_app = GraphQLRouter(schema)
    app.include_router(graphql_app, prefix="/graphql")
    return app


def register_default_sensors() -> None:
    sensors = [WindowFocusSensor()]
    for sensor in sensors:
        sensor.initialize({})
        register_sensor(sensor)


async def sample_sensors() -> None:
    for entry in list_sensors():
        sensor = entry.sensor
        if sensor.is_running():
            sensor.capture()
    await asyncio.sleep(0.1)


async def sensor_loop(control_queue: asyncio.Queue[str], stop_event: asyncio.Event) -> None:
    paused = False
    while not stop_event.is_set():
        try:
            command = await asyncio.wait_for(control_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            command = None

        if command == "pause":
            paused = True
        elif command == "resume":
            paused = False
        elif command == "shutdown":
            stop_event.set()
            continue

        if paused:
            await asyncio.sleep(0.1)
            continue

        await sample_sensors()


def install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_event: asyncio.Event,
    server: uvicorn.Server,
) -> None:
    def _handle_signal() -> None:
        stop_event.set()
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal())


async def run() -> None:
    host = os.getenv("CONTEXGO_HOST", "127.0.0.1")
    port = int(os.getenv("CONTEXGO_PORT", "35011"))
    instance_lock = acquire_instance_lock(host, port)

    register_default_sensors()
    app = build_app()
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
        fd=instance_lock.socket.fileno() if instance_lock.socket else None,
    )
    server = uvicorn.Server(config)

    global CONTROL_QUEUE, STOP_EVENT
    STOP_EVENT = asyncio.Event()
    CONTROL_QUEUE = asyncio.Queue()

    loop = asyncio.get_running_loop()
    install_signal_handlers(loop, STOP_EVENT, server)

    server_task = asyncio.create_task(server.serve())
    sensor_task = asyncio.create_task(sensor_loop(CONTROL_QUEUE, STOP_EVENT))

    await STOP_EVENT.wait()
    server.should_exit = True
    await asyncio.gather(server_task, sensor_task, return_exceptions=True)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
