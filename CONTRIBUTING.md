# 贡献指南（Contributing）

感谢你对 Dwechatword 的关注！欢迎通过以下方式参与贡献。

## 行为准则

参与本项目即表示你同意遵守我们的[行为准则](CODE_OF_CONDUCT.md)。

## 如何贡献

### 报告 Bug

1. 先在 [Issues](https://github.com/leipengic/Dwechatword/issues) 中搜索是否已有人报告相同问题。
2. 提交新 issue 时，请包含：
   - **环境信息**：操作系统、Python 版本、依赖版本（`pip list` 中相关包）；
   - **复现步骤**：清晰的操作步骤，便于复现；
   - **期望行为 vs 实际行为**；
   - **日志**：`logs/dwechatword.log` 中的相关报错片段（请脱敏，勿贴 token/cookie）。

### 提出功能建议

在 issue 中说明该功能要解决的问题、使用场景，以及你期望的行为。如果是较复杂的功能，建议先讨论再动手。

### 提交代码（Pull Request）

1. **Fork** 本仓库并克隆到本地；
2. 从 `main` 分支创建功能分支：`git checkout -b feature/your-feature`；
3. 编写代码，并保持风格与现有代码一致；
4. 运行测试确保通过：`pytest tests/ -v`；
5. 提交清晰的 commit message（参考[约定式提交](https://www.conventionalcommits.org/zh-hans/)）；
6. 推送到你的 fork 并创建 Pull Request，描述改动内容与原因。

## 开发约定

- **Python 3.8+**，代码遵循 PEP 8；
- 新增模块请补充相应的单元测试（放入 `tests/`）；
- 涉及反爬/频控相关的改动，请在 PR 中说明默认参数是否偏保守，避免给使用者带来账号风险；
- 请勿在代码或提交中夹带任何登录凭据（token、cookie、`.env` 内容）。

## 目录速览

| 文件/目录 | 职责 |
|---|---|
| `wechat_exporter/fetcher.py` | 通道 A：后台接口分页拉取 |
| `wechat_exporter/article_fetcher.py` | 通道 B：文章页直抓 |
| `wechat_exporter/parser.py` | 文章 HTML 解析 |
| `wechat_exporter/*_writer.py` | Word / PDF / Markdown 导出 |
| `wechat_exporter/pipeline.py` | 双通道 + 多格式编排 |

## 免责声明

本项目仅供备份**自有**公众号内容使用，请勿提交任何用于抓取他人公众号、绕过平台限制或商业用途的代码。

再次感谢你的贡献！
