"""冒烟测试：不联网，验证核心解析与导出逻辑可用。"""

from __future__ import annotations

from pathlib import Path

from wechat_exporter.docx_writer import build_docx, _sanitize_filename
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
