# 更新记录

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，每次发版的文案由本地 `promoter` 生成、人工审批后写入 `content/approved/release/<tag>.md`，再由 GitHub Actions 建 Release。

## v0.2.0

### 变更
- 新增 `promoter` CLI：本地生成 Release Notes 与草稿，模板引擎兜底（不依赖 Ollama）
- 新增 `release` 工作流：推 tag 自动测试、构建、建 Release、发布到 PyPI / npm / Docker Hub（配了 token 才跑）
- 新增 `pages-indexnow` 工作流：自动部署落地页并提交 IndexNow，同时生成 sitemap/robots
- 新增内容校验：未审批内容、超长文案、合规红线在 CI 里直接拦下
- 新增 `scripts/check_changelog.py`：**推 tag 前校验 CHANGELOG 是否漏写本版本**，漏写则拦下发布
- **已移除所有对外社交发布**：不再向 Mastodon / Bluesky / Telegram / Discord 发送任何内容
  （`social.enabled_platforms = []`，`allow_social_posting` / `allow_public_reply` / `allow_awesome_pr` 均为 `false`）
- 项目定位收敛为：**只发布自己的 Release Notes / 更新日志与文档站点**

## v0.1.0

### 变更
- 初始版本：草稿审批流、模板兜底引擎
