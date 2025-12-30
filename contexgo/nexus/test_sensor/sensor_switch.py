"""Reusable sensor toggle control."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import flet as ft


@dataclass
class SensorViewModel:
    sensor_id: str
    name: str
    is_on: bool = False


ToggleHandler = Callable[[str, bool], Awaitable[None]]


class SensorSwitch(ft.UserControl):
    def __init__(
        self,
        model: SensorViewModel,
        *,
        on_toggle: Optional[ToggleHandler] = None,
    ) -> None:
        super().__init__()
        self.model = model
        self._on_toggle = on_toggle
        self._switch: ft.Switch | None = None
        self._status: ft.Text | None = None

    def build(self) -> ft.Control:
        self._status = ft.Text(self._status_text(self.model.is_on))
        self._switch = ft.Switch(value=self.model.is_on, on_change=self._handle_toggle)
        return ft.Container(
            padding=12,
            border=ft.border.all(1, ft.colors.OUTLINE_VARIANT),
            border_radius=8,
            content=ft.Row(
                controls=[
                    ft.Column(
                        [
                            ft.Text(self.model.name, weight=ft.FontWeight.BOLD),
                            self._status,
                        ],
                        expand=True,
                    ),
                    self._switch,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def set_state(self, is_on: bool) -> None:
        self.model.is_on = is_on
        if self._switch is not None:
            self._switch.value = is_on
        if self._status is not None:
            self._status.value = self._status_text(is_on)
        self.update()

    def _handle_toggle(self, event: ft.ControlEvent) -> None:
        new_state = bool(event.control.value)
        self.set_state(new_state)
        if self._on_toggle is None:
            return
        handler = self._on_toggle
        result = handler(self.model.sensor_id, new_state)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)

    @staticmethod
    def _status_text(is_on: bool) -> str:
        return "状态：开启" if is_on else "状态：关闭"
