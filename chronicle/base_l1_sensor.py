# -*- coding: utf-8 -*-
import json
import uuid
import time
import abc
from datetime import datetime
from typing import Any, Dict, List, Optional

from ContexGo.chronicle.base import BaseCaptureComponent
from ContexGo.protocol.context import RawContextProperties
from ContexGo.protocol.enums import ContentFormat, ContextSource, ContextType
from ContexGo.infra.logging_utils import get_logger

logger = get_logger(__name__)

class BaseL1Sensor(BaseCaptureComponent):
    """
    L1 协议标准感知器基类 (Refactored)。
    """

    def __init__(self, name: str, description: str, source_type: ContextSource, 
                 l1_type: ContextType, content_format: ContentFormat = ContentFormat.TEXT):
        """
        初始化感知器。
        1. 绑定 L1 协议类型枚举，避免字符串硬编码。
        2. 显式指定内容格式标签，解决信封对齐问题。
        """
        super().__init__(name=name, description=description, source_type=source_type)
        self._l1_type = l1_type
        self._content_format = content_format
        self._device_id = "Default-Device"

    def _initialize_impl(self, config: Dict[str, Any]) -> bool:
        """解析配置并触发子类初始化。"""
        self._device_id = config.get("device_id", "Default-Device")
        return self._init_sensor(config)

    def _capture_impl(self) -> List[RawContextProperties]:
        """
        捕获循环实现。
        针对 ID 冗余、时钟漂移及语义对齐进行了重构。
        """
        try:
            raw_payloads = self._collect_l1_payloads()
            if not raw_payloads:
                return []
            
            results = []
            for payload in raw_payloads:
                # [改动点 1] 物理时间锚点同步：确保 Header 与容器使用同一时间戳
                now_ts = time.time()
                now_dt = datetime.fromtimestamp(now_ts)
                
                # [改动点 2] ID 统一：预生成 UUID 用于内外双层标识
                event_uuid = str(uuid.uuid4())

                # 构造 L1 协议信封 (内部语义层)
                l1_event = {
                    "header": {
                        "uuid": event_uuid,
                        "timestamp": now_ts,
                        "device_id": self._device_id,
                        "type": self._l1_type.value # 使用枚举值
                    },
                    "payload": payload
                }
                
                # 封装至内核交换格式 (外部传输层)
                results.append(RawContextProperties(
                    object_id=event_uuid, # [改动点 3] 强行对齐内外 ID
                    source=self._source_type,
                    content_format=self._content_format, # [改动点 4] 注入准确的语义标签
                    content_text=json.dumps(l1_event, ensure_ascii=False),
                    create_time=now_dt
                ))
            return results
        except Exception as e:
            logger.error(f"{self._name} capture failure: {str(e)}")
            return []

    @abc.abstractmethod
    def _init_sensor(self, config: Dict[str, Any]) -> bool:
        """子类需实现具体的硬件/接口初始化。"""
        pass

    @abc.abstractmethod
    def _collect_l1_payloads(self) -> List[Dict[str, Any]]:
        """子类需实现：返回业务 Payload。"""
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