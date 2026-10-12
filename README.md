# zidon

把「本地写草稿 → 人工审批 → 推 tag → GitHub 云端发布」这条链路做成可运行的代码。

**项目定位：只发布自己的内容 —— Release Notes、更新日志、文档站点。**

> **对外社交发布已整段禁用。** 本项目不会向 Mastodon / Bluesky / Telegram / Discord 发送任何内容，
> 也不做 issue 公开回复、不提交 Awesome 列表 PR。禁用是代码层的拦截，不只是配置注释，见
> [外发已整段禁用（以及如何恢复）](#外发已整段禁用以及如何恢复)。
> 想手动发到某处时，`promoter gen --kind social` 仍然可以生成本地文案，你自己复制粘贴——程序不外发。

- 本机（i3 / 16G / 无显卡）只干轻活：写发布说明草稿，不直连任何账号
- 发布动作全部在 GitHub Actions 上，用官方 API 或官方 CLI
- 只依赖 Python 标准库，不需要装任何第三方包

## 链路

```
你写代码 / README / CHANGELOG
  └─ promoter gen --kind release     本地生成发布说明草稿（可选 Ollama，没装就用模板）
       └─ promoter review               你看一眼，改一句或点确认
            └─ promoter approve --push      入库 content/approved/ 并推送（见下方「受限网络」）
                 └─ promoter release --version v0.2.0    本地建 Release（推荐的默认路径）
                      · CHANGELOG 守卫：本版本没写更新记录就拦下发布
                      · 取 content/approved/release/v0.2.0.md 作为 Release Notes
                      · 打包 dist/src-zidon-v0.2.0.tar.gz 并挂为附件
                      · 创建/更新 Release → 打印 Release URL
                           └─ 搜索引擎收录 → 陌生人点进仓库 → star / issue

（另一条路，需要 .github/workflows 已就位）
  git tag v0.2.0 && git push --tags
    └─ GitHub Actions：守卫 → 测试 → 建 Release → 部署 Pages + IndexNow →（可选）PyPI/npm/Docker
```

## 受限网络下的两个兜底（重要）

本机（以及任何 git-over-HTTPS 被重置的网络）实测过两个坑，代码里已经处理：

| 症状 | 原因 | 现在怎么办 |
| --- | --- | --- |
| `push` 报 `Recv failure: Connection was reset` | git-over-HTTPS 的 POST 被网络重置，而 `api.github.com` 正常 | `approve --push` / `push` 会**自动退回 GitHub Contents API** 上传，命令输出里会写「已改用 GitHub API 推送 N 个文件」 |
| `commit` 报 `Author identity unknown` | 新克隆的仓库没配 git 身份 | 只在身份缺失时补一份**仓库本地**身份（`zidon-bot`），不动你的全局配置 |

需要的环境变量（任选其一）：`GITHUB_TOKEN` / `GH_TOKEN` / `ZIDON_GITHUB_TOKEN`，
权限要求 **Contents: Read and write**（细粒度即可）。

> ⚠️ 已知限制：`.github/workflows/` 下的文件需要 PAT 额外具备 **Workflows** 权限，否则推送返回 403
> （`Resource not accessible by personal access token`）。该权限只能在 GitHub 网页上勾选。
> 因此 `promoter release` 把「发布」这一步做成了**本地可用**，不依赖 Actions 也能发出 Release。

## 你实际要做的 2 件事

| 时机 | 命令 | 耗时 |
| --- | --- | --- |
| 发新版本前 | `python -m promoter gen --kind release --version v0.2.0` → `python -m promoter review` → `python -m promoter approve release/v0.2.0 --push` | 约 1 分钟 |
| 正式发版 | 在 `CHANGELOG.md` 写下 `## v0.2.0` 小节 → `python -m promoter release --version v0.2.0` | 10 秒 |

## 本地准备

`config/promoter.json` 已经填好了（`repo=wan101218/zidon`、`homepage`、`install`、`one_liner`）。

```powershell
# 0. 只需要 Python 3.10+ 和 git，本工具零第三方依赖
python -m promoter doctor          # 自检：环境、模型、合规开关一目了然

# 1. （可选）装本地小模型，文案会更像人话
ollama pull qwen3:0.6b
#    没装也没关系：自动回退模板引擎，链路照样跑通，草稿结构一致
#    当前 config 的 llm.engine 已设为 template，即纯模板模式
```

## 日常用法

```powershell
# 生成发布说明（写的越具体，草稿越有用）
python -m promoter gen --kind release --version v0.2.0 `
  --summary "新增了 X，修了 Y" --highlight "支持离线模式" --highlight "启动快 3 倍"

# 审批（交互式：y 批准 / e 用编辑器改 / n 丢弃 / s 跳过 / q 退出）
python -m promoter review

# 或确认某一份并立刻推送，触发云端发布
python -m promoter approve release/v0.2.0 --push

# 打 tag 之前先本地预检 CHANGELOG（和 CI 用的是同一个守卫）
python scripts/check_changelog.py --version v0.2.0

# 发布 Release（本地走 API，不需要 Actions；会先过守卫再打包上传）
python -m promoter release --version v0.2.0
# 变体：--draft 建草稿 / --no-asset 不传源码包 / --skip-guard 跳过守卫（不推荐）

# 手动生成落地页/sitemap 到本地看一眼
python scripts/make_site.py --root . --out _site

# 想手动发到某个地方时，生成本地文案自己复制（程序不外发）
python -m promoter gen --kind social --locale zh --version v0.2.0
```

`drafts/`（未审批）已被 `.gitignore` 排除，**未审批的内容不可能进入仓库**。

## 云端配置

**不需要配置任何社交平台 token。** 现在只有三个可选的包管理器凭据：

| 名称 | 用途 | 是否必需 |
| --- | --- | --- |
| `PYPI_API_TOKEN` | 发布到 PyPI（需仓库里有 `pyproject.toml`） | 可选 |
| `NPM_TOKEN` | 发布到 npm（需有 `package.json`） | 可选 |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | 发布到 Docker Hub（需有 `Dockerfile`） | 可选 |

都没配也不影响：未配置的发布目标会被自动跳过，Release / Pages / IndexNow 照常工作。

工作流一览：

| 文件 | 触发 | 干什么 |
| --- | --- | --- |
| [ci.yml](.github/workflows/ci.yml) | push / PR | 语法检查、内容校验、生成→审批全链路自测 |
| [content.yml](.github/workflows/content.yml) | `content/approved/` 有变更 | 内容校验 + 审批结果入库（**不外发任何内容**） |
| [release.yml](.github/workflows/release.yml) | 推 `v*` tag | CHANGELOG 守卫 → 测试 → 构建 → 建 Release →（可选）发包 |
| [pages-indexnow.yml](.github/workflows/pages-indexnow.yml) | site / README / content 变更 | 部署 GitHub Pages + 生成 sitemap/robots + 提交 IndexNow |

## 外发已整段禁用（以及如何恢复）

**当前状态**：`social.enabled_platforms = []`，`compliance.allow_social_posting` / `allow_public_reply` /
`allow_awesome_pr` 均为 `false`。

**这不只是配置里的注释，是代码层的闸门。** 即使把 `DRY_RUN` 设为 `false`、token 也配齐了，
相关命令仍会直接拒绝执行：

```
$ python -m promoter publish-batch --platform mastodon
[已禁用] 批量发布到 mastodon 被 config/promoter.json 的 compliance.allow_social_posting=false 拦下，未发送任何内容。
```

被拦下的动作：`promoter publish`、`promoter publish-batch`（真实发送时）、`promoter inbox push --send`。
`drafts/social` 与 `drafts/announce` 的自动触发路径也已经从工作流里移除；`release.yml` 里的
`announce` job 已删除。`promoter gen` 仍可生成本地文案（只写文件，不外发）。

**恢复步骤**（真要做的时候，按顺序）：

1. 改 `config/promoter.json`：`social.enabled_platforms` 填平台名（`mastodon` / `bluesky` / `telegram` / `discord`），
   同时把 `compliance.allow_social_posting` 改成 `true`（要公开回 issue 再加 `allow_public_reply`）。
   两者必须一致，`scripts/lint_content.py` 会强制校验，不一致直接让 CI 失败。
2. 在仓库 Settings → Secrets and variables → Actions 里填对应平台凭据。需要哪些环境变量，
   看 [promoter/platforms.py](promoter/platforms.py) 里的 `REQUIRED_ENV`（那是唯一清单，照它填）。
3. 恢复工作流里的发送步骤：`git log` 里找回被删掉的 `announce` job 与 content.yml 的发布步骤。
4. 先保持 `DRY_RUN=true` 跑一次，确认 `publish/` 目录里的待发内容无误后再改成 `false`。

## 安全与合规（重要）

1. **人工审批前置**：`drafts/` 被 gitignore，只有 `content/approved/`（必须经 `promoter approve`）才会入库；CI 校验 `status=approved`，绕过审批的提交直接失败。
2. **合规开关真的生效**：`compliance.allow_*` 不是装饰性配置——为 `false` 时对应命令直接返回失败，不会静默放行；把 `allow_auto_follow` / `allow_auto_dm` / `allow_scraping` / `allow_mass_comment` 改成 `true` 会让 CI 直接拦下。
3. **不外发**：没有自动关注、私信、群发评论功能；社交发布 / 公开回复 / Awesome PR 三条出站路径全部关闭。
4. **CHANGELOG 守卫**：推 tag 时如果 `CHANGELOG.md` 里没有本版本小节（或小节是空的），发布会被拦下——发版就必须写更新记录。
5. **诚实**：提示词明确禁止编造功能、用户数和他人评价；超长内容在生成时截断、在 CI 里报错。
6. **IndexNow**：搜索引擎官方支持的主动推送方式。Google 与 Bing 已废弃 sitemap ping，所以这里不做 ping——不是漏了，是那两个接口已经没了。

## 目录结构

```
promoter/            本地工具（零依赖）
  main.py            CLI：gen / review / approve / reject / push / publish / inbox / sitelinks
  generate.py        组装事实 -> 调模型 -> 落盘草稿
  llm.py             Ollama 调用
  prompts.py         提示词（含防编造约束）
  templates.py       无模型时的模板兜底
  store.py           drafts/ <-> content/approved/ 与状态
  platforms.py       平台适配 + 字数上限 + 频率闸门（外发已禁用，代码保留）
  inbox.py           issue 回复（外发已禁用，代码保留）
scripts/
  lint_content.py    CI 内容校验 + 合规开关一致性
  check_changelog.py 推 tag 前的 CHANGELOG 漏写守卫
  make_site.py       落地页 + sitemap/robots + IndexNow
content/approved/    已审批内容（云端读这里）
content/state/       幂等状态
land/                首发公告草稿（人工改写后 approve 即可入库）
config/promoter.json 项目配置
site/index.html      落地页（Pages 优先用它，没有则用 README 生成）
drafts/              未审批草稿（不进 git）
```

## 常见问题

- **推 tag 时被 CHANGELOG 守卫拦下**：补写 `## v0.2.0` 小节即可；本地先跑 `python scripts/check_changelog.py --version v0.2.0` 预检。
- **Release Notes 用的是自动生成的、不是你审批过的**：检查文件名是否与 tag 一致（`content/approved/release/v0.2.0.md`，点号要保留），不一致工作流会静默退回 `--generate-notes`。
- **模型写得太空**：换大一点的模型（`qwen3:1.7b`、`llama3.2:3b`），或把 `--highlight` 写具体些——草稿质量主要取决于你给的事实。
- **想切换是否用 AI**：`config/promoter.json` 的 `llm.engine`（`ollama` / `template`），或环境变量 `PROMOTER_LLM_ENGINE=template`。
- **落地页想自己设计**：把页面放进 `site/`，工作流会用 `site/` 而不是从 README 生成。
- **PyPI 报名字被占用**：改 `project.name`，或删掉 `pyproject.toml` 相关步骤。