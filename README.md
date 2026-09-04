# Dwechatword

微信公众号文章批量导出工具，支持导出为 **Word（.docx）/ PDF / Markdown（.md）** 三种格式。

项目采用**双通道**设计，面向「备份自有公众号内容」场景：

| 通道 | 说明 | 是否需要登录 | 适用场景 |
|---|---|---|---|
| **api** | 调用微信公众平台后台接口分页抓取 | 需扫码登录 | 批量导出本人公众号全部文章 |
| **article** | 直接抓取文章页 `mp.weixin.qq.com/s/xxx` | **免登录** | 按链接列表逐篇抓取，绕过后台接口频控 |

> **合规声明**：仅支持导出**自己拥有管理权限**的公众号文章（个人内容备份用途）。请遵守微信公众平台使用规范，控制抓取频率，勿用于抓取他人公众号或商业用途。

---

## 项目结构

```
Dwechatword/
├── main.py                     # 命令行入口（login / export / single）
├── requirements.txt            # 依赖清单
├── .env.example                # 配置模板（复制为 .env 使用）
├── .gitignore
├── wechat_exporter/
│   ├── __init__.py
│   ├── config.py               # 全局配置（通道/格式/反爬参数）
│   ├── logger.py               # 日志（控制台 + 滚动文件）
│   ├── exceptions.py           # 异常体系（含反爬/抓取异常）
│   ├── login.py                # Playwright 扫码登录、会话持久化
│   ├── fetcher.py              # 通道 A：后台接口拉列表、分页、频控退避
│   ├── article_fetcher.py      # 通道 B：文章页直抓、反爬识别、重试
│   ├── parser.py               # 文章 HTML 解析、图片下载、结构化
│   ├── docx_writer.py          # Word 导出
│   ├── markdown_writer.py      # Markdown 导出
│   ├── pdf_writer.py           # PDF 导出（WeasyPrint）
│   └── pipeline.py             # 双通道 + 多格式编排
├── tests/
│   └── test_smoke.py           # 冒烟测试（离线可跑）
└── output/                     # 导出结果（运行时生成，不入库）
```

## 实现原理

### 通道 A —— 后台接口批量导出（api）

1. **登录与采集**
   - `login.py` 用 Playwright 打开 `mp.weixin.qq.com`，人工扫码后从跳转 URL 提取 `token`，保存 cookies 到 `session.json`；后续运行直接复用登录态，失效时提示重新扫码。
   - `fetcher.py` 调用后台接口：
     - `/cgi-bin/searchbiz` —— 按公众号名称搜索，获取本人账号 `fakeid`；
     - `/cgi-bin/appmsg?action=list_ex` —— 以 `begin/count` 分页拉取文章列表，返回 `app_msg_list`（含 `title`、`link`、`create_time`、`digest`）与 `app_msg_cnt`（总数）。
2. **反爬与稳定性**
   - 翻页/单篇间隔加随机抖动（默认 10s/5s，可在 `.env` 调整）；
   - 触发频控（`ret=200013`）自动指数退避重试（默认 120s 起，最多 5 次）；
   - 登录态失效（`ret=200002/200003`）抛出明确异常提示重新扫码。

### 通道 B —— 文章页直抓（article）

针对「后台接口触发频控、token 失效」的痛点，新增**无需登录**的文章页直抓通道：

1. **抓取**
   - `article_fetcher.py` 以完整浏览器请求头（UA/Referer/Accept）直接请求 `mp.weixin.qq.com/s/xxx`；
   - 若存在 `session.json`，自动复用其 cookies 增强请求可信度；
   - 智能识别微信「环境异常 / 访问过于频繁」验证页与 HTTP 403，抛出 `AntiCrawlError`。
2. **反爬重试**
   - 网络错误与验证页分别处理，采用指数退避重试（默认 3 次，基础 3s）；
   - 单篇失败不影响整体，结束后汇总失败清单。

### 解析与多格式导出

- `parser.py` 抓取每篇文章 HTML，定位 `#activity-name`（标题）、`#publish_time`（时间）、`#js_content`（正文），深度优先遍历产出结构化内容块（段落/标题/引用/列表/图片）；图片取 `data-src`（微信懒加载属性）下载到本地缓存。
- 三种导出器共享同一套 `Article/Block` 结构：
  - **Word**：标题 → Heading 1，元信息 → 灰色小字区，正文 → 宋体小四、1.5 倍行距、首行缩进，图片居中按页宽缩放；
  - **Markdown**：ATX 标题、引用块元信息、加粗/斜体行内样式、图片相对路径引用；
  - **PDF**：先渲染为自包含 HTML（图片 base64 内联、中文字体声明），再由 WeasyPrint 转 PDF。
- 文件命名统一：`yyyy-mm-dd-文章标题-vX.X.<扩展名>`（日期为发布日期）。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium   # 若下载失败，代码会自动使用系统已安装的 Edge/Chrome

# 2. 配置
copy .env.example .env    # 编辑 MP_ACCOUNT_NAME 为你的公众号名称

# 3a. 通道 A：批量导出（需登录）
python main.py login        # 首次扫码登录
python main.py export       # 导出全部文章

# 3b. 通道 B：文章页直抓（免登录）
python main.py single https://mp.weixin.qq.com/s/xxxxx          # 单篇
python main.py export --channel article --urls <链接1> <链接2>   # 多篇
python main.py export --channel article --urls-file links.txt    # 从文件读取
```

## 常用配置（.env）

| 配置项 | 默认 | 说明 |
|---|---|---|
| `MP_ACCOUNT_NAME` | - | 公众号名称（通道 api 必填） |
| `CHANNEL` | api | `api`=后台接口；`article`=文章页直抓 |
| `EXPORT_FORMATS` | word,pdf,md | 导出格式，逗号分隔，任意组合 |
| `PAGE_SIZE` | 5 | 每页文章数（平台上限 5） |
| `MAX_PAGES` | 0 | 最大页数，0=抓完为止 |
| `PAGE_INTERVAL` | 10 | 翻页基础间隔秒（+随机抖动） |
| `RATE_LIMIT_WAIT` | 120 | 频控退避基础等待秒 |
| `ARTICLE_INTERVAL` | 5 | 单篇抓取间隔秒 |
| `ARTICLE_TIMEOUT` | 30 | 文章页抓取超时秒 |
| `ARTICLE_RETRIES` | 3 | 直抓失败/触发验证的重试次数 |
| `ARTICLE_RETRY_WAIT` | 3 | 重试退避基础秒（指数递增） |
| `DOC_VERSION` | v1.0 | 文件名版本号 |

## 测试要点（自有账号实测清单）

- [ ] `python main.py login`：浏览器弹出二维码，扫码后提示"登录成功"，`session.json` 生成且包含 `token` 与 `cookies`。
- [ ] 会话复用：再次运行 `export` 不重新扫码直接开始采集。
- [ ] 列表分页：文章数 > 5 时正确翻页，`output/index.csv` 行数与后台文章总数一致。
- [ ] 内容完整性：抽查 docx/md/pdf —— 标题、发布时间、正文段落、加粗/斜体、图片位置均正常；图片缺失不报错中断。
- [ ] 通道 B：`python main.py single <文章链接>` 免登录直抓，生成三种格式文件；构造验证页场景确认抛出明确的反爬提示。
- [ ] 反爬：将 `PAGE_INTERVAL` 调小制造频控，确认触发 `ret=200013` 后自动等待重试而非崩溃。
- [ ] 登录态过期：删除 `session.json` 后运行，确认报错明确提示重新扫码。
- [ ] 异常文章：删除/违规文章链接失效时，记录失败清单并继续导出其余文章。
- [ ] 离线冒烟测试：`pytest tests/ -v` 全部通过。

## 常见问题

**Q：运行 `export` 一直报 `ret=200013` 频控怎么办？**
- 代码会自动指数退避重试 5 次，若仍失败需冷却 1~24 小时后再试。
- 降低频率：将 `PAGE_INTERVAL` 调到 15、`RATE_LIMIT_WAIT` 调到 180 以上。
- 改用**通道 B**：`python main.py export --channel article --urls ...`，直接抓文章页，绕过后台接口频控。

**Q：通道 B 抓取报「检测到验证/异常页面」？**
- 说明当前 IP 触发了微信文章页反爬。等待一段时间、降低 `ARTICLE_INTERVAL`，或复用已登录的 `session.json`（通道 B 会自动加载 cookies）。

**Q：PDF 导出报「未安装 WeasyPrint」？**
- 执行 `pip install weasyprint`（Windows 需额外安装 GTK 运行时，见 WeasyPrint 官方文档）；或注释 `requirements.txt` 中该行、将 `EXPORT_FORMATS` 改为 `word,md` 跳过 PDF。

**Q：`playwright install chromium` 下载失败怎么办？**
- 保持系统 Edge/Chrome 为最新版即可，`login.py` 已优先调用系统浏览器，无需强制下载 Chromium。

## 免责声明

本项目仅供个人备份自有公众号内容使用。请勿用于抓取他人公众号、绕过平台限制或任何商业用途；使用产生的账号风险由使用者自行承担。

## 贡献

欢迎提交 Issue 与 Pull Request。参与前请阅读[贡献指南](CONTRIBUTING.md)与[行为准则](CODE_OF_CONDUCT.md)。

## 致谢

本项目功能与思路参考了开源项目 [qiye45/wechatDownload](https://github.com/qiye45/wechatDownload)（微信公众号文章批量下载工具），特此感谢原作者 **qiye45（长风）** 的开源贡献与思路启发。本项目的文章页直抓通道与多格式导出在此思路上重新实现。

## License

[MIT](./LICENSE) © leipengic
