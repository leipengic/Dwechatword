"""Dwechatword 命令行入口。

用法：
  python main.py login    # 仅扫码登录，保存会话
  python main.py export   # 使用已保存会话导出全部文章
  python main.py all      # 登录（如需）+ 导出全流程
"""

from __future__ import annotations

import argparse
import sys

from wechat_exporter.config import settings
from wechat_exporter.logger import setup_logging
from wechat_exporter.login import login_and_save_session
from wechat_exporter.pipeline import run_export


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dwechatword",
        description="微信公众号文章批量导出为 Word 文档",
    )
    parser.add_argument(
        "command",
        choices=["login", "export", "all"],
        help="login=扫码登录；export=导出文章；all=登录+导出",
    )
    parser.add_argument("--headless", action="store_true",
                        help="登录浏览器无头模式（默认有头，需扫码不建议）")
    args = parser.parse_args()

    logger = setup_logging()

    if not settings.account_name:
        logger.error("未配置 MP_ACCOUNT_NAME，请复制 .env.example 为 .env 并填写公众号名称")
        return 1

    settings.ensure_dirs()

    try:
        if args.command == "login":
            login_and_save_session(headless=args.headless)
        elif args.command == "export":
            run_export()
        else:
            run_export()  # run_export 内部会按需触发扫码
        return 0
    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130
    except Exception as e:  # noqa: BLE001
        logger.exception("执行失败：%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
