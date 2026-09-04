"""PDF 导出模块：把结构化 Article 渲染为 PDF 文件。

实现方式：先将 Article 渲染为自包含 HTML（图片内联 base64、中文字体声明），
再交由 WeasyPrint 渲染为 PDF。这样能复用 Web 排版能力，稳定处理中文与图片。

若 WeasyPrint 未安装，抛出明确提示（引导 `pip install weasyprint`）。
"""

from __future__ import annotations

import base64
import html as html_lib
import logging
import re
from pathlib import Path

from .config import settings
from .parser import Article, Block

logger = logging.getLogger("dwechatword.pdf_writer")


def _sanitize_filename(name: str, max_len: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .")
    return name[:max_len] or "untitled"


def _img_data_uri(path: Path) -> str:
    """把本地图片转成 base64 data URI，实现 PDF 自包含。"""
    try:
        data = path.read_bytes()
        ext = path.suffix.lstrip(".").lower() or "jpg"
        mime = {"png": "image/png", "jpg": "image/jpeg",
                "jpeg": "image/jpeg", "gif": "image/gif",
                "webp": "image/webp"}.get(ext, "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception:  # noqa: BLE001
        return ""


def _render_blocks(article: Article) -> str:
    """渲染正文块为 HTML 片段。"""
    parts: list[str] = []
    for block in article.blocks:
        if block.type == "image" and block.image_path:
            uri = _img_data_uri(block.image_path)
            if uri:
                parts.append(f'<p class="img"><img src="{uri}"/></p>')
            continue
        if not block.runs:
            continue

        runs_html = []
        for r in block.runs:
            t = html_lib.escape(r.text)
            if r.bold:
                t = f"<strong>{t}</strong>"
            if r.italic:
                t = f"<em>{t}</em>"
            if r.underline:
                t = f"<u>{t}</u>"
            runs_html.append(t.replace("\n", "<br/>"))
        text = "".join(runs_html)

        if block.type == "heading":
            level = min(block.level + 1, 4)
            parts.append(f"<h{level}>{text}</h{level}>")
        elif block.type == "quote":
            parts.append(f"<blockquote>{text}</blockquote>")
        elif block.type == "list_item":
            parts.append(f"<p class=\"li\">• {text}</p>")
        else:
            parts.append(f"<p>{text}</p>")
    return "\n".join(parts)


_CSS = """
@page { size: A4; margin: 2.2cm 2.4cm; }
body { font-family: "Noto Serif CJK SC", "SimSun", "宋体", serif;
       font-size: 11pt; line-height: 1.7; color: #222; }
h1 { font-size: 20pt; text-align: center; margin: 0 0 1em; }
h2, h3, h4 { font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }
.meta { color: #808080; font-size: 9pt; border-bottom: 1px solid #ddd;
        padding-bottom: 0.8em; margin-bottom: 1.5em; }
.meta div { margin: 2px 0; }
p { margin: 0.5em 0; text-indent: 2em; }
p.img, p.li { text-indent: 0; }
p.img { text-align: center; }
img { max-width: 100%; height: auto; }
blockquote { color: #606060; margin: 0.5em 1em; padding-left: 0.8em;
             border-left: 3px solid #ccc; }
"""


def build_pdf(article: Article, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    body = _render_blocks(article)
    meta = [f"发布时间：{html_lib.escape(article.publish_time or '未知')}"]
    if article.digest:
        meta.append(f"摘要：{html_lib.escape(article.digest)}")
    if article.url:
        meta.append(f"原文链接：{html_lib.escape(article.url)}")
    meta_html = "".join(f"<div>{m}</div>" for m in meta)

    doc_html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{html_lib.escape(article.title)}</title>
<style>{_CSS}</style></head>
<body>
<h1>{html_lib.escape(article.title)}</h1>
<div class="meta">{meta_html}</div>
{body}
</body></html>"""

    date_part = article.publish_time[:10] if len(article.publish_time) >= 10 else "unknown-date"
    filename = f"{date_part}-{_sanitize_filename(article.title)}-{settings.doc_version}.pdf"
    out_path = out_dir / filename

    try:
        from weasyprint import HTML  # noqa: PLC0415 延迟导入，避免硬依赖
        HTML(string=doc_html, base_url=str(out_dir)).write_pdf(str(out_path))
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "未安装 WeasyPrint，无法生成 PDF。请先执行：pip install weasyprint"
        ) from e
    except Exception as e:  # noqa: BLE001
        logger.warning("PDF 渲染失败 %s: %s", article.title, e)
        raise

    logger.info("已导出 PDF：%s", out_path.name)
    return out_path
