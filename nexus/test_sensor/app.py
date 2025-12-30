"""Entry point for the sensor test UI."""
from __future__ import annotations

import flet as ft

from .page import main


def run() -> None:
    ft.app(target=main)


if __name__ == "__main__":
    run()
