# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import contextlib
import json
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from contexgo.protocol.base_chronicle import BaseChronicle
from contexgo.protocol.context import RawContextProperties

BASE_CHRONICLE_PATH = Path("data") / "chronicle"
BLOB_DIR_NAME = "blobs"
TABLE_NAME = "chronicle"

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    source TEXT,
    content TEXT,
    blob_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_chronicle_timestamp ON {TABLE_NAME}(timestamp);
CREATE INDEX IF NOT EXISTS idx_chronicle_source ON {TABLE_NAME}(source);
"""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _normalize_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        with contextlib.suppress(ValueError):
            return float(value)
    return time.time()


def _uuid7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    uuid_int = (timestamp_ms << 80) | (0x7 << 76) | (rand_a << 64)
    uuid_int |= (0x2 << 62) | rand_b
    return str(uuid.UUID(int=uuid_int))


def _resolve_month_db_path(base_path: Path, ts: float) -> Path:
    dt = datetime.fromtimestamp(ts)
    year = dt.strftime("%Y")
    month = dt.strftime("%m")
    return base_path / year / f"{year}{month}.db"


def _resolve_blob_path(base_path: Path, ts: float, object_id: str, extension: str) -> Path:
    dt = datetime.fromtimestamp(ts)
    year = dt.strftime("%Y")
    day_bucket = dt.strftime("%m-%d")
    blob_dir = base_path / year / BLOB_DIR_NAME / day_bucket
    _ensure_dir(blob_dir)
    safe_ext = extension.lstrip(".") if extension else "jpg"
    return blob_dir / f"{object_id}.{safe_ext}"


def initialize_chronicle_db(db_path: Path) -> None:
    _ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _serialize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


_DEFAULT_GATE: Optional["ChronicleGate"] = None


def _get_default_gate(base_path: Optional[Path] = None) -> "ChronicleGate":
    global _DEFAULT_GATE
    target_base = base_path or BASE_CHRONICLE_PATH
    if _DEFAULT_GATE is None or _DEFAULT_GATE._base_path != target_base:
        _DEFAULT_GATE = ChronicleGate(base_path=target_base)
    return _DEFAULT_GATE


def save_event(event: Dict[str, Any], base_path: Optional[Path] = None) -> Path:
    gate = _get_default_gate(base_path)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        temp_gate = ChronicleGate(base_path=base_path or BASE_CHRONICLE_PATH)
        payload = temp_gate._prepare_payload(dict(event))
        try:
            temp_gate._write_batch([payload])
        finally:
            temp_gate._close_connections()
        return Path()
    loop.create_task(gate.append(event))
    return Path()


def save_raw_context(raw: RawContextProperties, base_path: Optional[Path] = None) -> Path:
    if hasattr(raw, "model_dump"):
        payload = raw.model_dump()
    else:
        payload = raw.dict()  # type: ignore[call-arg]
    payload.setdefault("source", payload.get("context_type"))
    if payload.get("create_time") is not None:
        payload["timestamp"] = payload.get("create_time")
    payload["id"] = payload.get("object_id")
    return save_event(payload, base_path=base_path)


async def shutdown_default_gate() -> None:
    gate = _DEFAULT_GATE
    if gate is None:
        return
    await gate.shutdown()


@dataclass
class ChronicleRecord:
    object_id: str
    timestamp: float
    source: Optional[str]
    content: str
    blob_path: Optional[str]


class ChronicleGate(BaseChronicle):
    """Chronicle gate with async batch insert and month routing."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        flush_interval: float = 2.0,
        max_batch_size: int = 200,
    ) -> None:
        self._base_path = base_path or BASE_CHRONICLE_PATH
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task[None]] = None
        self._flush_interval = max(1.0, min(flush_interval, 5.0))
        self._max_batch_size = max(1, max_batch_size)
        self._connections: Dict[Path, sqlite3.Connection] = {}

    async def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_writer_task()
        payload = self._prepare_payload(payload)
        await self._queue.put(payload)
        return payload

    async def append_many(self, payloads: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        self._ensure_writer_task()
        for payload in payloads:
            payload = self._prepare_payload(payload)
            await self._queue.put(payload)
        return payloads

    async def read_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._read_by_id_sync, object_id)

    async def read_by_time_range(
        self, start_ts: float, end_ts: float
    ) -> Iterable[Dict[str, Any]]:
        return await asyncio.to_thread(self._read_by_time_range_sync, start_ts, end_ts)

    async def read_by_source(self, source: str) -> Iterable[Dict[str, Any]]:
        return await asyncio.to_thread(self._read_by_source_sync, source)

    async def flush(self) -> None:
        await self._queue.join()

    async def shutdown(self) -> None:
        await self.flush()
        if self._writer_task and not self._writer_task.done():
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
        self._close_connections()

    def _ensure_writer_task(self) -> None:
        if self._writer_task and not self._writer_task.done():
            return
        loop = asyncio.get_running_loop()
        self._writer_task = loop.create_task(self._writer_loop())

    async def _writer_loop(self) -> None:
        while True:
            payload = await self._queue.get()
            batch = [payload]
            start_time = asyncio.get_running_loop().time()
            while len(batch) < self._max_batch_size:
                remaining = self._flush_interval - (
                    asyncio.get_running_loop().time() - start_time
                )
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                batch.append(item)
            try:
                self._write_batch(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        grouped: Dict[Path, List[ChronicleRecord]] = {}
        for payload in batch:
            record = self._prepare_record(payload)
            db_path = _resolve_month_db_path(self._base_path, record.timestamp)
            grouped.setdefault(db_path, []).append(record)

        for db_path, records in grouped.items():
            conn = self._get_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            cursor.executemany(
                f"""
                INSERT INTO {TABLE_NAME} (id, timestamp, source, content, blob_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.object_id,
                        record.timestamp,
                        record.source,
                        record.content,
                        record.blob_path,
                    )
                    for record in records
                ],
            )
            conn.commit()

    def _prepare_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in payload and "object_id" not in payload:
            payload["id"] = _uuid7()
        payload.setdefault(
            "timestamp",
            _normalize_timestamp(payload.get("timestamp") or payload.get("create_time")),
        )
        return payload

    def _prepare_record(self, payload: Dict[str, Any]) -> ChronicleRecord:
        object_id = payload.get("id") or payload.get("object_id") or _uuid7()
        timestamp = _normalize_timestamp(payload.get("timestamp") or payload.get("create_time"))
        source = payload.get("source") or payload.get("context_type")
        content = _serialize_content(payload.get("content") or payload.get("content_text"))

        blob_path = None
        blob_bytes = payload.get("blob_bytes") or payload.get("content_bytes")
        if isinstance(blob_bytes, (bytes, bytearray)):
            extension = payload.get("blob_ext") or payload.get("content_ext") or "jpg"
            blob_path = self._write_blob(timestamp, object_id, bytes(blob_bytes), extension)
        return ChronicleRecord(
            object_id=str(object_id),
            timestamp=timestamp,
            source=str(source) if source is not None else None,
            content=content,
            blob_path=blob_path,
        )

    def _write_blob(self, timestamp: float, object_id: str, data: bytes, extension: str) -> str:
        blob_path = _resolve_blob_path(self._base_path, timestamp, object_id, extension)
        with blob_path.open("wb") as handle:
            handle.write(data)
        rel_path = blob_path.relative_to(self._base_path)
        return str(rel_path)

    def _get_connection(self, db_path: Path) -> sqlite3.Connection:
        if db_path in self._connections:
            return self._connections[db_path]
        initialize_chronicle_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        self._connections[db_path] = conn
        return conn

    def _close_connections(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()

    def _read_by_id_sync(self, object_id: str) -> Optional[Dict[str, Any]]:
        for db_path in self._iter_db_paths():
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    f"SELECT id, timestamp, source, content, blob_path FROM {TABLE_NAME} WHERE id = ?",
                    (object_id,),
                ).fetchone()
            finally:
                conn.close()
            if row:
                return self._row_to_payload(row)
        return None

    def _read_by_time_range_sync(self, start_ts: float, end_ts: float) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for db_path in self._iter_db_paths_in_range(start_ts, end_ts):
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    f"""
                    SELECT id, timestamp, source, content, blob_path
                    FROM {TABLE_NAME}
                    WHERE timestamp BETWEEN ? AND ?
                    ORDER BY timestamp ASC
                    """,
                    (start_ts, end_ts),
                ).fetchall()
            finally:
                conn.close()
            results.extend(self._row_to_payload(row) for row in rows)
        return results

    def _read_by_source_sync(self, source: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for db_path in self._iter_db_paths():
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    f"""
                    SELECT id, timestamp, source, content, blob_path
                    FROM {TABLE_NAME}
                    WHERE source = ?
                    ORDER BY timestamp ASC
                    """,
                    (source,),
                ).fetchall()
            finally:
                conn.close()
            results.extend(self._row_to_payload(row) for row in rows)
        return results

    def _iter_db_paths(self) -> Iterable[Path]:
        if not self._base_path.exists():
            return []
        db_paths: List[Path] = []
        for year_dir in self._base_path.iterdir():
            if not year_dir.is_dir():
                continue
            db_paths.extend(sorted(year_dir.glob("*.db")))
        return db_paths

    def _iter_db_paths_in_range(self, start_ts: float, end_ts: float) -> Iterable[Path]:
        start_dt = datetime.fromtimestamp(start_ts)
        end_dt = datetime.fromtimestamp(end_ts)
        current = datetime(start_dt.year, start_dt.month, 1)
        end_marker = datetime(end_dt.year, end_dt.month, 1)
        db_paths: List[Path] = []
        while current <= end_marker:
            ts = current.timestamp()
            db_paths.append(_resolve_month_db_path(self._base_path, ts))
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        return [path for path in db_paths if path.exists()]

    @staticmethod
    def _row_to_payload(row: sqlite3.Row | tuple) -> Dict[str, Any]:
        return {
            "id": row[0],
            "timestamp": row[1],
            "source": row[2],
            "content": row[3],
            "blob_path": row[4],
        }
