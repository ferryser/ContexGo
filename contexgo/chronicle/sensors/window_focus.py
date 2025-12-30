# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import importlib.util
from ctypes import wintypes
from typing import Any, Dict, List, Optional

from contexgo.chronicle.base_l1_sensor import BaseL1Sensor
from contexgo.chronicle.assembly.event_gate import save_raw_context
from contexgo.infra.config import get_sys_type, is_test_mode
from contexgo.infra.logging_utils import get_logger, setup_logging
from contexgo.protocol.enums import ContentFormat, ContextSource, ContextType

setup_logging({"log_path": "data/logs/window_focus.log"})
logger = get_logger(__name__)


class WindowFocusSensor(BaseL1Sensor):
    """Capture foreground window focus changes on Windows."""

    def __init__(self) -> None:
        super().__init__(
            name="WindowFocusSensor",
            description="Capture foreground window focus metadata",
            source_type=ContextSource.WINDOW_FOCUS,
            l1_type=ContextType.WINDOW_FOCUS,
            content_format=ContentFormat.TEXT,
        )
        self._is_windows = False
        self._use_stub = False
        self._last_window_handle: Optional[int] = None

    def _init_sensor(self, config: Dict[str, Any]) -> bool:
        sys_type = get_sys_type()
        if sys_type != "windows":
            logger.warning("WindowFocusSensor only supports Windows; current=%s", sys_type)
            return False
        self._is_windows = True

        if is_test_mode:
            logger.info("WindowFocusSensor running in test mode; hooks disabled")
            self._use_stub = True
            return True

        logger.info("WindowFocusSensor initialized for Windows foreground window polling")
        return True

    def _capture_impl(self) -> List[Any]:
        raw_payloads = super()._capture_impl()
        for raw in raw_payloads:
            save_raw_context(raw)
        return raw_payloads

    def _collect_l1_payloads(self) -> List[Dict[str, Any]]:
        if not self._is_windows:
            return []
        if self._use_stub:
            return [
                {
                    "app_name": "StubApp",
                    "window_title": "Stub Window Title",
                    "url": None,
                    "process_id": 1234,
                }
            ]

        window_info = self._get_foreground_window_info()
        if not window_info:
            return []
        if window_info.get("window_handle") == self._last_window_handle:
            return []
        self._last_window_handle = window_info.get("window_handle")

        payload = {
            "app_name": window_info.get("app_name"),
            "window_title": window_info.get("window_title"),
            "url": window_info.get("url"),
            "process_id": window_info.get("process_id"),
        }
        return [payload]

    def _get_foreground_window_info(self) -> Optional[Dict[str, Any]]:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None

        title_length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(title_length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, title_length + 1)
        window_title = buffer.value

        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        pid = int(process_id.value)

        app_name = self._resolve_process_name(pid)

        return {
            "window_handle": int(hwnd),
            "window_title": window_title,
            "process_id": pid,
            "app_name": app_name,
            "url": None,
        }

    @staticmethod
    def _resolve_process_name(pid: int) -> str:
        spec = importlib.util.find_spec("psutil")
        if spec is None:
            return str(pid)
        import psutil

        process = psutil.Process(pid)
        return process.name()
