"""流水线编排：登录 → 取 fakeid → 拉列表 → 逐篇抓取解析 → 导出 Word。"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from pathlib import Path

from .config import settings
from .docx_writer import build_docx
from .exceptions import SessionExpiredError
from .fetcher import WeChatMPClient, collect_all_articles
from .login import get_session
from .parser import fetch_html, parse_article

logger = logging.getLogger("dwechatword.pipeline")


def run_export() -> list[Path]:
    """执行全流程导出，返回生成的 docx 路径列表。"""
    settings.ensure_dirs()

    # 1. 登录态
    session = get_session(auto_login=True)
    client = WeChatMPClient(session["token"], session["cookies"])

    # 2. fakeid（失效时重登一次）
    try:
        fakeid = client.get_fakeid(settings.account_name)
    except SessionExpiredError:
        logger.warning("登录态失效，请重新扫码")
        session = get_session(auto_login=False)  # 触发明确报错提示
        raise
    logger.info("公众号 fakeid：%s", fakeid)

    # searchbiz 后立即拉列表容易触发频控，先冷却一会
    time.sleep(random.uniform(5, 10))

    # 3. 文章列表
    articles = collect_all_articles(client, fakeid)
    logger.info("文章列表采集完成，共 %s 篇", len(articles))
    if not articles:
        return []

    # 索引文件（便于核对）
    index_path = settings.output_dir / "index.csv"
    with index_path.open("w", encoding="utf-8-sig") as f:
        f.write("序号,标题,发布时间,链接\n")
        for i, a in enumerate(articles, 1):
            ts = datetime.fromtimestamp(a.get("create_time", 0)).strftime("%Y-%m-%d %H:%M")
            title = str(a.get("title", "")).replace(",", "，")
            f.write(f"{i},{title},{ts},{a.get('link', '')}\n")
    logger.info("文章索引已写入 %s", index_path)

    # 4. 逐篇导出
    exported: list[Path] = []
    failed: list[str] = []
    for i, meta in enumerate(articles, 1):
        url = meta.get("link", "")
        title = meta.get("title", "")
        logger.info("[%s/%s] 抓取文章：%s", i, len(articles), title)
        try:
            html = fetch_html(url)
            article = parse_article(
                html,
                url=url,
                title_hint=title,
                publish_time_hint=meta.get("create_time"),
                digest_hint=meta.get("digest", ""),
            )
            exported.append(build_docx(article))
        except Exception as e:  # noqa: BLE001 单篇失败不中断整体
            logger.error("文章《%s》导出失败：%s", title, e)
            failed.append(title)
        if i < len(articles):
            time.sleep(settings.article_interval + random.uniform(0, 2))

    logger.info("导出完成：成功 %s 篇，失败 %s 篇", len(exported), len(failed))
    if failed:
        logger.warning("失败文章：%s", "；".join(failed))
    return exported
