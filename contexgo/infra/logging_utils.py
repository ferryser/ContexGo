# -*- coding: utf-8 -*-
# 路径：contexgo/infra/logging_utils.py

from typing import Any, Dict
from .logger import log, log_manager

def setup_logging(config: Dict[str, Any]):
    """
    配置日志底座，将配置传递给底层 LogManager
    """
    log_manager.configure(config)
    log.info("ContexGo logging infrastructure initialized")

def get_logger(name: str):
    """
    供各模块调用，绑定模块名称以便追溯
    """
    return log.bind(name=name)