"""全局配置：从 .env 与环境变量加载。

统一管理两类通道（后台接口 / 文章页直抓）与多格式导出（Word / PDF / Markdown）
的开关、反爬频控参数与路径。
"""

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


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # ---------------- 公众号信息 ----------------
    account_name: str = os.getenv("MP_ACCOUNT_NAME", "")

    # ---------------- 路径 ----------------
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

    # ---------------- 通道选择 ----------------
    # channel: "api" = 后台接口批量（需登录，仅本人公众号，按时间范围/全部）；
    #          "article" = 文章页直抓（无需登录，按链接列表抓取）；
    #          "auto" = 默认 api。
    channel: str = os.getenv("CHANNEL", "api").strip().lower()

    # ---------------- 导出格式 ----------------
    # 逗号分隔，支持 word/pdf/md，可多选，如 "word,pdf,md"
    export_formats: str = os.getenv("EXPORT_FORMATS", "word,pdf,md").strip().lower()
    doc_version: str = os.getenv("DOC_VERSION", "v1.0")

    # ---------------- 抓取行为（默认偏保守，降低触发微信频控概率） ----------------
    page_size: int = _int_env("PAGE_SIZE", 5)
    max_pages: int = _int_env("MAX_PAGES", 0)          # 0 = 不限制
    page_interval: float = _float_env("PAGE_INTERVAL", 10)
    rate_limit_wait: int = _int_env("RATE_LIMIT_WAIT", 120)
    article_interval: float = _float_env("ARTICLE_INTERVAL", 5)

    # ---------------- 文章页直抓（通道 B）反爬参数 ----------------
    # 单篇文章抓取超时（秒）
    article_timeout: int = _int_env("ARTICLE_TIMEOUT", 30)
    # 触发验证/失败后的重试次数
    article_retries: int = _int_env("ARTICLE_RETRIES", 3)
    # 重试退避基础秒数
    article_retry_wait: float = _float_env("ARTICLE_RETRY_WAIT", 3)
    # 是否在请求失败时自动切换为后台接口通道兜底
    article_fallback_api: bool = _bool_env("ARTICLE_FALLBACK_API", False)

    # ---------------- 兼容旧版别名 ----------------
    @property
    def export_formats_list(self) -> list[str]:
        """解析 export_formats 为规范列表，去重并过滤非法项。"""
        valid = {"word", "pdf", "md", "docx"}
        seen: list[str] = []
        for item in self.export_formats.replace("，", ",").split(","):
            f = item.strip().lower()
            if f == "docx":
                f = "word"
            if f and f in valid and f not in seen:
                seen.append(f)
        return seen

    def ensure_dirs(self) -> None:
        for p in (self.output_dir, self.image_cache_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
