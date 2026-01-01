import asyncio
import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
existing_pythonpath = os.environ.get("PYTHONPATH", "")
if existing_pythonpath:
    os.environ["PYTHONPATH"] = f"{repo_root_str}{os.pathsep}{existing_pythonpath}"
else:
    os.environ["PYTHONPATH"] = repo_root_str

import uvicorn
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from contexgo.chronicle.assembly.sensor_manager import SensorManager
from contexgo.chronicle.assembly.chronicle_gate import shutdown_default_gate
from contexgo.infra.logging_utils import get_logger
from contexgo.protocol.api.schema import schema
from contexgo.protocol.api.sensor_registry import (
    get_sensor_factory,
    register_sensors_from_config,
)

STOP_EVENT: Optional[asyncio.Event] = None

logger = get_logger(__name__)
DEFAULT_SENSOR_CONFIG_PATH = Path("data") / "CONTEXGO_SENSOR_CONFIG.json"
_SCRIPT_LOG_TIMES: Dict[str, float] = {}


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


def _default_sensor_configs() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "global_config": {},
        "sensors": [
            {
                "sensor_type": "input_metric",
                "sensor_id": "input_metric",
                "script_path": "contexgo/chronicle/sensors/activity.py",
                "config": {"capture_interval": 1.0},
            },
            {
                "sensor_type": "window_focus",
                "sensor_id": "window_focus",
                "script_path": "contexgo/chronicle/sensors/focus.py",
                "config": {"capture_interval": 1.0},
            },
            {
                "sensor_type": "desktop_snapshot",
                "sensor_id": "desktop_snapshot",
                "script_path": "contexgo/chronicle/sensors/vision/capturer.py",
                "config": {"capture_interval": 10.0},
            },
            {
                "sensor_type": "clipboard_update",
                "sensor_id": "clipboard_update",
                "script_path": "contexgo/chronicle/sensors/clipboard.py",
                "config": {},
            },
            {
                "sensor_type": "system_lifecycle",
                "sensor_id": "system_lifecycle",
                "script_path": "contexgo/chronicle/sensors/heartbeat.py",
                "config": {},
            },
            {
                "sensor_type": "file_mutation",
                "sensor_id": "file_mutation",
                "script_path": "contexgo/chronicle/sensors/files.py",
                "config": {},
            },
            {
                "sensor_type": "media_status",
                "sensor_id": "media_status",
                "script_path": "contexgo/chronicle/sensors/media.py",
                "config": {},
            },
        ],
    }


def _write_default_sensor_config(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _default_sensor_configs()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _parse_sensor_configs(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if payload is None:
        return [], {}
    if isinstance(payload, dict):
        sensors = payload.get("sensors", [])
        global_config = payload.get("global_config", {})
        if not isinstance(sensors, list):
            raise ValueError("Sensor configuration 'sensors' must be a list")
        if not isinstance(global_config, dict):
            raise ValueError("Sensor configuration 'global_config' must be a dict")
        return sensors, global_config
    if isinstance(payload, list):
        return payload, {}
    raise ValueError("Sensor configuration must be a list or object")


def _log_missing_script(path: Path) -> None:
    now = time.time()
    last = _SCRIPT_LOG_TIMES.get(str(path), 0.0)
    if now - last < 600:
        return
    _SCRIPT_LOG_TIMES[str(path)] = now
    logger.warning("Sensor script missing: %s", path.as_posix())


def _filter_configs(configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    factory = get_sensor_factory()
    filtered: List[Dict[str, Any]] = []
    for item in configs:
        if not isinstance(item, dict):
            raise ValueError("Sensor configuration entries must be dictionaries")
        script_path = item.get("script_path") or item.get("script")
        if script_path:
            script = Path(str(script_path))
            if not script.exists():
                _log_missing_script(script)
                continue
        sensor_type = item.get("sensor_type")
        if not sensor_type:
            raise ValueError("sensor_type is required in sensor configuration")
        if str(sensor_type).strip().lower() not in factory:
            logger.warning("Unknown sensor type '%s'; skipping", sensor_type)
            continue
        filtered.append(item)
    return filtered


def register_default_sensors() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    config_path = os.getenv("CONTEXGO_SENSOR_CONFIG_PATH")
    config_payload = os.getenv("CONTEXGO_SENSOR_CONFIG")
    configs = None

    if config_path:
        with open(config_path, "r", encoding="utf-8") as handle:
            configs = json.load(handle)
    elif config_payload:
        configs = json.loads(config_payload)
    else:
        _write_default_sensor_config(DEFAULT_SENSOR_CONFIG_PATH)
        with DEFAULT_SENSOR_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            configs = json.load(handle)

    sensor_configs, global_config = _parse_sensor_configs(configs)
    sensor_configs = _filter_configs(sensor_configs)
    if sensor_configs:
        register_sensors_from_config(sensor_configs)
    return sensor_configs, global_config


_SENSOR_MANAGER: Optional[SensorManager] = None


def _get_sensor_manager() -> SensorManager:
    global _SENSOR_MANAGER
    if _SENSOR_MANAGER is None:
        _SENSOR_MANAGER = SensorManager()
    return _SENSOR_MANAGER


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

    _, global_config = register_default_sensors()
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

    global STOP_EVENT
    STOP_EVENT = asyncio.Event()

    loop = asyncio.get_running_loop()
    install_signal_handlers(loop, STOP_EVENT, server)

    server_task = asyncio.create_task(server.serve())
    manager = _get_sensor_manager()
    if global_config:
        manager.apply_global_config(global_config)
    manager.start_all()
    sensor_task = asyncio.create_task(manager.monitor_health(STOP_EVENT))

    await STOP_EVENT.wait()
    server.should_exit = True
    manager.stop_all()
    await shutdown_default_gate()
    await asyncio.gather(server_task, sensor_task, return_exceptions=True)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
