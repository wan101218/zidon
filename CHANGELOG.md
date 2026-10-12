# 更新记录

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，每次发版的文案由本地 `promoter` 生成、人工审批后写入 `content/approved/release/<tag>.md`，再由 `promoter release`（或 GitHub Actions）建 Release。

## v0.2.1

### 修复
- **修复受限网络下 `push` 必然失败**：原来只走 `git push`，而部分网络会把 git-over-HTTPS 的请求直接重置
  （`Recv failure: Connection was reset`）。现在 `git push` 失败会自动退回 **GitHub Contents API** 上传，
  保证「审批 → 上传 → 触发云端」在任何能访问 `api.github.com` 的环境都能走通
- **修复新克隆仓库首次提交失败**：仓库未配置 git 身份时 `git commit` 会报
  `Author identity unknown`。现在只在身份缺失时补一份**仓库本地**身份（不动全局配置）

### 新增
- 新增 `promoter release` 子命令：**本地发布 GitHub Release**，作为 `release.yml` 的等价实现
  - 与工作流一致：先过 CHANGELOG 守卫 → 取 `content/approved/release/<tag>.md` 作为 Notes →
    打包 `dist/src-zidon-<tag>.tar.gz` → 创建/更新 Release → 上传附件 → 打印 Release URL
  - 存在的意义：`.github/workflows/` 需要 `Workflows` 权限才能推送，缺权限时云端自动化无法就位；
    把「发布」这一步搬到本地后，系统不依赖 GitHub Actions 也能真正发布内容
  - 未写 CHANGELOG 时会被守卫直接拦下（exit 2），与 CI 行为一致

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
