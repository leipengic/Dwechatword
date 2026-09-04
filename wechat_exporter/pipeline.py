"""流水线编排：双通道抓取 → 解析 → 多格式导出（Word / PDF / Markdown）。

通道：
  - "api"：后台接口批量导出（需扫码登录，仅本人公众号，按全部/时间范围）。
  - "article"：文章页直抓（无需登录，从链接列表逐篇抓取，绕过后台接口频控）。

导出：
  由 settings.export_formats 决定，支持 word / pdf / md 任意组合，
  统一复用 parser 产出的 Article/Block 结构。
"""

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
from .parser import Article, fetch_html, parse_article
from .article_fetcher import build_fetcher_from_session

logger = logging.getLogger("dwechatword.pipeline")


# ------------------------------------------------------------------ 导出分发
def export_article(article: Article, out_dir: Path | None = None) -> list[Path]:
    """按配置的导出格式，把单篇 Article 渲染为文件，返回路径列表。"""
    out_dir = out_dir or settings.output_dir
    paths: list[Path] = []
    for fmt in settings.export_formats_list:
        if fmt == "word":
            paths.append(build_docx(article, out_dir=out_dir))
        elif fmt == "md":
            from .markdown_writer import build_markdown
            paths.append(build_markdown(article, out_dir=out_dir))
        elif fmt == "pdf":
            from .pdf_writer import build_pdf
            paths.append(build_pdf(article, out_dir=out_dir))
    return paths


# ------------------------------------------------------------------ 通道 A
def _run_api_channel() -> list[Path]:
    """后台接口批量导出。"""
    session = get_session(auto_login=True)
    client = WeChatMPClient(session["token"], session["cookies"])

    try:
        fakeid = client.get_fakeid(settings.account_name)
    except SessionExpiredError:
        logger.warning("登录态失效，请重新扫码")
        raise
    logger.info("公众号 fakeid：%s", fakeid)

    time.sleep(random.uniform(5, 10))  # searchbiz 后冷却，降低频控概率

    articles = collect_all_articles(client, fakeid)
    logger.info("文章列表采集完成，共 %s 篇", len(articles))
    if not articles:
        return []

    _write_index(articles)

    exported: list[Path] = []
    failed: list[str] = []
    for i, meta in enumerate(articles, 1):
        url = meta.get("link", "")
        title = meta.get("title", "")
        logger.info("[%s/%s] 抓取文章：%s", i, len(articles), title)
        try:
            html = fetch_html(url)
            article = parse_article(
                html, url=url, title_hint=title,
                publish_time_hint=meta.get("create_time"),
                digest_hint=meta.get("digest", ""),
            )
            exported.extend(export_article(article))
        except Exception as e:  # noqa: BLE001 单篇失败不中断整体
            logger.error("文章《%s》导出失败：%s", title, e)
            failed.append(title)
        if i < len(articles):
            time.sleep(settings.article_interval + random.uniform(0, 2))

    _summarize(exported, failed)
    return exported


# ------------------------------------------------------------------ 通道 B
def _run_article_channel(urls: list[str]) -> list[Path]:
    """文章页直抓导出（无需登录）。"""
    if not urls:
        logger.error("通道 article 需要提供文章链接列表（--urls 或 --urls-file）")
        return []

    # 若有登录态，复用其 cookies 增强请求可信度（可选）
    session = None
    try:
        session = get_session(auto_login=False)
    except SessionExpiredError:
        session = None
    fetcher = build_fetcher_from_session(session)

    exported: list[Path] = []
    failed: list[str] = []
    for i, url in enumerate(urls, 1):
        logger.info("[%s/%s] 直抓文章：%s", i, len(urls), url)
        try:
            html = fetcher.fetch_article(url)
            article = parse_article(html, url=url)
            exported.extend(export_article(article))
        except Exception as e:  # noqa: BLE001 单篇失败不中断整体
            logger.error("文章直抓失败：%s（%s）", url, e)
            failed.append(url)
        if i < len(urls):
            time.sleep(settings.article_interval + random.uniform(0, 2))

    _summarize(exported, failed)
    return exported


# ------------------------------------------------------------------ 工具
def _write_index(articles: list[dict]) -> None:
    index_path = settings.output_dir / "index.csv"
    with index_path.open("w", encoding="utf-8-sig") as f:
        f.write("序号,标题,发布时间,链接\n")
        for i, a in enumerate(articles, 1):
            ts = datetime.fromtimestamp(a.get("create_time", 0)).strftime("%Y-%m-%d %H:%M")
            title = str(a.get("title", "")).replace(",", "，")
            f.write(f"{i},{title},{ts},{a.get('link', '')}\n")
    logger.info("文章索引已写入 %s", index_path)


def _summarize(exported: list[Path], failed: list[str]) -> None:
    logger.info("导出完成：成功 %s 个文件，失败 %s 篇", len(exported), len(failed))
    if failed:
        logger.warning("失败清单：%s", "；".join(failed))


# ------------------------------------------------------------------ 入口
def run_export(urls: list[str] | None = None) -> list[Path]:
    """统一导出入口：按 settings.channel 分派通道。"""
    settings.ensure_dirs()

    channel = settings.channel
    if channel == "article":
        return _run_article_channel(urls or [])
    if channel == "api":
        return _run_api_channel()

    logger.warning("未知通道 %r，回退到 api 通道", channel)
    return _run_api_channel()
