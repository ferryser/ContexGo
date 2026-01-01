"""Entry point for the sensor test UI."""
from __future__ import annotations

import flet as ft

from contexgo.infra.config import is_test_mode
from contexgo.infra.logging_utils import build_log_config, get_logger, setup_logging

from .page import main

logger = get_logger("nexus.test_sensor.app")


def run() -> None:
    setup_logging(build_log_config(__file__, level="INFO"))
    if is_test_mode:
        logger.info("UI 启动")
    ft.app(target=main)


if __name__ == "__main__":
    run()
