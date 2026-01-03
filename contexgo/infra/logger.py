# -*- coding: utf-8 -*-
# 路径：contexgo/infra/logger.py

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger

LOG_BROADCAST_MAXSIZE = 50
log_broadcast: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=LOG_BROADCAST_MAXSIZE)
_log_broadcast_loop: Optional[asyncio.AbstractEventLoop] = None


def set_log_broadcast_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _log_broadcast_loop
    _log_broadcast_loop = loop


def _enqueue_log_broadcast(payload: Dict[str, Any]) -> None:
    try:
        log_broadcast.put_nowait(payload)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            log_broadcast.get_nowait()
            log_broadcast.task_done()
        with contextlib.suppress(asyncio.QueueFull):
            log_broadcast.put_nowait(payload)


def _broadcast_sink(message: Any) -> None:
    record = message.record
    timestamp = record["time"]
    if hasattr(timestamp, "datetime"):
        timestamp = timestamp.datetime
    payload = {
        "timestamp": timestamp,
        "level": record["level"].name,
        "message": record["message"],
        "name": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    loop = _log_broadcast_loop
    if loop and loop.is_running():
        loop.call_soon_threadsafe(_enqueue_log_broadcast, payload)
    else:
        _enqueue_log_broadcast(payload)

def _derive_log_path_from_script(script_path: str) -> str:
    script = Path(script_path).resolve()
    parts = script.parts
    if "contexgo" in parts:
        contexgo_index = parts.index("contexgo")
        relative_parts = parts[contexgo_index + 1 :]
        if len(relative_parts) >= 2:
            subdir = relative_parts[0]
            filename = Path(relative_parts[-1]).with_suffix(".log").name
            return str(Path("data/logs") / subdir / filename)
        if len(relative_parts) == 1:
            return str(Path("data/logs") / Path(relative_parts[0]).with_suffix(".log").name)
    return str(Path("data/logs") / script.with_suffix(".log").name)


def _normalize_data_logs_path(path: Path) -> Path:
    parts = path.parts
    for idx, part in enumerate(parts):
        if part == "data" and idx + 1 < len(parts) and parts[idx + 1] == "logs":
            relative_parts = parts[idx + 2 :]
            if len(relative_parts) >= 2:
                return Path("data/logs") / relative_parts[0] / Path(relative_parts[-1]).name
            if len(relative_parts) == 1:
                return Path("data/logs") / relative_parts[0]
            return Path("data/logs/main.log")
    return Path("data/logs") / path.name


def _resolve_log_path(config: Dict[str, Any]) -> str:
    script_path = config.get("script_path")
    if script_path:
        return _derive_log_path_from_script(script_path)

    log_path = config.get("log_path")
    if log_path:
        candidate = Path(log_path)
        return str(_normalize_data_logs_path(candidate))

    return str(Path("data/logs/main.log"))


class LogManager:
    """
    ContexGo 日志管理器：负责控制台和文件的多路输出配置
    """
    def __init__(self):
        # 清除 Loguru 默认的控制台处理器
        logger.remove()

    def configure(self, config: Dict[str, Any]) -> None:
        """
        根据配置动态调整日志行为
        """
        level = config.get("level", "INFO")

        # 1. 配置控制台高亮输出
        console_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.add(sys.stderr, level=level, format=console_format)

        # 2. 配置物理文件持久化
        log_path = _resolve_log_path(config)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # 3. 配置日志广播队列
        logger.add(_broadcast_sink, level=level, enqueue=True)

        # 滚动配置：单文件 5MB，保留 5 个历史文件
        logger.add(
            log_path,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="5 MB",
            retention=5,
            encoding="utf-8",
            enqueue=True  # 核心：确保多线程 Sensor 写入安全
        )

    def get_logger(self):
        return logger

# 实例化全局管理器
log_manager = LogManager()
# 直接暴露 logger 供快捷调用
log = logger
