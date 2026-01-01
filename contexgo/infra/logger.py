# -*- coding: utf-8 -*-
# 路径：contexgo/infra/logger.py

import os
import sys
from typing import Any, Dict
from loguru import logger

class LogManager:
    """
    ContexGo 日志管理器：负责控制台和文件的多路输出配置
    """
    def __init__(self):
        # 清除 Loguru 默认的控制台处理器
        logger.remove()

    def configure(self, config: Dict[str, Any]) -> None:
        """
        根据配置动态调整日志行为
        """
        level = config.get("level", "INFO")

        # 1. 配置控制台高亮输出
        console_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.add(sys.stderr, level=level, format=console_format)

        # 2. 配置物理文件持久化
        # 默认指向 data/logs/chronicle 目录，并以模块脚本名作为文件名
        log_dir = config.get("log_dir")
        if not log_dir:
            log_path = config.get("log_path")
            if log_path:
                log_dir = log_path if log_path.endswith(os.sep) else os.path.dirname(log_path)

        log_dir = log_dir or "data/logs/chronicle"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "{module}.log")

        # 滚动配置：单文件 5MB，保留 5 个历史文件
        logger.add(
            log_path,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="5 MB",
            retention=5,
            encoding="utf-8",
            enqueue=True  # 核心：确保多线程 Sensor 写入安全
        )

    def get_logger(self):
        return logger

# 实例化全局管理器
log_manager = LogManager()
# 直接暴露 logger 供快捷调用
log = logger
