"""Flet entry page for sensor monitoring."""
from __future__ import annotations

import asyncio
import os
from typing import Dict, List

import flet as ft

from contexgo.infra.config import is_test_mode
from contexgo.infra.logging_utils import build_log_config, get_logger, setup_logging

from .api_client import GraphQLClient
from .sensor_switch import SensorSwitch, SensorViewModel

logger = get_logger("nexus.test_sensor.page")

SENSORS_QUERY = """
query Sensors {
  sensors {
    id
    name
    isOn
  }
}
"""

TOGGLE_SENSOR_MUTATION = """
mutation ToggleSensor($sensorId: ID!, $enable: Boolean!) {
  toggleSensor(sensorId: $sensorId, enable: $enable) {
    statusCode
    message
    sensors {
      id
      isOn
    }
  }
}
"""

SENSOR_STATUS_SUBSCRIPTION = """
subscription SensorStatus {
  sensorStatus {
    sensorId
    status
    message
  }
}
"""


class SensorDashboard:
    def __init__(self, page: ft.Page, client: GraphQLClient) -> None:
        self.page = page
        self.client = client
        self._switches: Dict[str, SensorSwitch] = {}
        self._list_view = ft.ListView(expand=True, spacing=12)
        self._status = ft.Text("正在初始化...")
        self._all_on_button = ft.ElevatedButton(
            "全部启动", on_click=self._handle_all_on_click
        )

    @property
    def view(self) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("传感器控制台", style=ft.TextThemeStyle.TITLE_LARGE),
                        self._all_on_button,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self._list_view,
                self._status,
            ],
            expand=True,
            spacing=16,
        )

    async def load_sensors(self) -> None:
        if is_test_mode:
            logger.info("加载传感器列表: 请求开始")
        try:
            response = await self.client.query(SENSORS_QUERY)
            sensors = response.data.get("sensors", [])

            self._list_view.controls.clear()
            self._switches.clear()

            for sensor in sensors:
                model = SensorViewModel(
                    sensor_id=str(sensor["id"]),
                    name=str(sensor["name"]),
                    is_on=bool(sensor.get("isOn")),
                )
                switch = SensorSwitch(model, on_toggle=self._handle_toggle)
                self._switches[model.sensor_id] = switch
                self._list_view.controls.append(switch)

            if not sensors:
                self._status.value = "暂无传感器数据。"
                if is_test_mode:
                    logger.info("加载传感器列表: 返回空列表")
            else:
                self._status.value = f"已加载 {len(sensors)} 个传感器。"
                if is_test_mode:
                    logger.info("加载传感器列表: 返回数量=%s", len(sensors))

            # 确保 UI 强制刷新
            self.page.update()
            if is_test_mode:
                logger.info("加载传感器列表: 请求结束")
        except Exception as e:
            self._status.value = f"加载失败: {e}"
            if is_test_mode:
                logger.exception("加载传感器列表失败")
            self.page.update()

    async def subscribe_updates(self) -> None:
        if is_test_mode:
            logger.info("订阅传感器状态更新: 启动")
        try:
            async for payload in self.client.subscribe(SENSOR_STATUS_SUBSCRIPTION):
                update = payload.get("data", {}).get("sensorStatus")
                if not update:
                    if is_test_mode:
                        logger.info("订阅传感器状态更新: 收到空数据")
                    continue
                sensor_id = str(update.get("sensorId"))
                status = str(update.get("status", ""))
                message = str(update.get("message", ""))
                is_on = status.lower() == "running"
                if is_test_mode:
                    logger.info(
                        "订阅传感器状态更新: sensor_id=%s status=%s message=%s",
                        sensor_id,
                        status,
                        message,
                    )
                self._apply_state(sensor_id, is_on, message=message)
        except Exception as e:
            self._status.value = f"订阅中断: {e}"
            if is_test_mode:
                logger.exception("订阅中断")
            self.page.update()

    async def poll_sensors(self) -> None:
        if is_test_mode:
            logger.info("轮询传感器状态: 启动")
        while True:
            if is_test_mode:
                logger.info("轮询传感器状态: 请求开始")
            try:
                response = await self.client.query(SENSORS_QUERY)
                sensors = response.data.get("sensors", [])
                self._sync_sensors(sensors)
                if not sensors:
                    self._status.value = "暂无传感器数据。"
                    if is_test_mode:
                        logger.info("轮询传感器状态: 返回空列表")
                else:
                    self._status.value = f"已刷新 {len(sensors)} 个传感器。"
                    if is_test_mode:
                        logger.info("轮询传感器状态: 返回数量=%s", len(sensors))
                self.page.update()
                if is_test_mode:
                    logger.info("轮询传感器状态: 请求结束")
            except Exception as exc:
                self._status.value = f"轮询失败: {exc}"
                if is_test_mode:
                    logger.exception("轮询失败")
                self.page.update()
            await asyncio.sleep(1)

    async def _handle_toggle(self, sensor_id: str, enabled: bool) -> None:
        if is_test_mode:
            logger.info("发送开关请求: sensor_id=%s enable=%s", sensor_id, enabled)
        try:
            await self.client.mutate(
                TOGGLE_SENSOR_MUTATION,
                variables={"sensorId": sensor_id, "enable": enabled},
            )
        except Exception as exc:
            self._status.value = f"开关请求失败: {exc}"
            self.page.update()

    def _apply_state(self, sensor_id: str, is_on: bool, *, message: str = "") -> None:
        switch = self._switches.get(sensor_id)
        if switch is None:
            if is_test_mode:
                logger.info("传感器状态更新被忽略: 未找到 sensor_id=%s", sensor_id)
            return
        switch.set_state(is_on)
        if message:
            self._status.value = f"传感器 {switch.model.name}: {message}"
        else:
            self._status.value = f"传感器 {switch.model.name} 状态已更新。"
        self.page.update()

    def _sync_sensors(self, sensors: list[dict]) -> None:
        new_ids = {str(sensor["id"]) for sensor in sensors}
        old_ids = set(self._switches.keys())

        for sensor_id in old_ids - new_ids:
            switch = self._switches.pop(sensor_id, None)
            if switch:
                self._list_view.controls.remove(switch)

        for sensor in sensors:
            sensor_id = str(sensor["id"])
            is_on = bool(sensor.get("isOn"))
            if sensor_id in self._switches:
                self._switches[sensor_id].set_state(is_on)
            else:
                model = SensorViewModel(
                    sensor_id=sensor_id,
                    name=str(sensor["name"]),
                    is_on=is_on,
                )
                switch = SensorSwitch(model, on_toggle=self._handle_toggle)
                self._switches[model.sensor_id] = switch
                self._list_view.controls.append(switch)

    def _handle_all_on_click(self, _: ft.ControlEvent) -> None:
        asyncio.create_task(self.set_all(True))

    async def set_all(self, enabled: bool) -> None:
        tasks: List[asyncio.Task] = []
        for sensor_id in self._switches:
            tasks.append(
                asyncio.create_task(
                    self.client.mutate(
                        TOGGLE_SENSOR_MUTATION,
                        variables={"sensorId": sensor_id, "enable": enabled},
                    )
                )
            )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _build_client() -> GraphQLClient:
    http_url = os.getenv("GRAPHQL_HTTP_URL", "http://localhost:35011/graphql")
    ws_url = os.getenv("GRAPHQL_WS_URL", "ws://localhost:35011/graphql")
    return GraphQLClient(http_url=http_url, ws_url=ws_url)


async def main(page: ft.Page) -> None:
    page.title = "Sensor Dashboard"
    page.padding = 24
    
    # 显式设置页面主题和亮度，防止某些版本默认透明
    page.theme_mode = ft.ThemeMode.LIGHT
    
    client = _build_client()
    dashboard = SensorDashboard(page, client)
    
    # 先添加视图框架，确保页面不是空的
    page.add(dashboard.view)
    page.update()

    # 数据初始化逻辑
    async def startup():
        await dashboard.load_sensors()
        # 确保数据加载后再次更新 UI
        page.update()
        # 并行启动轮询和订阅任务
        page.run_task(dashboard.poll_sensors)
        page.run_task(dashboard.subscribe_updates)

    def shutdown(_: ft.ControlEvent) -> None:
        asyncio.create_task(client.close())

    page.on_close = shutdown
    
    # 使用 run_task 启动主初始化逻辑
    page.run_task(startup)


if __name__ == "__main__":
    setup_logging(build_log_config(__file__, level="INFO"))
    ft.app(target=main)
