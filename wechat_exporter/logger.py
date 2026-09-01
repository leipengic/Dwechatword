"""日志：控制台 + 滚动文件双通道。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import settings

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dwechatword")
    if logger.handlers:  # 防止重复初始化
        return logger
    logger.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FMT, datefmt="%H:%M:%S"))
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "dwechatword.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(file_handler)
    return logger
