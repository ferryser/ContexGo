# -*- coding: utf-8 -*-
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from contexgo.protocol.context import RawContextProperties


BASE_EVENT_PATH = Path("data") / "chronicle" / "event"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _ensure_event_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _resolve_event_path(object_id: str, create_time: Optional[datetime] = None) -> Path:
    event_time = create_time or datetime.now()
    date_bucket = event_time.strftime("%Y-%m-%d")
    event_dir = BASE_EVENT_PATH / date_bucket
    _ensure_event_dir(event_dir)
    return event_dir / f"{object_id}.jsonl"


def save_event(event: Dict[str, Any]) -> Path:
    object_id = event.get("object_id") or str(uuid.uuid4())
    create_time = event.get("create_time")
    if isinstance(create_time, str):
        try:
            create_time = datetime.fromisoformat(create_time)
        except ValueError:
            create_time = None
    event_path = _resolve_event_path(object_id, create_time=create_time)
    with event_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=_json_default))
        handle.write("\n")
    return event_path


def save_raw_context(raw: RawContextProperties) -> Path:
    if hasattr(raw, "model_dump"):
        payload = raw.model_dump()
    else:
        payload = raw.dict()  # type: ignore[call-arg]
    payload.setdefault("object_id", raw.object_id)
    payload.setdefault("create_time", raw.create_time)
    return save_event(payload)
