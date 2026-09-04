"""通道 B：文章页直抓模块（无需登录，绕过后台接口频控）。

直接抓取 `https://mp.weixin.qq.com/s/<随机串>` 的文章页 HTML，规避后台接口
（appmsg/searchbiz）对 token 与频控的强依赖。面向"自有公众号文章备份"场景，
从已知的文章链接列表出发，逐篇抓取正文，交由 parser 统一解析。

反爬应对策略：
  1. 完整浏览器请求头（UA / Referer / Accept / Accept-Language）；
  2. 优先复用登录态中的 cookies（如存在），增强请求可信度；
  3. 识别微信"环境异常/访问频繁"验证页，抛出 AntiCrawlError；
  4. 失败指数退避重试，网络错误与验证页分别处理；
  5. 可选回退：当直抓持续失败时，交由后台接口通道兜底（见 pipeline）。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from .config import settings
from .exceptions import AntiCrawlError, FetchError

logger = logging.getLogger("dwechatword.article_fetcher")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BASE = "https://mp.weixin.qq.com"

# 微信文章页典型反爬/异常标识
_CAPTCHA_MARKERS = (
    "当前环境异常", "完成验证", "访问过于频繁", "操作频繁",
    "请在微信客户端打开链接", "环境异常", "验证码",
)
# 正文容器缺失通常意味着被拦截或链接失效
_ARTICLE_URL_RE = re.compile(r"^https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_\-]+")


class ArticleFetcher:
    """携带可选 cookies 的文章页直抓客户端。"""

    def __init__(self, cookies: list[dict] | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Referer": "https://mp.weixin.qq.com/",
            "Upgrade-Insecure-Requests": "1",
        })
        for c in cookies or []:
            self.session.cookies.set(
                c.get("name"), c.get("value"),
                domain=c.get("domain", ".qq.com"),
            )

    # ------------------------------------------------------------------ core
    def fetch_article(self, url: str) -> str:
        """抓取单篇文章 HTML，带反爬识别与指数退避重试。"""
        if not _ARTICLE_URL_RE.match(url or ""):
            raise FetchError(f"非法文章链接：{url!r}")

        last_err: Exception | None = None
        for attempt in range(1, settings.article_retries + 1):
            try:
                return self._fetch_once(url)
            except AntiCrawlError:
                # 验证页：等待更长，重试
                last_err = AntiCrawlError(
                    f"文章页触发反爬验证：{url}（第 {attempt} 次）")
                logger.warning("%s", last_err)
                wait = settings.article_retry_wait * (2 ** (attempt - 1))
            except FetchError as e:
                last_err = e
                wait = settings.article_retry_wait * attempt
                logger.warning("抓取失败（第 %s 次）：%s", attempt, e)
            except requests.RequestException as e:
                last_err = FetchError(f"网络错误：{e}")
                wait = settings.article_retry_wait * attempt
                logger.warning("网络错误（第 %s 次）：%s", attempt, e)

            if attempt < settings.article_retries:
                time.sleep(wait)

        raise last_err if last_err else FetchError(f"抓取失败：{url}")

    def _fetch_once(self, url: str) -> str:
        """单次抓取，识别验证页并解析编码。"""
        resp = self.session.get(url, timeout=settings.article_timeout)
        if resp.status_code == 403:
            raise AntiCrawlError(f"HTTP 403 被拒绝：{url}")
        resp.raise_for_status()

        # 微信响应常无 charset 头，GBK/UTF-8 混合；优先按 apparent 解码
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1",):
            resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        if self._is_captcha(html):
            raise AntiCrawlError(f"检测到验证/异常页面：{url}")
        if "#js_content" not in html and "rich_media_content" not in html:
            raise FetchError(f"未找到正文容器，可能链接失效或被拦截：{url}")
        return html

    @staticmethod
    def _is_captcha(html: str) -> bool:
        """识别微信反爬验证页。"""
        head = html[:2000]
        return any(m in head for m in _CAPTCHA_MARKERS)


def build_fetcher_from_session(session: dict[str, Any] | None) -> ArticleFetcher:
    """由会话文件（若存在）构造直抓客户端，复用 cookies 增强可信度。"""
    cookies = (session or {}).get("cookies") or []
    return ArticleFetcher(cookies=cookies)
