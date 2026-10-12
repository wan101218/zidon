# 如何使用 / 如何验证（zidon）

> 本文对应当前仓库状态（含 `promoter release` 与两个受限网络兜底）。
> 所有命令都在仓库根目录执行；只需要 **Python 3.10+**，零第三方依赖。

---

## 一、30 秒验证它在你机器上能不能用

```powershell
cd "D:\PC Projects\zidon"

python -m promoter doctor          # ① 环境自检
python -m unittest discover -s tests -v   # ② 测试（11 项）
python -m promoter gen --kind release --version v0.2.1 --summary "自检"   # ③ 生成草稿
python -m promoter queue           # ④ 看到草稿
python -m promoter reject release/v0.2.1   # ⑤ 丢掉（不污染待发队列）
```

**通过标准**

| 步骤 | 期望 |
| --- | --- |
| ① doctor | 打印「环境自检」，Python 版本行是 `[OK]`；Ollama 那行是 `[--]` 也算正常（会回退模板引擎） |
| ② 测试 | `OK`，11 项全过 |
| ③ gen | 打印草稿预览，`引擎：template` |
| ④ queue | 「待审批草稿 1 份」并列出 `release/v0.2.1` |
| ⑤ reject | 提示已丢弃，再次 queue 为空 |

---

## 二、日常发版的完整流程

```powershell
# 0) 设置 token（Contents: Read and write 即可；三个变量名任选其一）
$env:GITHUB_TOKEN = "github_pat_xxx"

# 1) 生成发布说明草稿（写得越具体，草稿越有用）
python -m promoter gen --kind release --version v0.2.2 `
  --summary "一句话总结" --highlight "变更点1" --highlight "变更点2"

# 2) 审批（交互式：y 批准 / e 编辑器改 / n 丢弃 / s 跳过 / q 退出）
python -m promoter review

#    或直接批准某一份
python -m promoter approve release/v0.2.2

# 3) 把「已批准内容」提交并上传（触发云端）
python -m promoter push
#    也支持：python -m promoter approve release/v0.2.2 --push

# 4) 在 CHANGELOG.md 写下 ## v0.2.2 小节（漏写会被守卫拦下，这是故意的）

# 5) 发布 Release（本地走 API，不需要 GitHub Actions）
python -m promoter release --version v0.2.2
```

**第 5 步会做四件事**：过 CHANGELOG 守卫 → 取 `content/approved/release/v0.2.2.md` 当 Notes →
打包 `dist/src-zidon-v0.2.2.tar.gz` → 创建/更新 Release 并挂附件，最后打印 Release URL。

常用变体：`--draft`（建草稿 Release）、`--no-asset`（不传源码包）、`--skip-guard`（跳过守卫，不推荐）。

---

## 三、怎么验证"真的发布出去了"

不要只看命令输出，直接查 GitHub：

```powershell
# 用浏览器打开（最快）
start https://github.com/wan101218/zidon/releases

# 或用 API 核对字段
curl.exe -H "Authorization: Bearer $env:GITHUB_TOKEN" `
  https://api.github.com/repos/wan101218/zidon/releases/tags/v0.2.2
```

**核对要点**

| 字段 | 期望 |
| --- | --- |
| `tag_name` / `name` | `v0.2.2` |
| `draft` / `prerelease` | 都是 `false` |
| `body` | 与你审批过的 `content/approved/release/v0.2.2.md` **逐字一致** |
| `assets` | 含 `src-zidon-v0.2.2.tar.gz` |

已实测过的证据（v0.2.1）：Release 存在、非草稿、附件 45506B、`body` 与仓库文件长度都是 224 且内容一致。

---

## 四、受限网络下的两个兜底（本机实测踩过）

| 症状 | 原因 | 现在的行为 |
| --- | --- | --- |
| `Recv failure: Connection was reset`（push 时） | 网络重置 git-over-HTTPS，但 `api.github.com` 正常 | **自动退回 GitHub Contents API** 上传，输出里会写「已改用 GitHub API 推送 N 个文件」 |
| `Author identity unknown`（commit 时） | 新克隆仓库没有 git 身份 | 只在缺失时补一份**仓库本地**身份 `zidon-bot`，不动全局配置 |

判定入口是否能走 API：

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://api.github.com
# 200 即可；若这里不通，API 兜底也没戏
```

---

## 五、已知限制（不是 bug，是权限/设计）

1. **`.github/workflows/` 推不上去**：细粒度 PAT 需要额外的 **Workflows: Read and write** 权限，
   否则 `PUT` 返回 `403 Resource not accessible by personal access token`。
   该权限只能在 GitHub 网页上勾选（Settings → Developer settings → Fine-grained tokens → 编辑该 token）。
   **影响**：`ci.yml` / `content.yml` / `release.yml` / `pages-indexnow.yml` 无法就位，GitHub Actions 那条路暂时不可用。
   **对策**：`promoter release` 已把「发布」搬到本地，不依赖 Actions。
2. **GitHub Pages 未开启**：`POST /repos/.../pages` 同样 403（token 缺 Pages 权限），
   所以 `site/index.html` 目前没有线上地址。需要你在仓库 Settings → Pages 里手动开启（Source 选 `main` / 根目录）。
3. **社交发布是"永久关闭"状态**：`social.enabled_platforms = []` 且三个 `allow_*` 开关均为 `false`，
   `publish` / `publish-batch` / `inbox push --send` 会被直接拦下。这是刻意设计，不是故障。

---

## 六、目录速查

| 路径 | 作用 |
| --- | --- |
| `promoter/` | CLI 主体：`config` `generate` `store` `release` `github_api` `platforms` `prompts` `templates` `inbox` `llm` |
| `promoter/release.py` | **本地发布 Release**（release.yml 的等价实现，走 API） |
| `promoter/store.py` | 草稿/审批/入库 + `git→API` 双通道推送 |
| `scripts/check_changelog.py` | CHANGELOG 守卫（本地与 CI 共用） |
| `scripts/lint_content.py` | 内容校验（未审批内容、超长、合规红线） |
| `scripts/make_site.py` | 生成落地页 / sitemap / robots |
| `content/approved/` | **唯一会被发布的正式内容**（必须经 `promoter approve`） |
| `drafts/` | 未审批草稿，已被 `.gitignore` 排除，绝不进仓库 |
| `tests/` | 最小测试集（unittest） |
| `dist/` | 发布产物，已 gitignore，只随 Release 附件分发 |
