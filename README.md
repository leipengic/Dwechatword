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

## 主要第三方库

按用途归类，均为 `requirements.txt` 中已声明且代码中实际调用的库。

### 浏览器自动化与网络请求

| 库 | 在项目中做的事 | 为什么选它 |
|---|---|---|
| `playwright` | `login.py` 启动 Edge/Chromium 打开公众平台，人工扫码后从跳转 URL 提取 `token` 并持久化 cookies | 公众平台登录只有人机扫码一条路，Selenium 之外 Playwright 的等待与反检测更省心；下载 Chromium 失败时可直接用系统浏览器 |
| `requests` | 两套通道的 HTTP 请求：后台接口分页、文章页直抓、图片下载 | 会话对象（`Session`）复用 cookies 与连接，配合自定义请求头最简单直接；项目无需异步并发 |

### 页面解析

| 库 | 在项目中做的事 | 为什么选它 |
|---|---|---|
| `beautifulsoup4` | `parser.py` 用 CSS 选择器定位 `#activity-name`、`#publish_time`、`#js_content`，再深度优先遍历产出结构化内容块 | 面对微信不规则的手写 HTML，容错性远好于正则与严格 XML 解析，改版时改选择器即可 |
| `lxml` | 作为 BeautifulSoup 的底层解析器（`BeautifulSoup(html, "lxml")`） | 比内置 `html.parser` 快一个量级，大批量文章导出时差距明显 |

### 文档导出

| 库 | 在项目中做的事 | 为什么选它 |
|---|---|---|
| `python-docx` | `docx_writer.py` 生成 Word：标题、元信息灰字区、正文宋体小四与 1.5 倍行距、首行缩进、图片居中按页宽缩放 | 无需装 Office 即可写 `.docx`，对段落样式与图片布局的控制粒度足够 |
| `Pillow` | 插入 Word 前读取图片原始尺寸，按页宽等比缩放 | 事实上的 Python 图像处理标准库，本项目只用到读取尺寸这一最小能力 |
| `WeasyPrint` | `pdf_writer.py` 先渲染自包含 HTML（图片 base64 内联、声明中文字体）再转 PDF | 可直接复用 CSS 排版能力，中文字体与图片处理比 ReportLab 等方案省事；**可选依赖**，不导 PDF 可不装 |

### 配置

| 库 | 在项目中做的事 | 为什么选它 |
|---|---|---|
| `python-dotenv` | 读取 `.env` 中的 `MP_ACCOUNT_NAME`、间隔、重试等参数 | 账号与频率参数需要频繁调整，放 `.env` 比对命令行手工输入更友好，也避免把配置写进代码 |

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

## 鸣谢（Acknowledgments）

感谢以下开源项目与开发者（图标均取自官方站点 / CDN）：

<table>
  <tr>
    <td align="center" width="140">
      <a href="https://github.com/qiye45">
        <img src="https://github.com/qiye45.png?size=120" width="64" height="64" alt="qiye45" /><br />
        <sub><b>qiye45（长风）</b></sub>
      </a>
      <br />
      <sub><a href="https://github.com/qiye45/wechatDownload">wechatDownload</a> 作者</sub>
    </td>
    <td align="center" width="140">
      <a href="https://www.jetbrains.com/idea/">
        <img src="https://resources.jetbrains.com/storage/products/intellij-idea/img/meta/intellij-idea_logo_300x300.png" width="64" height="64" alt="IntelliJ IDEA" /><br />
        <sub><b>IntelliJ IDEA</b></sub>
      </a>
      <br />
      <sub>JetBrains 出品</sub>
    </td>
    <td align="center" width="140">
      <a href="https://www.jetbrains.com/pycharm/">
        <img src="https://resources.jetbrains.com/storage/products/pycharm/img/meta/pycharm_logo_300x300.png" width="64" height="64" alt="PyCharm" /><br />
        <sub><b>PyCharm</b></sub>
      </a>
      <br />
      <sub>JetBrains 出品</sub>
    </td>
  </tr>
</table>

| 项目 / 库 | 贡献 | 许可证 |
|---|---|---|
| [qiye45/wechatDownload](https://github.com/qiye45/wechatDownload) | 思路来源：文章抓取的整体流程与参数设计 | _（待补充：原仓库 LICENSE 未在本项目内核验，使用前请自行确认）_ |
| [Playwright](https://github.com/microsoft/playwright) | 扫码登录与会话持久化 | Apache-2.0 |
| [requests](https://github.com/psf/requests) | 所有 HTTP 请求 | Apache-2.0 |
| [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/) | 文章 HTML 解析 | MIT |
| [lxml](https://lxml.de/) | 高性能底层解析器 | BSD-3-Clause |
| [python-docx](https://github.com/python-openxml/python-docx) | Word 导出 | MIT |
| [Pillow](https://python-pillow.org/) | 读取图片尺寸用于排版 | HPND |
| [WeasyPrint](https://weasyprint.org/) | HTML → PDF 渲染（可选依赖） | BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `.env` 配置加载 | BSD-3-Clause |
| [JetBrains](https://www.jetbrains.com/) | 提供 IntelliJ IDEA / PyCharm 等开发工具 | 商业授权（开源项目可申请免费许可证） |

> 贡献者名单：_（待补充，欢迎在 PR 中署名）_

## License

[MIT](./LICENSE) © leipengic
