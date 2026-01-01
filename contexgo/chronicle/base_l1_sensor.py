# -*- coding: utf-8 -*-
import json
import time
import abc
import uuid_utils as uuid # 采用具备时间序的 v7 算法
from datetime import datetime
from typing import Any, Dict, List, Optional

from contexgo.chronicle.base import BaseCaptureComponent
from contexgo.chronicle.assembly.chronicle_gate import save_raw_context
from contexgo.protocol.context import RawContextProperties
from contexgo.protocol.enums import ContentFormat, ContextSource, ContextType
from contexgo.infra.logging_utils import get_logger

logger = get_logger(__name__)

class BaseL1Sensor(BaseCaptureComponent):
    """
    L1 协议标准感知器基类 (Refactored with UUIDv7)。
    """

    def __init__(self, name: str, description: str, source_type: ContextSource, 
                 l1_type: ContextType, content_format: ContentFormat = ContentFormat.TEXT):
        """
        初始化感知器。
        1 绑定 L1 协议类型枚举，避免字符串拼写错误。
        2 预置内容格式标签，解决信封外层元数据对齐问题。
        """
        super().__init__(name=name, description=description, source_type=source_type)
        self._l1_type = l1_type
        self._content_format = content_format
        self._device_id = "Default-Device"

    def _initialize_impl(self, config: Dict[str, Any]) -> bool:
            """
            从配置注入或自动生成设备物理标识。
            优先级：配置指定 > 硬件 MAC 映射 > 默认回退。
            """
            # 1. 尝试从配置获取
            device_id = config.get("device_id")
            # 2. 若配置缺失，则根据硬件 MAC 地址生成唯一 ID，确保分布式环境下的单真源属性
            if not device_id:
                try:
                    # 获取 48 位硬件地址并转化为十六进制字符串
                    node = uuid.getnode()
                    device_id = f"Node-{hex(node)[2:].upper()}"
                    logger.info(f"{self._name}: No device_id in config, auto-generated: {device_id}")
                except Exception:
                    device_id = "Unknown-Device"
                    logger.warning(f"{self._name}: Failed to get hardware ID, fallback to: {device_id}")
            self._device_id = device_id            
            # 3. 触发子类的硬件/模型初始化逻辑
            return self._init_sensor(config)

    def _capture_impl(self) -> List[RawContextProperties]:
        """
        捕获循环实现。
        强制执行内外 ID 一致性与物理时序对齐。
        """
        raw_payloads = self._collect_l1_payloads()
        if not raw_payloads:
            return []

        results = []
        for payload in raw_payloads:
            # 1 同步物理时间锚点：确保逻辑记录与物理发生时间无漂移
            now_ts = time.time()
            now_dt = datetime.fromtimestamp(now_ts)

            # 2 生成单调递增的 UUIDv7 并统一命名为 object_id
            event_id = str(uuid.uuid7())

            # 3 构造 L1 协议信封 (内部逻辑存根)
            l1_event = {
                "header": {
                    "object_id": event_id, # 更名：从 uuid 改为 object_id
                    "timestamp": now_ts,
                    "device_id": self._device_id,
                    "type": self._l1_type.value
                },
                "payload": payload
            }

            # 4 封装至外部集装箱 (物理通行证)
            results.append(RawContextProperties(
                object_id=event_id, # 内外标识强一致
                source=self._source_type,
                content_format=self._content_format, # 准确描述 Payload 的媒体属性
                content_text=json.dumps(l1_event, ensure_ascii=False),
                create_time=now_dt
            ))
        for raw in results:
            save_raw_context(raw)
        return results

    @abc.abstractmethod
    def _init_sensor(self, config: Dict[str, Any]) -> bool:
        """子类需实现具体的信号采集入口。"""
        pass

    @abc.abstractmethod
    def _collect_l1_payloads(self) -> List[Dict[str, Any]]:
        """子类需实现：返回原始业务数据列表。"""
        pass

    def _start_impl(self) -> bool:
        return True

    def _stop_impl(self, graceful: bool = True) -> bool:
        return True

    def _get_config_schema_impl(self) -> Dict[str, Any]:
        return {
            "properties": {
                "device_id": {"type": "string", "default": "Default-Device"}
            }
        }
