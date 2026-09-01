"""解析模块：抓取文章页 HTML，解析标题/发布时间/正文/图片。

输出的结构化块（Block）供 docx_writer 生成 Word。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from .config import settings
from .exceptions import ParseError

logger = logging.getLogger("dwechatword.parser")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6",
              "blockquote", "li", "pre", "tr"}
INLINE_BOLD = {"strong", "b"}
INLINE_ITALIC = {"em", "i"}


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class Block:
    type: str                       # paragraph / heading / image / quote / list_item
    runs: list[Run] = field(default_factory=list)
    image_path: Path | None = None
    level: int = 1                  # 标题级别


@dataclass
class Article:
    title: str
    publish_time: str
    url: str
    digest: str = ""
    blocks: list[Block] = field(default_factory=list)


# ---------------------------------------------------------------------- 抓取
def fetch_html(url: str) -> str:
    headers = {"User-Agent": UA, "Referer": "https://mp.weixin.qq.com/"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def download_image(url: str) -> Path | None:
    """下载图片到缓存目录，返回本地路径；失败返回 None。"""
    if not url.startswith("http"):
        return None
    ext = ".jpg"
    m = re.search(r"wx_fmt=(\w+)", url)
    if m:
        ext = "." + m.group(1)
    name = hashlib.md5(url.encode()).hexdigest() + ext
    path = settings.image_cache_dir / name
    if path.exists():
        return path
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return path
    except Exception as e:  # noqa: BLE001 单图失败不影响整体导出
        logger.warning("图片下载失败 %s: %s", url, e)
        return None


# ---------------------------------------------------------------------- 解析
def _collect_inline(tag: Tag, runs: list[Run], bold=False, italic=False,
                    underline=False) -> None:
    """递归收集行内节点，累积粗体/斜体/下划线样式。"""
    for child in tag.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text.strip("\n"):
                runs.append(Run(text, bold, italic, underline))
        elif isinstance(child, Tag):
            if child.name == "br":
                runs.append(Run("\n", bold, italic, underline))
                continue
            if child.name == "img":
                continue  # 图片在块级处理
            _collect_inline(
                child, runs,
                bold=bold or child.name in INLINE_BOLD,
                italic=italic or child.name in INLINE_ITALIC,
                underline=underline or child.name == "u",
            )


def _walk(tag: Tag, blocks: list[Block]) -> None:
    """深度优先遍历内容树，产出块级 Block。"""
    has_block_child = any(
        isinstance(c, Tag) and (c.name in BLOCK_TAGS or c.find(BLOCK_TAGS))
        for c in tag.children
    )
    if tag.name == "img":
        src = tag.get("data-src") or tag.get("src")
        if src:
            img = download_image(src)
            if img:
                blocks.append(Block(type="image", image_path=img))
        return

    if tag.name in BLOCK_TAGS and not has_block_child:
        # 叶子块：图片 + 文字
        for img in tag.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if src:
                local = download_image(src)
                if local:
                    blocks.append(Block(type="image", image_path=local))
        runs: list[Run] = []
        _collect_inline(tag, runs)
        text = "".join(r.text for r in runs).strip()
        if not text:
            return
        if tag.name.startswith("h"):
            blocks.append(Block(type="heading", runs=runs, level=int(tag.name[1])))
        elif tag.name == "blockquote":
            blocks.append(Block(type="quote", runs=runs))
        elif tag.name == "li":
            blocks.append(Block(type="list_item", runs=runs))
        else:
            blocks.append(Block(type="paragraph", runs=runs))
        return

    # 容器节点：继续下钻
    for child in tag.children:
        if isinstance(child, Tag):
            if child.name == "img":
                src = child.get("data-src") or child.get("src")
                if src:
                    local = download_image(src)
                    if local:
                        blocks.append(Block(type="image", image_path=local))
            elif child.find(["img"] + list(BLOCK_TAGS)) or child.name in BLOCK_TAGS:
                _walk(child, blocks)
            else:
                runs = []
                _collect_inline(child, runs)
                text = "".join(r.text for r in runs).strip()
                if text:
                    blocks.append(Block(type="paragraph", runs=runs))
        elif isinstance(child, NavigableString) and str(child).strip():
            blocks.append(Block(type="paragraph", runs=[Run(str(child).strip())]))


def parse_article(html: str, url: str = "", title_hint: str = "",
                  publish_time_hint: int | None = None,
                  digest_hint: str = "") -> Article:
    """解析文章 HTML 为结构化 Article。"""
    soup = BeautifulSoup(html, "lxml")

    # 标题
    title = (soup.select_one("#activity-name")
             or soup.select_one("h1.rich_media_title")
             or soup.select_one("h1"))
    title_text = title.get_text(strip=True) if title else title_hint or "无标题"

    # 发布时间：优先页面内时间，其次 API 的 create_time
    publish_time = ""
    t = soup.select_one("#publish_time")
    if t:
        publish_time = t.get_text(strip=True)
    if not publish_time and publish_time_hint:
        publish_time = datetime.fromtimestamp(publish_time_hint).strftime(
            "%Y-%m-%d %H:%M")

    # 正文容器
    content = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
    if content is None:
        raise ParseError(f"未找到正文容器 #js_content：{url}")

    # 清洗：去掉脚本/样式/隐藏节点
    for bad in content.find_all(["script", "style", "svg"]):
        bad.decompose()

    blocks: list[Block] = []
    _walk(content, blocks)
    logger.info("文章《%s》解析完成：%s 个内容块", title_text, len(blocks))

    return Article(
        title=title_text,
        publish_time=publish_time,
        url=url,
        digest=digest_hint,
        blocks=blocks,
    )
