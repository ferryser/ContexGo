import json
import uuid
import time
import abc
from datetime import datetime
from typing import Any, Dict, List, Optional

from opencontext.context_capture.base import BaseCaptureComponent
from opencontext.models.context import RawContextProperties
from opencontext.models.enums import ContentFormat, ContextSource
from ContexGo.infra.logging_utils import get_logger

logger = get_logger(__name__)

class BaseL1Sensor(BaseCaptureComponent):
    """
    L1 协议标准感知器基类。
    集成物理线程调度与 L1 Event Schema 协议封包逻辑。
    """

    def __init__(self, name: str, description: str, source_type: ContextSource, l1_type: str):
        """
        初始化感知器。
        1. 调用底座基类初始化线程与状态变量。
        2. 绑定 L1 协议类型标识。
        """
        super().__init__(name=name, description=description, source_type=source_type)
        self._l1_type = l1_type
        self._device_id = "Default-Device"

    def _initialize_impl(self, config: Dict[str, Any]) -> bool:
        """
        初始化实现。
        1. 解析全局配置中的 device_id。
        2. 触发子类的硬件/模型初始化逻辑。
        """
        self._device_id = config.get("device_id", "Default-Device")
        return self._init_sensor(config)

    def _capture_impl(self) -> List[RawContextProperties]:
        """
        捕获循环实现。
        1. 调用子类实现的信号采集逻辑，获取 Payload 列表。
        2. 封装 Header (路由层) 并序列化为标准化 JSON。
        """
        try:
            raw_payloads = self._collect_l1_payloads()
            if not raw_payloads:
                return []
            
            results = []
            for payload in raw_payloads:
                # 构造 L1 协议信封
                l1_event = {
                    "header": {
                        "uuid": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "device_id": self._device_id,
                        "type": self._l1_type
                    },
                    "payload": payload
                }
                
                # 封装至内核交换格式 RawContextProperties
                results.append(RawContextProperties(
                    source=self._source_type,
                    content_format=ContentFormat.TEXT,
                    content_text=json.dumps(l1_event, ensure_ascii=False),
                    create_time=datetime.now()
                ))
            return results
        except Exception as e:
            logger.error(f"{self._name} capture failure: {str(e)}")
            return []

    @abc.abstractmethod
    def _init_sensor(self, config: Dict[str, Any]) -> bool:
        """子类需实现：初始化具体的硬件接口、Hook 或 AI 引擎。"""
        pass

    @abc.abstractmethod
    def _collect_l1_payloads(self) -> List[Dict[str, Any]]:
        """子类需实现：返回符合 L1 协议规范的业务 Payload 列表。"""
        pass

    def _start_impl(self) -> bool:
        """默认启动逻辑。"""
        return True

    def _stop_impl(self, graceful: bool = True) -> bool:
        """默认停止逻辑。"""
        return True

    def _get_config_schema_impl(self) -> Dict[str, Any]:
        """扩展配置 Schema。"""
        return {
            "properties": {
                "device_id": {"type": "string", "default": "Default-Device"}
            }
        }