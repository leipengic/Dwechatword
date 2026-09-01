"""登录模块：Playwright 打开浏览器扫码登录公众平台，持久化 cookie 与 token。

登录成功后保存 session.json（cookies + token），后续运行可直接复用登录态。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .config import settings
from .exceptions import LoginError, SessionExpiredError

LOGIN_URL = "https://mp.weixin.qq.com/"
TOKEN_PATTERN = re.compile(r"token=(\d+)")
LOGIN_TIMEOUT_SECONDS = 300  # 扫码超时：5 分钟


def login_and_save_session(headless: bool = False) -> dict[str, Any]:
    """打开浏览器 → 扫码 → 抓取 token 与 cookies → 写入 session.json。"""
    from playwright.sync_api import sync_playwright

    print("=" * 56)
    print("请在弹出的浏览器中扫码登录微信公众平台（个人微信扫码）")
    print(f"超时时间：{LOGIN_TIMEOUT_SECONDS // 60} 分钟")
    print("=" * 56)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")

            token = None
            deadline = time.time() + LOGIN_TIMEOUT_SECONDS
            while time.time() < deadline:
                url = page.url
                m = TOKEN_PATTERN.search(url)
                if m:  # 登录成功后跳转 home?t=xxx 带 token
                    token = m.group(1)
                    break
                try:
                    content = page.content()
                    m = TOKEN_PATTERN.search(content)
                    if m:
                        token = m.group(1)
                        # 页面内出现 token 但 URL 未跳转，等跳转稳定
                        page.wait_for_load_state("domcontentloaded")
                        if TOKEN_PATTERN.search(page.url):
                            token = TOKEN_PATTERN.search(page.url).group(1)
                        break
                except Exception:  # noqa: BLE001 页面跳转过程中的瞬时错误
                    pass
                time.sleep(1)

            if not token:
                raise LoginError("扫码超时或未检测到 token，请重试")

            cookies = context.cookies()
            session = {"token": token, "cookies": cookies,
                       "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            settings.session_file.write_text(
                json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"登录成功，token={token}")
            print(f"会话已保存：{settings.session_file}")
            return session
        finally:
            browser.close()


def load_session() -> dict[str, Any]:
    """读取本地会话文件。"""
    if not settings.session_file.exists():
        raise SessionExpiredError(
            f"未找到会话文件 {settings.session_file}，请先执行 login 命令扫码登录"
        )
    try:
        return json.loads(settings.session_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SessionExpiredError(f"会话文件损坏，请重新登录: {e}") from e


def get_session(auto_login: bool = True) -> dict[str, Any]:
    """获取会话：本地缓存优先，失效或不存在则触发扫码。"""
    try:
        return load_session()
    except SessionExpiredError:
        if not auto_login:
            raise
        return login_and_save_session()
