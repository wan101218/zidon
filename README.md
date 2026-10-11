# zidon

把「本地 AI 写草稿 → 人工审批 → git push → GitHub 云端自动发布」这条宣传链路做成可运行的代码。

- 本机（i3 / 16G / 无显卡）只干轻活：用 Ollama + 小模型写文案，**不直连任何社交账号**
- 对外发布的每一步都在 GitHub Actions 上跑，全部通过平台官方 API
- 默认 **dry-run**：先把要发的内容写成文件，你确认后才真的发
- 只依赖 Python 标准库，不需要装任何第三方包

## 链路

```
你写代码/README
  └─ promoter gen       本地生成：Release Notes / 社交草稿 / Awesome PR / issue 回复
       └─ promoter review   你看一眼，改一句或点确认
            └─ git push        推 content/approved/ 到 GitHub
                 └─ GitHub Actions 云端自动：
                      · 校验内容（未审批/超长/合规红线一律拦住）
                      · 建 Release（用你审批过的 notes）
                      · 发社交动态（Mastodon/Bluesky/Telegram/Discord，可 dry-run）
                      · 部署 GitHub Pages + 提交 IndexNow
                      · 发布到 PyPI / npm / Docker Hub（配了 token 才跑）
                           └─ 陌生人从搜索引擎/包管理器/社交平台点进仓库
                                └─ star / issue
                                     └─ promoter inbox pull   本地 AI 写回复草稿
                                          └─ 你审批 → promoter inbox push 回复
```

## 你实际只做 3 件事

| 时机 | 命令 | 耗时 |
| --- | --- | --- |
| 有新版本要宣传 | `python -m promoter gen --kind release --version v0.2.0` → `python -m promoter review` | 1 分钟 |
| 发布 | `python -m promoter approve release/v0-2-0 --push` | 10 秒 |
| 有人提 issue | `python -m promoter inbox pull` → `python -m promoter review` → `python -m promoter inbox push --send` | 1 分钟 |

## 本地准备

```powershell
# 0. 只需要 Python 3.10+ 和 git，本工具零第三方依赖
python -m promoter doctor

# 1. （可选，想要更好的文案质量）装本地小模型
ollama pull qwen3:0.6b
#    没装也没关系：会自动回退到模板引擎，链路照样跑通，草稿结构完全一致

# 2. 把项目信息填进 config/promoter.json（repo / one_liner / install / homepage）
```

## 日常用法

```powershell
# 生成版本发布文案（Release Notes + 各平台社交草稿）
python -m promoter gen --kind release --version v0.2.0 `
  --summary "新增了 X，修了 Y" --highlight "支持离线模式" --highlight "启动快 3 倍"

# 单独生成某平台某语言的一条动态
python -m promoter gen --kind social --platform mastodon --locale zh --version v0.2.0

# 写 Awesome 列表的收录条目前
python -m promoter gen --kind awesome --list awesome-selfhosted

# 审批（交互式：y 批准 / e 用编辑器改 / n 丢弃 / s 跳过 / q 退出）
python -m promoter review

# 或直接确认某一份，并立刻推送触发云端发布
python -m promoter approve release/v0-2-0 --push

# issue 回复闭环（本地读 issue 需要 GH_TOKEN，权限只要 repo 读+写评论）
$env:GH_TOKEN="github_pat_xxx"
python -m promoter inbox pull --repo yourname/zidon --limit 5
python -m promoter review
python -m promoter inbox push --repo yourname/zidon            # 默认 dry-run，只打印
python -m promoter inbox push --repo yourname/zidon --send     # 真的发出去
```

`drafts/`（未审批）已被 `.gitignore` 排除，**未审批的内容不可能被发出去**。

## 云端配置（GitHub 仓库设置）

变量（Settings → Secrets and variables → Actions → **Variables**）：

| 名称 | 用途 | 建议值 |
| --- | --- | --- |
| `DRY_RUN` | 社交发布总开关 | 先填 `true`，验证后改 `false` |
| `MASTODON_BASE_URL` | 实例地址 | `https://mastodon.social` |
| `BSKY_HANDLE` | Bluesky 账号 | `you.bsky.social` |
| `TELEGRAM_CHAT_ID` | 频道 ID | `-100xxxx` |

密钥（同一页面 → **Secrets**）：

| 名称 | 用途 |
| --- | --- |
| `MASTODON_TOKEN` | Mastodon 应用 access token |
| `BSKY_APP_PASSWORD` | Bluesky App Password（不是登录密码） |
| `TELEGRAM_BOT_TOKEN` | 自建 Bot 的 token |
| `DISCORD_WEBHOOK_URL` | 频道 Webhook 地址 |
| `PYPI_API_TOKEN` | PyPI API token（有 `pyproject.toml` 才用） |
| `NPM_TOKEN` | npm automation token（有 `package.json` 才用） |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | Docker Hub（有 `Dockerfile` 才用） |

**只填你真正要用的**：没配 token 的平台会被自动跳过，不会报错。

工作流一览：

| 文件 | 触发 | 干什么 |
| --- | --- | --- |
| [ci.yml](.github/workflows/ci.yml) | push / PR | 语法检查、内容校验、全链路自测 |
| [content.yml](.github/workflows/content.yml) | `content/approved/` 有变更（你 approve 后 push） | 校验 → 发帖（可 dry-run）→ 记录幂等状态 |
| [release.yml](.github/workflows/release.yml) | 推 `v*` tag | 测试 → 构建 → 建 Release → 发社交 → 发布 PyPI/npm/Docker |
| [pages-indexnow.yml](.github/workflows/pages-indexnow.yml) | site/README/content 变更 | 部署 GitHub Pages + 生成 sitemap/robots + 提交 IndexNow |

发布一个新版本：

```powershell
python -m promoter gen --kind release --version v0.3.0 --summary "..."
python -m promoter gen --kind social  --platform mastodon --locale zh --version v0.3.0
python -m promoter review              # 审批
git tag v0.3.0 && git push --tags      # 推 tag → 云端自动建 Release + 发社交 + 发包
```

## 安全与合规（重要）

这套东西只做合法、平台允许的事：

1. **人工审批前置**：`drafts/` 被 gitignore，只有 `content/approved/`（必须经 `promoter approve`）才会被发布；CI 会校验 `status=approved`，绕过审批的提交直接失败。
2. **只用官方 API**：Mastodon / Bluesky / Telegram / Discord / PyPI 都是公开 API，不模拟登录、不抓取页面、不违反 ToS。
3. **不做骚扰动作**：没有自动关注、自动私信、群发评论的功能，配置项 `compliance.allow_*` 全部默认为 `false`，CI 里如果被改成 `true` 会直接拦下。
4. **频率闸门**：同一平台两次发帖最小间隔（默认 60 分钟）+ 每日上限（默认 3 条），代码里强制，防止刷屏。
5. **幂等**：内容指纹记在 `content/state/published.json`，重跑工作流不会重复发帖。
6. **诚实**：提示词明确禁止编造功能、用户数和他人评价；超长内容会在生成时截断、在 CI 里报错。
7. **IndexNow**：这是搜索引擎官方支持的主动推送方式。Google 与 Bing 已废弃 sitemap ping，所以这里不做 ping——不是漏了，是那两个接口已经没了。

## 目录结构

```
promoter/           本地工具（零依赖）
  main.py           CLI：gen/review/approve/publish/inbox/sitelinks
  generate.py       组装事实 -> 调模型 -> 落盘草稿
  llm.py            Ollama 调用
  prompts.py        提示词（含防编造约束）
  templates.py      无模型时的模板兜底
  platforms.py      平台适配 + 字数上限 + 频率闸门
  inbox.py          issue 回复闭环
  store.py          drafts/ <-> content/approved/ 与状态
scripts/
  lint_content.py   CI 内容校验
  make_site.py      生成落地页 + sitemap/robots/IndexNow
content/approved/   已审批内容（云端只发这里）
content/state/      幂等状态
land/               首发公告草稿（人工改写后 approve 即可入库）
config/promoter.json 项目配置
drafts/             未审批草稿（不进 git）
```

## 常见问题

- **模型太笨/写得很空**：换大一点的模型（`qwen3:1.7b`、`llama3.2:3b`），或把 `--highlight` 写具体些，草稿质量主要取决于你给的事实。
- **想临时关掉 AI**：`config/promoter.json` 里把 `llm.engine` 改成 `template`，或设环境变量 `PROMOTER_LLM_ENGINE=template`。
- **想暂停所有发布**：仓库变量 `DRY_RUN=true`，云端只会把待发内容写进 `publish/`。
- **PyPI 报名字被占用**：`project.name` 改成你自己的包名，或删掉 `pyproject.toml` 相关步骤。