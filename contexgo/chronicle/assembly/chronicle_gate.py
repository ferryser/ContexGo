# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from contexgo.protocol.base_chronicle import BaseChronicle
from contexgo.protocol.context import RawContextProperties


BASE_CHRONICLE_PATH = Path("data") / "chronicle"
EVENT_DIR = "event"
META_DIR = "metadata"
BLOB_DIR = "blob"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _resolve_date_bucket(base_path: Path, create_time: Optional[datetime]) -> Path:
    event_time = create_time or datetime.now()
    date_bucket = event_time.strftime("%Y-%m-%d")
    return base_path / date_bucket


def _resolve_event_path(
    base_path: Path, object_id: str, create_time: Optional[datetime] = None
) -> Path:
    event_dir = _resolve_date_bucket(base_path, create_time)
    _ensure_dir(event_dir)
    return event_dir / f"{object_id}.jsonl"


def _resolve_metadata_path(
    base_path: Path, object_id: str, create_time: Optional[datetime] = None
) -> Path:
    metadata_dir = _resolve_date_bucket(base_path, create_time)
    _ensure_dir(metadata_dir)
    return metadata_dir / f"{object_id}.json"


def _resolve_blob_path(
    base_path: Path, object_id: str, extension: str, create_time: Optional[datetime] = None
) -> Path:
    blob_dir = _resolve_date_bucket(base_path, create_time)
    _ensure_dir(blob_dir)
    safe_ext = extension.lstrip(".") if extension else "bin"
    return blob_dir / f"{object_id}.{safe_ext}"


def save_event(event: Dict[str, Any], base_path: Optional[Path] = None) -> Path:
    base = base_path or (BASE_CHRONICLE_PATH / EVENT_DIR)
    object_id = event.get("object_id") or str(uuid.uuid4())
    create_time = _parse_create_time(event.get("create_time"))
    event_path = _resolve_event_path(base, object_id, create_time=create_time)
    with event_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=_json_default))
        handle.write("\n")
    return event_path


def save_raw_context(raw: RawContextProperties, base_path: Optional[Path] = None) -> Path:
    if hasattr(raw, "model_dump"):
        payload = raw.model_dump()
    else:
        payload = raw.dict()  # type: ignore[call-arg]
    payload.setdefault("object_id", raw.object_id)
    payload.setdefault("create_time", raw.create_time)
    return save_event(payload, base_path=base_path)


def _parse_create_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


@dataclass
class BlobPayload:
    payload: Dict[str, Any]
    blob_bytes: bytes
    blob_extension: str


class ChronicleGate(BaseChronicle):
    """Chronicle gate with async CRUD and GraphQL-ready adapters."""

    def __init__(self, base_path: Optional[Path] = None) -> None:
        self._base_path = base_path or BASE_CHRONICLE_PATH
        self._event_base = self._base_path / EVENT_DIR
        self._metadata_base = self._base_path / META_DIR
        self._blob_base = self._base_path / BLOB_DIR
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task[None]] = None

    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._is_event(payload):
            await self._enqueue_event(payload)
            return payload
        await self._write_metadata(payload)
        return payload

    async def read_by_id(self, object_id: str) -> Optional[Dict[str, Any]]:
        for file_path in self._iter_event_files():
            if file_path.stem == object_id:
                return self._load_json(file_path)
        for file_path in self._iter_metadata_files():
            if file_path.stem == object_id:
                return self._load_json(file_path)
        return None

    async def read_by_time_range(
        self, start_ts: float, end_ts: float
    ) -> Iterable[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        start_time = datetime.fromtimestamp(start_ts)
        end_time = datetime.fromtimestamp(end_ts)
        for file_path in self._iter_event_files():
            record = self._load_json(file_path)
            if self._is_time_in_range(record, start_time, end_time):
                results.append(record)
        for file_path in self._iter_metadata_files():
            record = self._load_json(file_path)
            if self._is_time_in_range(record, start_time, end_time):
                results.append(record)
        return results

    async def read_by_type(self, context_type: str) -> Iterable[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        for file_path in self._iter_event_files():
            record = self._load_json(file_path)
            if self._record_matches_type(record, context_type):
                results.append(record)
        for file_path in self._iter_metadata_files():
            record = self._load_json(file_path)
            if self._record_matches_type(record, context_type):
                results.append(record)
        return results

    async def update(self, object_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload.copy()
        payload["object_id"] = object_id
        if self._is_event(payload):
            await self._enqueue_event(payload)
            return payload
        await self._write_metadata(payload)
        return payload

    async def delete(self, object_id: str) -> bool:
        deleted = False
        for file_path in list(self._iter_event_files()):
            if file_path.stem == object_id:
                file_path.unlink(missing_ok=True)
                deleted = True
        for file_path in list(self._iter_metadata_files()):
            if file_path.stem == object_id:
                file_path.unlink(missing_ok=True)
                deleted = True
        for file_path in list(self._iter_blob_files()):
            if file_path.stem == object_id:
                file_path.unlink(missing_ok=True)
                deleted = True
        return deleted

    async def shutdown(self) -> None:
        if self._writer_task and not self._writer_task.done():
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task

    def _is_event(self, payload: Dict[str, Any]) -> bool:
        content_type = payload.get("content_type") or payload.get("context_type")
        return str(content_type).lower() == "event"

    async def _enqueue_event(self, payload: Dict[str, Any]) -> None:
        self._ensure_writer_task()
        await self._queue.put(payload)

    def _ensure_writer_task(self) -> None:
        if self._writer_task and not self._writer_task.done():
            return
        loop = asyncio.get_running_loop()
        self._writer_task = loop.create_task(self._writer_loop())

    async def _writer_loop(self) -> None:
        while True:
            payload = await self._queue.get()
            try:
                self._write_event(payload)
            finally:
                self._queue.task_done()

    def _write_event(self, payload: Dict[str, Any]) -> Path:
        blob_payload = self._extract_blob(payload)
        if blob_payload:
            payload = blob_payload.payload
            payload["content_path"] = self._write_blob(blob_payload)
        return save_event(payload, base_path=self._event_base)

    async def _write_metadata(self, payload: Dict[str, Any]) -> Path:
        blob_payload = self._extract_blob(payload)
        if blob_payload:
            payload = blob_payload.payload
            payload["content_path"] = self._write_blob(blob_payload)
        object_id = payload.get("object_id") or str(uuid.uuid4())
        payload["object_id"] = object_id
        create_time = _parse_create_time(payload.get("create_time"))
        metadata_path = _resolve_metadata_path(
            self._metadata_base, object_id, create_time=create_time
        )
        with metadata_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
        return metadata_path

    def _write_blob(self, blob_payload: BlobPayload) -> str:
        object_id = blob_payload.payload.get("object_id") or str(uuid.uuid4())
        blob_payload.payload["object_id"] = object_id
        create_time = _parse_create_time(blob_payload.payload.get("create_time"))
        blob_path = _resolve_blob_path(
            self._blob_base,
            object_id,
            blob_payload.blob_extension,
            create_time=create_time,
        )
        with blob_path.open("wb") as handle:
            handle.write(blob_payload.blob_bytes)
        return str(blob_path)

    def _extract_blob(self, payload: Dict[str, Any]) -> Optional[BlobPayload]:
        if "content_bytes" not in payload:
            return None
        blob_bytes = payload.get("content_bytes")
        if not isinstance(blob_bytes, (bytes, bytearray)):
            return None
        extension = payload.get("content_ext") or payload.get("content_type") or "bin"
        safe_payload = payload.copy()
        safe_payload.pop("content_bytes", None)
        safe_payload.pop("content_ext", None)
        return BlobPayload(
            payload=safe_payload,
            blob_bytes=bytes(blob_bytes),
            blob_extension=str(extension),
        )

    def _iter_event_files(self) -> Iterable[Path]:
        if not self._event_base.exists():
            return []
        return self._event_base.glob("**/*.jsonl")

    def _iter_metadata_files(self) -> Iterable[Path]:
        if not self._metadata_base.exists():
            return []
        return self._metadata_base.glob("**/*.json")

    def _iter_blob_files(self) -> Iterable[Path]:
        if not self._blob_base.exists():
            return []
        return self._blob_base.glob("**/*.*")

    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        with file_path.open("r", encoding="utf-8") as handle:
            line = handle.readline()
            return json.loads(line) if line else {}

    @staticmethod
    def _record_matches_type(record: Dict[str, Any], context_type: str) -> bool:
        record_type = record.get("context_type") or record.get("content_type")
        return str(record_type).lower() == str(context_type).lower()

    @staticmethod
    def _is_time_in_range(
        record: Dict[str, Any], start_time: datetime, end_time: datetime
    ) -> bool:
        create_time = _parse_create_time(record.get("create_time"))
        if not create_time:
            return False
        return start_time <= create_time <= end_time
