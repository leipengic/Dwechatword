"""Markdown 导出模块：把结构化 Article 渲染为 Markdown 文件。

排版策略：
  - 标题 → `#`/`##` 等 ATX 标题
  - 元信息（发布时间/摘要/原文链接）→ 引用块
  - 正文段落 → 普通段落，保留加粗/斜体
  - 引用块 → `>` 前缀，列表 → `-`，图片 → 相对路径
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .config import settings
from .parser import Article, Block

logger = logging.getLogger("dwechatword.markdown_writer")


def _sanitize_filename(name: str, max_len: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .")
    return name[:max_len] or "untitled"


def _inline_md(runs) -> str:
    """把行内 runs 拼接为 Markdown 行内片段。"""
    out: list[str] = []
    for r in runs:
        t = r.text
        if r.bold and r.italic:
            t = f"***{t}***"
        elif r.bold:
            t = f"**{t}**"
        elif r.italic:
            t = f"*{t}*"
        out.append(t)
    return "".join(out)


def build_markdown(article: Article, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# {article.title}")
    lines.append("")
    lines.append(f"> 发布时间：{article.publish_time or '未知'}")
    if article.digest:
        lines.append(f"> 摘要：{article.digest}")
    if article.url:
        lines.append(f"> 原文链接：{article.url}")
    lines.append("")

    for block in article.blocks:
        if block.type == "image" and block.image_path:
            # 使用相对于 md 文件的相对路径
            try:
                rel = block.image_path.relative_to(out_dir)
            except ValueError:
                rel = block.image_path.name
            lines.append(f"![图片]({rel.as_posix()})")
            lines.append("")
            continue

        if not block.runs:
            continue

        text = _inline_md(block.runs)
        if block.type == "heading":
            lines.append(f"{'#' * (min(block.level + 1, 6))} {text}")
        elif block.type == "quote":
            for seg in text.split("\n"):
                lines.append(f"> {seg}")
        elif block.type == "list_item":
            lines.append(f"- {text}")
        else:
            lines.append(text)
        lines.append("")

    date_part = article.publish_time[:10] if len(article.publish_time) >= 10 else "unknown-date"
    filename = f"{date_part}-{_sanitize_filename(article.title)}-{settings.doc_version}.md"
    out_path = out_dir / filename
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("已导出 Markdown：%s", out_path.name)
    return out_path
