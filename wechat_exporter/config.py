"""全局配置：从 .env 与环境变量加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # 公众号名称
    account_name: str = os.getenv("MP_ACCOUNT_NAME", "")
    # 文件路径
    session_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("SESSION_FILE", "session.json")
    )
    output_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output")
    )
    image_cache_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("IMAGE_CACHE_DIR", ".image_cache")
    )
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    # 抓取行为（默认值偏保守，降低触发微信频控概率）
    page_size: int = _int_env("PAGE_SIZE", 5)
    max_pages: int = _int_env("MAX_PAGES", 0)          # 0 = 不限制
    page_interval: float = _int_env("PAGE_INTERVAL", 10)
    rate_limit_wait: int = _int_env("RATE_LIMIT_WAIT", 120)
    article_interval: float = _int_env("ARTICLE_INTERVAL", 5)
    # Word 文档版本号（文件命名 yyyy-mm-dd-标题-vX.X.docx）
    doc_version: str = os.getenv("DOC_VERSION", "v1.0")

    def ensure_dirs(self) -> None:
        for p in (self.output_dir, self.image_cache_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
