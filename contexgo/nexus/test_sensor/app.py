"""Entry point for the sensor test UI."""
from __future__ import annotations

import flet as ft

from contexgo.infra.config import is_test_mode
from contexgo.infra.logging_utils import get_logger, setup_logging

from .page import main

LOG_PATH = "data/logs/chronicle/test_sensor_ui.log"
logger = get_logger("nexus.test_sensor.app")


def run() -> None:
    setup_logging({"log_path": LOG_PATH, "level": "INFO"})
    if is_test_mode:
        logger.info("UI 启动")
    ft.app(target=main)


if __name__ == "__main__":
    run()
