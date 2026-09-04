"""Dwechatword 命令行入口。

用法：
  python main.py login                 # 仅扫码登录，保存会话（通道 api 前置）
  python main.py export                # 后台接口批量导出（通道 api，需登录）
  python main.py single <文章链接>      # 文章页直抓导出单篇（通道 article，免登录）
  python main.py export --urls u1 u2   # 文章页直抓导出多篇（通道 article，免登录）
  python main.py export --urls-file f  # 从文件读取链接列表（每行一个）

导出格式由 .env 的 EXPORT_FORMATS 控制（word,pdf,md 任意组合）。
"""

from __future__ import annotations

import argparse
import sys

from wechat_exporter.config import settings
from wechat_exporter.logger import setup_logging
from wechat_exporter.login import login_and_save_session
from wechat_exporter.pipeline import run_export


def _read_urls_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f
                if line.strip() and not line.lstrip().startswith("#")]


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dwechatword",
        description="微信公众号文章批量导出（Word / PDF / Markdown）",
    )
    parser.add_argument(
        "command",
        choices=["login", "export", "single"],
        help="login=扫码登录；export=导出文章；single=单篇直抓",
    )
    parser.add_argument(
        "urls", nargs="*", metavar="URL",
        help="文章链接（single 或 export --channel article 时使用）",
    )
    parser.add_argument("--urls-file", help="从文件读取文章链接（每行一个）")
    parser.add_argument("--channel", choices=["api", "article"],
                        help="覆盖 .env 中的 CHANNEL")
    parser.add_argument("--headless", action="store_true",
                        help="登录浏览器无头模式（默认有头，需扫码不建议）")
    args = parser.parse_args()

    logger = setup_logging()

    if args.channel:
        settings.channel = args.channel

    settings.ensure_dirs()

    try:
        if args.command == "login":
            login_and_save_session(headless=args.headless)
            return 0

        if args.command == "single":
            if not args.urls:
                logger.error("single 需要提供一个文章链接")
                return 1
            settings.channel = "article"
            run_export(urls=args.urls)
            return 0

        # export
        if settings.channel == "article":
            urls = list(args.urls)
            if args.urls_file:
                urls.extend(_read_urls_file(args.urls_file))
            if not urls:
                logger.error("通道 article 需要 --urls 或 --urls-file 提供链接")
                return 1
            run_export(urls=urls)
        else:
            if not settings.account_name:
                logger.error(
                    "未配置 MP_ACCOUNT_NAME，请复制 .env.example 为 .env 并填写公众号名称")
                return 1
            run_export()
        return 0
    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130
    except Exception as e:  # noqa: BLE001
        logger.exception("执行失败：%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
