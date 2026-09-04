"""冒烟测试：不联网，验证核心解析与多格式导出逻辑可用。"""

from __future__ import annotations

from pathlib import Path

from wechat_exporter.docx_writer import build_docx, _sanitize_filename
from wechat_exporter.markdown_writer import build_markdown
from wechat_exporter.parser import Article, Block, Run

SAMPLE_HTML = """
<html><body>
<h1 id="activity-name">测试文章标题</h1>
<em id="publish_time">2026-09-01 10:00</em>
<div id="js_content">
  <p>第一段普通文字，包含<strong>加粗</strong>和<em>斜体</em>。</p>
  <h2>二级标题</h2>
  <blockquote>引用文字</blockquote>
  <ul><li>列表项一</li><li>列表项二</li></ul>
</div>
</body></html>
"""


def test_sanitize_filename():
    assert _sanitize_filename('a/b:c*d?"e') == "a_b_c_d__e"


def test_parse_article():
    from wechat_exporter.parser import parse_article
    art = parse_article(SAMPLE_HTML, url="https://mp.weixin.qq.com/s/abc")
    assert art.title == "测试文章标题"
    assert art.publish_time == "2026-09-01 10:00"
    types = [b.type for b in art.blocks]
    assert "heading" in types and "quote" in types and "list_item" in types


def test_build_docx(tmp_path: Path):
    art = Article(
        title="冒烟测试文档",
        publish_time="2026-09-01 12:00",
        url="https://mp.weixin.qq.com/s/test",
        blocks=[
            Block(type="paragraph", runs=[Run("正文内容", bold=True)]),
            Block(type="heading", runs=[Run("小标题")], level=2),
            Block(type="quote", runs=[Run("引用")]),
        ],
    )
    path = build_docx(art, out_dir=tmp_path)
    assert path.exists() and path.suffix == ".docx"
    assert "冒烟测试文档" in path.name and "2026-09-01" in path.name


def test_build_markdown(tmp_path: Path):
    art = Article(
        title="冒烟测试MD",
        publish_time="2026-09-01 12:00",
        url="https://mp.weixin.qq.com/s/test",
        digest="摘要内容",
        blocks=[
            Block(type="heading", runs=[Run("二级")], level=2),
            Block(type="paragraph", runs=[Run("加粗", bold=True), Run("普通")]),
            Block(type="list_item", runs=[Run("列表项")]),
        ],
    )
    path = build_markdown(art, out_dir=tmp_path)
    assert path.exists() and path.suffix == ".md"
    content = path.read_text(encoding="utf-8")
    assert "# 冒烟测试MD" in content
    assert "**加粗**" in content
    assert "> 发布时间：2026-09-01 12:00" in content
    assert "- 列表项" in content


def test_captcha_detection():
    """反爬验证页识别逻辑。"""
    from wechat_exporter.article_fetcher import ArticleFetcher
    assert ArticleFetcher._is_captcha("<div>当前环境异常，完成验证</div>")
    assert ArticleFetcher._is_captcha("访问过于频繁，请稍后再试")
    assert not ArticleFetcher._is_captcha(
        "<div id='js_content'>正常正文</div>")


def test_export_formats_parsing():
    """导出格式解析：逗号分隔、去重、docx 别名、过滤非法项。"""
    from wechat_exporter.config import Settings
    s = Settings()
    s.export_formats = "word,pdf,md"
    assert s.export_formats_list == ["word", "pdf", "md"]

    s.export_formats = "docx,word,md,md"
    assert s.export_formats_list == ["word", "md"]

    s.export_formats = "word，pdf,foo"
    assert s.export_formats_list == ["word", "pdf"]
