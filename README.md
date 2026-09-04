# Dwechatword

微信公众号文章批量导出为本地 Word 文档（.docx）。基于 Python 爬虫思路：登录微信公众平台管理后台，调用官方后台接口分页抓取本人名下公众号的全部群发文章（含标题、正文、图片、发布时间），并按结构化排版导出为 Word。

> 仅支持导出**自己拥有管理权限**的公众号文章（个人内容备份用途），请遵守微信公众平台使用规范，控制抓取频率。

## 项目结构

```
Dwechatword/
├── main.py                     # 命令行入口（login / export / all）
├── requirements.txt            # 依赖清单
├── .env.example                # 配置模板（复制为 .env 使用）
├── .gitignore
├── wechat_exporter/
│   ├── config.py               # 全局配置（.env 加载）
│   ├── logger.py               # 日志（控制台 + 滚动文件）
│   ├── exceptions.py           # 异常体系
│   ├── login.py                # Playwright 扫码登录、会话持久化
│   ├── fetcher.py              # 文章列表接口调用、分页、频控退避
│   ├── parser.py               # 文章 HTML 解析、图片下载、结构化
│   ├── docx_writer.py          # python-docx 生成 Word
│   └── pipeline.py             # 全流程编排
├── tests/
│   └── test_smoke.py           # 冒烟测试（离线可跑）
└── output/                     # 导出结果（运行时生成，不入库）
```

## 实现原理

1. **登录与采集**
   - `login.py` 用 Playwright 打开 `mp.weixin.qq.com`，人工扫码后从跳转 URL 提取 `token`，保存 cookies 到 `session.json`；后续运行直接复用登录态，失效时提示重新扫码。
   - `fetcher.py` 调用后台接口：
     - `/cgi-bin/searchbiz` —— 按公众号名称搜索，获取本人账号 `fakeid`；
     - `/cgi-bin/appmsg?action=list_ex` —— 以 `begin/count` 分页拉取文章列表，返回 `app_msg_list`（含 `title`、`link`、`create_time`、`digest`）与 `app_msg_cnt`（总数）。文章链接形如 `https://mp.weixin.qq.com/s/<随机串>`。
2. **解析与导出**
   - `parser.py` 抓取每篇文章 HTML，定位 `#activity-name`（标题）、`#publish_time`（时间）、`#js_content`（正文），深度优先遍历产出结构化内容块；图片取 `data-src`（微信懒加载属性）下载到本地缓存。
   - `docx_writer.py` 渲染为 Word：标题 → Heading 1，元信息（发布时间/摘要/原文链接）→ 灰色小字区，正文 → 宋体小四、1.5 倍行距、首行缩进，图片居中按页宽缩放。
   - 文件命名：`yyyy-mm-dd-文章标题-v1.0.docx`（日期为发布日期）；另生成 `output/index.csv` 全量索引便于核对。
3. **反爬与稳定性**
   - 翻页/单篇间隔加随机抖动（默认 5s/3s，可在 `.env` 调整）；
   - 触发频控（`ret=200013`）自动指数退避重试（默认等待 60s 起，最多 5 次）；
   - 登录态失效（`ret=200002/200003`）抛出明确异常提示重新扫码；
   - 单篇文章导出失败不影响整体，结束后汇总失败清单；全流程写入 `logs/dwechatword.log`。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium   # 若下载失败，代码会自动使用系统已安装的 Edge/Chrome

# 2. 配置
copy .env.example .env    # 编辑 MP_ACCOUNT_NAME 为你的公众号名称

# 3. 首次登录（扫码）
python main.py login

# 4. 导出全部文章
python main.py export
```

常用配置（.env）：

| 配置项 | 默认 | 说明 |
|---|---|---|
| `MP_ACCOUNT_NAME` | - | 公众号名称（必填） |
| `PAGE_SIZE` | 5 | 每页文章数（平台上限 5） |
| `MAX_PAGES` | 0 | 最大页数，0=抓完为止 |
| `PAGE_INTERVAL` | 5 | 翻页基础间隔秒（+随机抖动） |
| `RATE_LIMIT_WAIT` | 60 | 频控退避基础等待秒 |
| `DOC_VERSION` | v1.0 | 文件名版本号 |

## 测试要点（自有账号实测清单）

- [ ] `python main.py login`：浏览器弹出二维码，扫码后 10s 内提示"登录成功"，`session.json` 生成且包含 `token` 与 `cookies`。
- [ ] 会话复用：再次运行 `export` 不重新扫码直接开始采集。
- [ ] 列表分页：文章数 > 5 时正确翻页，日志出现"第 N 页：获取 X 篇（累计 Y/总数）"，`output/index.csv` 行数与公众号后台文章总数一致。
- [ ] 内容完整性：抽查 docx —— 标题、发布时间、正文段落、加粗/斜体样式、图片位置均正常；图片缺失的文章不报错中断。
- [ ] 排版：打开 Word 检查中文字体（宋体/微软雅黑）、1.5 倍行距、首行缩进、图片居中且不超页宽。
- [ ] 反爬：将 `PAGE_INTERVAL` 调小制造频控，确认触发 `ret=200013` 后自动等待重试而非直接崩溃。
- [ ] 登录态过期：手动删除 `session.json` 中部分 cookie 或等待过期后运行，确认报错信息明确提示重新扫码。
- [ ] 异常文章：删除/违规文章链接已失效时，程序记录失败清单并继续导出其余文章。
- [ ] 离线冒烟测试：`pip install pytest && pytest tests/ -v` 全部通过。

## 推送到 GitHub（仓库 Dwechatword）

```bash
cd Dwechatword
git init
git add .
git commit -m "feat: 微信公众号文章批量导出 Word 工具"
# 在 GitHub 网页新建空仓库 Dwechatword（不要勾选 README 初始化），然后：
git branch -M main
git remote add origin https://github.com/<你的用户名>/Dwechatword.git
git push -u origin main
```

> `.gitignore` 已排除 `.env`、`session.json`、`output/`、`logs/`，不会泄露登录凭据与本地数据。

## 常见问题

**Q：运行 `export` 一直报 `ret=200013` 频控怎么办？**
- 说明当前账号/IP 触发了微信后台的频次限制。代码会自动指数退避重试 5 次，若仍失败需冷却 1~24 小时后再试。
- 降低频率：将 `.env` 中的 `PAGE_INTERVAL` 调到 10~15、`RATE_LIMIT_WAIT` 调到 120 以上。
- 避免在短时间内反复登录/导出，否则容易加重限制。

**Q：`playwright install chromium` 下载失败怎么办？**
- 保持系统 Edge/Chrome 为最新版即可，`login.py` 已优先调用系统浏览器，无需强制下载 Chromium。

## 免责声明

本项目仅供个人备份自有公众号内容使用。请勿用于抓取他人公众号、绕过平台限制或任何商业用途；使用产生的账号风险由使用者自行承担。

## License

[MIT](./LICENSE) © leipengic
