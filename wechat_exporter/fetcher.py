"""采集模块：调用公众平台后台接口，分页拉取公众号全部文章元数据。

核心接口：
  1. searchbiz  —— 按名称搜索公众号，得到 fakeid
  2. appmsg     —— list_ex 动作分页拉取该 fakeid 下的群发文章
链接形如 https://mp.weixin.qq.com/s/<随机串>，来自 app_msg_list[].link。
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

from .config import settings
from .exceptions import RateLimitError, SessionExpiredError, WeChatExporterError

logger = logging.getLogger("dwechatword.fetcher")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BASE = "https://mp.weixin.qq.com"

# 常见错误码
RET_OK = 0
RET_FREQ_CONTROL = 200013   # 触发频控
RET_SESSION_EXPIRED = {200002, 200003}  # 登录态失效


class WeChatMPClient:
    """携带登录态的平台接口客户端。"""

    def __init__(self, token: str, cookies: list[dict]) -> None:
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Referer": f"{BASE}/cgi-bin/home?t=home/index&lang=zh_CN&token={token}",
        })
        for c in cookies:
            self.session.cookies.set(
                c.get("name"), c.get("value"), domain=c.get("domain", "")
            )

    # ------------------------------------------------------------------ utils
    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        params.update({
            "token": self.token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": 1,
        })
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        ret = (data.get("base_resp") or {}).get("ret", RET_OK)
        if ret == RET_FREQ_CONTROL:
            raise RateLimitError("接口频控（ret=200013）")
        if ret in RET_SESSION_EXPIRED:
            raise SessionExpiredError(f"登录态失效（ret={ret}）")
        if ret != RET_OK:
            raise WeChatExporterError(
                f"接口返回错误 ret={ret} errmsg={(data.get('base_resp') or {}).get('errmsg')}"
            )
        return data

    # ------------------------------------------------------------------ api
    def get_fakeid(self, account_name: str) -> str:
        """按公众号名称搜索，返回本人账号的 fakeid。"""
        data = self._get(f"{BASE}/cgi-bin/searchbiz", {
            "action": "search_biz",
            "begin": 0,
            "count": 5,
            "query": account_name,
            "random": round(random.random(), 16),
        })
        biz_list = data.get("list") or []
        if not biz_list:
            raise WeChatExporterError(f"未搜索到公众号「{account_name}」，请检查名称")
        # 命中第一条（本人账号全名精确搜索通常首位即正确）
        for biz in biz_list:
            if biz.get("nickname") == account_name:
                return biz["fakeid"]
        logger.warning("未精确匹配到「%s」，默认使用搜索结果第一条：%s",
                       account_name, biz_list[0].get("nickname"))
        return biz_list[0]["fakeid"]

    def list_articles(self, fakeid: str, begin: int, count: int | None = None) -> dict:
        """拉取一页文章列表。"""
        count = count or settings.page_size
        return self._get(f"{BASE}/cgi-bin/appmsg", {
            "action": "list_ex",
            "begin": begin,
            "count": count,
            "fakeid": fakeid,
            "type": 9,          # 9 = 全部
            "query": "",
            "random": round(random.random(), 16),
        })


def collect_all_articles(client: WeChatMPClient, fakeid: str) -> list[dict]:
    """分页拉取全部文章元数据，自动处理频控退避。"""
    all_articles: list[dict] = []
    total: int | None = None
    begin = 0
    page = 0
    seen_links: set[str] = set()

    while True:
        page += 1
        if settings.max_pages and page > settings.max_pages:
            logger.info("达到最大页数限制 %s，停止翻页", settings.max_pages)
            break

        attempt = 0
        while True:  # 频控重试
            try:
                data = client.list_articles(fakeid, begin)
                break
            except RateLimitError:
                attempt += 1
                wait = settings.rate_limit_wait + random.uniform(5, 15) * attempt
                logger.warning("第 %s 页触发频控，等待 %.0f 秒后重试（第 %s 次）",
                               page, wait, attempt)
                if attempt >= 5:
                    raise
                time.sleep(wait)

        if total is None:
            total = int(data.get("app_msg_cnt", 0))
            logger.info("公众号共有 %s 篇文章，开始采集", total)

        msg_list = data.get("app_msg_list") or []
        if not msg_list:
            logger.info("第 %s 页无更多数据，采集结束", page)
            break

        fresh = [a for a in msg_list if a.get("link") not in seen_links]
        for a in fresh:
            seen_links.add(a.get("link"))
        all_articles.extend(fresh)
        logger.info("第 %s 页：获取 %s 篇（累计 %s/%s）",
                    page, len(fresh), len(all_articles), total or "?")

        begin += len(msg_list)
        if total and begin >= total:
            break

        # 翻页随机间隔，降低频控概率
        time.sleep(settings.page_interval + random.uniform(0, 3))

    return all_articles
