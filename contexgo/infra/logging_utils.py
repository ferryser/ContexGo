# -*- coding: utf-8 -*-
# 路径：contexgo/infra/logging_utils.py

from typing import Any, Dict, Optional
from .logger import log, log_manager

def setup_logging(config: Dict[str, Any]):
    """
    配置日志底座，将配置传递给底层 LogManager
    """
    log_manager.configure(config)
    log.info("ContexGo logging infrastructure initialized")


def build_log_config(script_path: str, level: Optional[str] = None) -> Dict[str, Any]:
    config: Dict[str, Any] = {"script_path": script_path}
    if level:
        config["level"] = level
    return config

def get_logger(name: str):
    """
    供各模块调用，绑定模块名称以便追溯
    """
    return log.bind(name=name)
