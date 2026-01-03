import argparse
import asyncio
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http import client as http_client
from queue import Empty, LifoQueue
from threading import Event, Thread
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse


try:
    import websockets
except ImportError:  # pragma: no cover - optional dependency
    websockets = None


@dataclass
class GraphQLResponse:
    data: Optional[Dict[str, Any]]
    errors: Optional[Iterable[Dict[str, Any]]]


class HTTPConnectionPool:
    def __init__(self, base_url: str, max_size: int = 2, timeout: float = 10.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported scheme: {parsed.scheme}")
        if not parsed.hostname:
            raise ValueError("Base URL must include a hostname")
        self._scheme = parsed.scheme
        self._hostname = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._path = parsed.path or "/graphql"
        if parsed.query:
            raise ValueError("Base URL should not include query params")
        self._timeout = timeout
        self._pool: LifoQueue[http_client.HTTPConnection] = LifoQueue(maxsize=max_size)
        self._max_size = max_size
        self._created = 0

    @property
    def path(self) -> str:
        return self._path

    def _create_connection(self) -> http_client.HTTPConnection:
        if self._scheme == "https":
            return http_client.HTTPSConnection(self._hostname, self._port, timeout=self._timeout)
        return http_client.HTTPConnection(self._hostname, self._port, timeout=self._timeout)

    @contextmanager
    def acquire(self) -> Iterable[http_client.HTTPConnection]:
        conn: Optional[http_client.HTTPConnection] = None
        try:
            try:
                conn = self._pool.get_nowait()
            except Empty:
                if self._created < self._max_size:
                    conn = self._create_connection()
                    self._created += 1
                else:
                    conn = self._pool.get()
            yield conn
        except Exception:
            if conn is not None:
                conn.close()
            raise
        else:
            if conn is not None:
                try:
                    self._pool.put_nowait(conn)
                except Exception:
                    conn.close()


class GraphQLHTTPClient:
    def __init__(self, base_url: str, pool_size: int = 2, timeout: float = 10.0) -> None:
        self._pool = HTTPConnectionPool(base_url, max_size=pool_size, timeout=timeout)

    def request(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
    ) -> GraphQLResponse:
        payload: Dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
        body = json.dumps(payload, ensure_ascii=False)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
        with self._pool.acquire() as conn:
            conn.request("POST", self._pool.path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
        if response.status >= 400:
            raise RuntimeError(f"GraphQL HTTP {response.status}: {raw.decode('utf-8', errors='ignore')}")
        parsed = json.loads(raw)
        return GraphQLResponse(data=parsed.get("data"), errors=parsed.get("errors"))


class GraphQLWebSocketClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        if websockets is None:
            raise RuntimeError("websockets is required for subscriptions. Install websockets>=10.")
        parsed = urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        self._url = f"{scheme}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
        self._path = parsed.path or "/graphql"
        self._timeout = timeout
        self._ws = None

    async def __aenter__(self) -> "GraphQLWebSocketClient":
            # 增加 subprotocols 参数，显式声明支持 graphql-transport-ws
            self._ws = await websockets.connect(
                f"{self._url}{self._path}",
                subprotocols=["graphql-transport-ws"]
            )
            # 其余初始化逻辑保持不变
            await self._ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            await self._await_ack()
            return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def _await_ack(self) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
            payload = json.loads(raw)
            if payload.get("type") == "connection_ack":
                return
            if payload.get("type") == "connection_error":
                raise RuntimeError(f"WebSocket connection error: {payload.get('payload')}")

    async def subscribe(self, query: str, variables: Optional[Dict[str, Any]] = None):
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        operation_id = str(uuid.uuid4())
        await self._ws.send(
            json.dumps(
                {
                    "id": operation_id,
                    "type": "subscribe",
                    "payload": {"query": query, "variables": variables or {}},
                }
            )
        )
        try:
            while True:
                raw = await self._ws.recv()
                payload = json.loads(raw)
                if payload.get("id") != operation_id:
                    continue
                message_type = payload.get("type")
                if message_type == "next":
                    yield payload.get("payload", {}).get("data")
                elif message_type == "error":
                    raise RuntimeError(f"Subscription error: {payload.get('payload')}")
                elif message_type == "complete":
                    break
        finally:
            await self._ws.send(json.dumps({"id": operation_id, "type": "complete"}))


def parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_recent(timestamp: datetime, max_age_seconds: float) -> bool:
    now = datetime.now(timezone.utc)
    return (now - timestamp).total_seconds() <= max_age_seconds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ContexGo GraphQL sensor CLI")
    parser.add_argument("--url", default="http://127.0.0.1:8000/graphql", help="GraphQL endpoint URL")
    parser.add_argument("--pool-size", type=int, default=2, help="HTTP connection pool size")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP/WS timeout seconds")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sensors", help="List all sensors")

    toggle = subparsers.add_parser("toggle", help="Toggle a sensor")
    toggle.add_argument("sensor_id")

    start = subparsers.add_parser("start", help="Start a sensor")
    start.add_argument("sensor_id")

    stop = subparsers.add_parser("stop", help="Stop a sensor")
    stop.add_argument("sensor_id")

    bulk_start = subparsers.add_parser("bulk-start", help="Start multiple sensors")
    bulk_start.add_argument("sensor_ids", nargs="+")

    bulk_stop = subparsers.add_parser("bulk-stop", help="Stop multiple sensors")
    bulk_stop.add_argument("sensor_ids", nargs="+")

    register = subparsers.add_parser("register", help="Register a sensor")
    register.add_argument("sensor_type")
    register.add_argument("--sensor-id")
    register.add_argument("--config", help="JSON config payload")

    unregister = subparsers.add_parser("unregister", help="Unregister a sensor")
    unregister.add_argument("sensor_id")

    log_stream = subparsers.add_parser("log-stream", help="Subscribe to logStream")
    log_stream.add_argument("--max-age-seconds", type=float, default=1.0)

    status_stream = subparsers.add_parser("status-stream", help="Subscribe to sensorStatus")

    subparsers.add_parser("serve", help="Run contexgo/main.py and stream logs")

    return parser


def print_sensors(sensors: Iterable[Dict[str, Any]]) -> None:
    rows = list(sensors)
    if not rows:
        print("No sensors found")
        return
    header = f"{'ID':<24} {'Name':<20} {'Status':<10} {'Running':<8} {'Errors':<6}"
    print(header)
    print("-" * len(header))
    for sensor in rows:
        print(
            f"{sensor['id']:<24} {sensor['name']:<20} {sensor['status']:<10} "
            f"{str(sensor['running']):<8} {sensor['error_count']:<6}"
        )


def ensure_no_errors(response: GraphQLResponse) -> None:
    if response.errors:
        raise RuntimeError(f"GraphQL errors: {response.errors}")


def handle_sensors(client: GraphQLHTTPClient) -> None:
    query = """
    query {
      sensors {
        id
        name
        description
        status
        running
        errorCount
      }
    }
    """
    response = client.request(query)
    ensure_no_errors(response)
    print_sensors(response.data["sensors"])


def handle_toggle(client: GraphQLHTTPClient, sensor_id: str, enable: Optional[bool]) -> None:
    mutation = """
    mutation($sensorId: ID!, $enable: Boolean) {
      toggleSensor(sensorId: $sensorId, enable: $enable) {
        statusCode
        message
        errorStack
        sensors {
          id
          name
          status
          running
          errorCount
        }
      }
    }
    """
    response = client.request(mutation, {"sensorId": sensor_id, "enable": enable})
    ensure_no_errors(response)
    result = response.data["toggleSensor"]
    print(f"{result['message']} (status={result['statusCode']})")
    if result["errorStack"]:
        print("Errors:", result["errorStack"])
    print_sensors(result["sensors"])


def handle_bulk(client: GraphQLHTTPClient, sensor_ids: Iterable[str], enable: Optional[bool]) -> None:
    mutation = """
    mutation($sensorIds: [ID!], $enable: Boolean) {
      bulkAction(sensorIds: $sensorIds, enable: $enable) {
        statusCode
        message
        errorStack
        sensors {
          id
          name
          status
          running
          errorCount
        }
      }
    }
    """
    response = client.request(mutation, {"sensorIds": list(sensor_ids), "enable": enable})
    ensure_no_errors(response)
    result = response.data["bulkAction"]
    print(f"{result['message']} (status={result['statusCode']})")
    if result["errorStack"]:
        print("Errors:", result["errorStack"])
    print_sensors(result["sensors"])


def handle_register(client: GraphQLHTTPClient, sensor_type: str, sensor_id: Optional[str], config: Optional[str]) -> None:
    mutation = """
    mutation($sensor: SensorRegistrationInput!) {
      registerSensor(sensor: $sensor) {
        statusCode
        message
        errorStack
        sensors {
          id
          name
          status
          running
          errorCount
        }
      }
    }
    """
    payload: Dict[str, Any] = {"sensor_type": sensor_type}
    if sensor_id:
        payload["sensor_id"] = sensor_id
    if config:
        payload["config"] = json.loads(config)
    response = client.request(mutation, {"sensor": payload})
    ensure_no_errors(response)
    result = response.data["registerSensor"]
    print(f"{result['message']} (status={result['statusCode']})")
    if result["errorStack"]:
        print("Errors:", result["errorStack"])
    print_sensors(result["sensors"])


def handle_unregister(client: GraphQLHTTPClient, sensor_id: str) -> None:
    mutation = """
    mutation($sensorId: ID!) {
      unregisterSensor(sensorId: $sensorId) {
        statusCode
        message
        errorStack
        sensors {
          id
          name
          status
          running
          errorCount
        }
      }
    }
    """
    response = client.request(mutation, {"sensorId": sensor_id})
    ensure_no_errors(response)
    result = response.data["unregisterSensor"]
    print(f"{result['message']} (status={result['statusCode']})")
    if result["errorStack"]:
        print("Errors:", result["errorStack"])
    print_sensors(result["sensors"])


async def handle_log_stream(base_url: str, timeout: float, max_age: float) -> None:
    query = """
    subscription {
      logStream {
        timestamp
        level
        message
        name
        function
        line
      }
    }
    """
    async with GraphQLWebSocketClient(base_url, timeout=timeout) as client:
        async for payload in client.subscribe(query):
            if not payload:
                continue
            event = payload.get("logStream")
            if not event:
                continue
            try:
                timestamp = parse_timestamp(event["timestamp"])
            except Exception:
                timestamp = datetime.now(timezone.utc)
            if not is_recent(timestamp, max_age):
                continue
            ts = timestamp.astimezone(timezone.utc).isoformat()
            print(f"[{ts}] {event['level']} {event['name']}:{event['function']}:{event['line']} {event['message']}")


async def handle_status_stream(base_url: str, timeout: float) -> None:
    query = """
    subscription {
      sensorStatus {
        sensorId
        status
        message
        timestamp
      }
    }
    """
    async with GraphQLWebSocketClient(base_url, timeout=timeout) as client:
        async for payload in client.subscribe(query):
            if not payload:
                continue
            event = payload.get("sensorStatus")
            if not event:
                continue
            print(
                f"[{event['timestamp']}] sensor={event['sensorId']} status={event['status']} message={event['message']}"
            )


class LogSubscriptionWorker:
    def __init__(self, base_url: str, timeout: float, start_time: datetime) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._start_time = start_time
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task[None]] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="log-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            print(f"Log subscription stopped: {exc}", file=sys.stderr)

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._subscribe())
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _subscribe(self) -> None:
        query = """
        subscription {
          logStream {
            timestamp
            level
            message
            name
            function
            line
          }
        }
        """
        while not self._stop_event.is_set():
            try:
                async with GraphQLWebSocketClient(self._base_url, timeout=self._timeout) as client:
                    async for payload in client.subscribe(query):
                        if self._stop_event.is_set():
                            return
                        if not payload:
                            continue
                        event = payload.get("logStream")
                        if not event:
                            continue
                        try:
                            timestamp = parse_timestamp(event["timestamp"])
                        except Exception:
                            timestamp = datetime.now(timezone.utc)
                        if timestamp < self._start_time:
                            continue
                        ts = timestamp.astimezone(timezone.utc).isoformat()
                        print(
                            f"[{ts}] {event['level']} {event['name']}:{event['function']}:{event['line']} "
                            f"{event['message']}"
                        )
            except Exception as exc:
                if self._stop_event.is_set():
                    return
                print(f"Log subscription error: {exc}", file=sys.stderr)
                await asyncio.sleep(1.0)


def _pump_stream(stream: Optional[object], writer: object) -> None:
    if stream is None:
        return
    for line in iter(stream.readline, ""):
        writer.write(line)
        writer.flush()


def _parse_host_port(base_url: str) -> Dict[str, str]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return {"CONTEXGO_HOST": host, "CONTEXGO_PORT": str(port)}


class _ControlParser(argparse.ArgumentParser):
    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if message:
            raise ValueError(message)
        raise ValueError("command parsing failed")

    def error(self, message: str) -> None:
        raise ValueError(message)


def _build_control_parser() -> argparse.ArgumentParser:
    parser = _ControlParser(prog="control", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Show this help message")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sensors", help="List all sensors")

    toggle = subparsers.add_parser("toggle", help="Toggle a sensor")
    toggle.add_argument("sensor_id")

    start = subparsers.add_parser("start", help="Start a sensor")
    start.add_argument("sensor_id")

    stop = subparsers.add_parser("stop", help="Stop a sensor")
    stop.add_argument("sensor_id")

    bulk_start = subparsers.add_parser("bulk-start", help="Start multiple sensors")
    bulk_start.add_argument("sensor_ids", nargs="+")

    bulk_stop = subparsers.add_parser("bulk-stop", help="Stop multiple sensors")
    bulk_stop.add_argument("sensor_ids", nargs="+")

    register = subparsers.add_parser("register", help="Register a sensor")
    register.add_argument("sensor_type")
    register.add_argument("--sensor-id")
    register.add_argument("--config", help="JSON config payload")

    unregister = subparsers.add_parser("unregister", help="Unregister a sensor")
    unregister.add_argument("sensor_id")

    return parser


def _dispatch_control_command(command: str, client: GraphQLHTTPClient, parser: argparse.ArgumentParser) -> bool:
    if command in {"help", "?"}:
        parser.print_help()
        return True
    if command in {"exit", "quit"}:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        print(f"Invalid command: {exc}", file=sys.stderr)
        return True
    if not tokens:
        return True
    try:
        args = parser.parse_args(tokens)
    except ValueError as exc:
        print(f"Invalid command: {exc}", file=sys.stderr)
        return True

    if args.command == "sensors":
        handle_sensors(client)
    elif args.command == "toggle":
        handle_toggle(client, args.sensor_id, None)
    elif args.command == "start":
        handle_toggle(client, args.sensor_id, True)
    elif args.command == "stop":
        handle_toggle(client, args.sensor_id, False)
    elif args.command == "bulk-start":
        handle_bulk(client, args.sensor_ids, True)
    elif args.command == "bulk-stop":
        handle_bulk(client, args.sensor_ids, False)
    elif args.command == "register":
        handle_register(client, args.sensor_type, args.sensor_id, args.config)
    elif args.command == "unregister":
        handle_unregister(client, args.sensor_id)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
    return True


def _setup_command_queue(loop: asyncio.AbstractEventLoop) -> tuple[asyncio.Queue[str], Optional[Thread], Event]:
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop_event = Event()

    def enqueue_line(line: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, line)

    try:
        loop.add_reader(sys.stdin, lambda: enqueue_line(sys.stdin.readline()))
        return queue, None, stop_event
    except (NotImplementedError, RuntimeError):
        def _reader() -> None:
            while not stop_event.is_set():
                line = sys.stdin.readline()
                enqueue_line(line)
                if line == "":
                    break

        thread = Thread(target=_reader, name="command-input", daemon=True)
        thread.start()
        return queue, thread, stop_event


async def _serve_control_loop(process: subprocess.Popen[str], client: GraphQLHTTPClient) -> int:
    loop = asyncio.get_running_loop()
    parser = _build_control_parser()
    queue, thread, stop_event = _setup_command_queue(loop)

    print("Interactive control loop ready. Type 'help' for commands, 'exit' to stop input.")
    try:
        while True:
            if process.poll() is not None:
                return process.returncode or 0
            try:
                line = await asyncio.wait_for(queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            if line == "":
                break
            if not _dispatch_control_command(line.strip(), client, parser):
                break
    finally:
        stop_event.set()
        if thread is None:
            loop.remove_reader(sys.stdin)

    return process.wait()


def handle_serve(base_url: str, timeout: float, pool_size: int) -> int:
    main_path = os.path.join(os.path.dirname(__file__), "contexgo", "main.py")
    env = os.environ.copy()
    env.update(_parse_host_port(base_url))
    process = subprocess.Popen(
        [sys.executable, main_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    pid = process.pid
    print(f"Started main.py (pid={pid})")
    stdout_thread = Thread(target=_pump_stream, args=(process.stdout, sys.stdout), daemon=True)
    stderr_thread = Thread(target=_pump_stream, args=(process.stderr, sys.stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    log_worker = None
    if websockets is None:
        print("websockets not installed; skip logStream subscription", file=sys.stderr)
    else:
        log_worker = LogSubscriptionWorker(base_url, timeout, datetime.now(timezone.utc))
        log_worker.start()

    try:
        client = GraphQLHTTPClient(base_url, pool_size=pool_size, timeout=timeout)
        return asyncio.run(_serve_control_loop(process, client))
    except KeyboardInterrupt:
        print("Forwarding SIGINT to main.py...", file=sys.stderr)
        process.send_signal(signal.SIGINT)
        return process.wait()
    finally:
        if log_worker:
            log_worker.stop()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"log-stream", "status-stream"}:
        if args.command == "log-stream":
            asyncio.run(handle_log_stream(args.url, args.timeout, args.max_age_seconds))
        else:
            asyncio.run(handle_status_stream(args.url, args.timeout))
        return

    if args.command == "serve":
        exit_code = handle_serve(args.url, args.timeout, args.pool_size)
        raise SystemExit(exit_code)

    client = GraphQLHTTPClient(args.url, pool_size=args.pool_size, timeout=args.timeout)

    if args.command == "sensors":
        handle_sensors(client)
    elif args.command == "toggle":
        handle_toggle(client, args.sensor_id, None)
    elif args.command == "start":
        handle_toggle(client, args.sensor_id, True)
    elif args.command == "stop":
        handle_toggle(client, args.sensor_id, False)
    elif args.command == "bulk-start":
        handle_bulk(client, args.sensor_ids, True)
    elif args.command == "bulk-stop":
        handle_bulk(client, args.sensor_ids, False)
    elif args.command == "register":
        handle_register(client, args.sensor_type, args.sensor_id, args.config)
    elif args.command == "unregister":
        handle_unregister(client, args.sensor_id)
    else:
        raise RuntimeError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
