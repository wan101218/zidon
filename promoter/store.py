"""草稿仓库：drafts/（未审批，不进 git） -> content/approved/（已审批，会被 CI 发布）。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

KINDS = ("release", "social", "announce", "awesome", "reply")


def repo_root() -> Path:
    """定位仓库根目录：优先环境变量，其次 git，最后按包位置推断。"""
    env = os.environ.get("PROMOTER_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(here),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        root = out.stdout.strip()
        if root:
            return Path(root).resolve()
    except Exception:
        pass
    return here.parent


def drafts_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "drafts"


def approved_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "content" / "approved"


def state_file(root: Path | None = None) -> Path:
    return (root or repo_root()) / "content" / "state" / "published.json"


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:60] or "draft"


_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\s]+')


def safe_name(text: str) -> str:
    """文件名安全化，但保留点号 —— 版本号要能和 git tag 对上（v0.2.0 -> v0.2.0.md）。"""
    name = _UNSAFE_NAME.sub("-", (text or "").strip()).strip("-. ")
    return name[:60] or "draft"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_draft(kind: str, slug: str, body: str, meta: dict) -> Path:
    """写一份草稿：<slug>.md 给人看，<slug>.json 给程序看。"""
    base = drafts_dir() / kind
    base.mkdir(parents=True, exist_ok=True)
    stem, n = slug, 2
    while (base / f"{stem}.md").exists():
        stem, n = f"{slug}-{n}", n + 1
    meta = dict(meta or {})
    meta.update({"kind": kind, "slug": f"{kind}/{stem}", "created_at": now_iso(), "status": "pending"})
    md = base / f"{stem}.md"
    write_text(md, body.rstrip() + "\n")
    write_text(base / f"{stem}.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return md


def pending_drafts() -> list[dict]:
    out: list[dict] = []
    root = drafts_dir()
    if not root.exists():
        return out
    for md in sorted(root.rglob("*.md")):
        meta_path = md.with_suffix(".json")
        meta = json.loads(read_text(meta_path)) if meta_path.exists() else {
            "kind": md.parent.name,
            "slug": f"{md.parent.name}/{md.stem}",
        }
        meta["_md"] = str(md)
        meta["_meta"] = str(meta_path)
        meta["_body"] = read_text(md)
        out.append(meta)
    return out


def resolve(slug: str) -> tuple[Path, Path]:
    """接受 'release/xxx'、'xxx' 或完整路径，返回 (md, meta) 两个路径。"""
    root = drafts_dir()
    s = slug.replace("\\", "/").strip()
    if s.endswith(".md") or s.endswith(".json"):
        p = Path(s)
        if not p.is_absolute():
            p = repo_root() / s
        return p.with_suffix(".md"), p.with_suffix(".json")
    if "/" in s:
        kind, stem = s.split("/", 1)
        return root / kind / f"{stem}.md", root / kind / f"{stem}.json"
    hits = list(root.rglob(f"{s}.md"))
    if not hits:
        raise FileNotFoundError(f"找不到草稿: {slug}")
    if len(hits) > 1:
        raise FileExistsError(f"草稿名不唯一: {slug} -> {[str(h) for h in hits]}")
    return hits[0], hits[0].with_suffix(".json")


def approve(slug: str) -> Path:
    """把草稿从 drafts/ 移到 content/approved/，并记录内容指纹。"""
    md, meta_path = resolve(slug)
    if not md.exists():
        raise FileNotFoundError(f"找不到草稿: {md}")
    body = read_text(md)
    meta = json.loads(read_text(meta_path)) if meta_path.exists() else {}
    meta.update({"status": "approved", "approved_at": now_iso(), "hash": sha256(body)})
    kind = meta.get("kind") or md.parent.name
    dst_dir = approved_dir() / kind
    dst_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(meta.get("slug", f"{kind}/{md.stem}")).name
    write_text(dst_dir / f"{stem}.md", body)
    write_text(dst_dir / f"{stem}.json", json.dumps(meta, ensure_ascii=False, indent=2))
    for p in (md, meta_path):
        if p.exists():
            p.unlink()
    _cleanup_empty(md.parent)
    return dst_dir / f"{stem}.md"


def reject(slug: str, delete: bool = True) -> Path:
    md, meta_path = resolve(slug)
    if delete:
        for p in (md, meta_path):
            if p.exists():
                p.unlink()
        _cleanup_empty(md.parent)
    return md


def _cleanup_empty(d: Path) -> None:
    root = drafts_dir()
    try:
        while d != root and d.exists() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    except Exception:
        pass


def approved_drafts(kind: str | None = None) -> list[dict]:
    out: list[dict] = []
    base = approved_dir() / kind if kind else approved_dir()
    if not base.exists():
        return out
    for md in sorted(base.rglob("*.md")):
        meta_path = md.with_suffix(".json")
        meta = json.loads(read_text(meta_path)) if meta_path.exists() else {}
        meta["_md"] = str(md)
        meta["_body"] = read_text(md)
        out.append(meta)
    return out


def load_state() -> dict:
    f = state_file()
    if f.exists():
        try:
            return json.loads(read_text(f))
        except Exception:
            pass
    return {"posted": []}


def save_state(state: dict) -> Path:
    return write_text(state_file(), json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def already_posted(state: dict, platform: str, digest: str) -> bool:
    return any(p.get("platform") == platform and p.get("hash") == digest for p in state.get("posted", []))


def record_post(state: dict, platform: str, digest: str, slug: str, detail: str = "") -> None:
    state.setdefault("posted", []).append(
        {"platform": platform, "hash": digest, "slug": slug, "at": now_iso(), "detail": detail}
    )


def detect_repo(root: Path) -> str:
    """从 git remote 解析出 owner/repo。"""
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    url = (r.stdout or "").strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError(f"无法从 remote 解析 owner/repo：{url!r}")
    return m.group(1)


def api_push(paths: list[Path], message: str, branch: str = "main") -> int:
    """用 GitHub Contents API 推送文件。

    存在的理由：部分网络会把 git-over-HTTPS 的 POST 直接重置
    （Recv failure: Connection was reset），而 api.github.com 正常。
    此时 git push 永远失败，但 API 可以推上去。

    token 取环境变量 GITHUB_TOKEN 或 ZIDON_GITHUB_TOKEN（需 Contents: Read and write）。
    """
    import base64
    import json as _json
    import os as _os
    import urllib.error
    import urllib.request

    token = _os.environ.get("GITHUB_TOKEN") or _os.environ.get("ZIDON_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("缺少 GITHUB_TOKEN / ZIDON_GITHUB_TOKEN，无法走 API 推送")

    root = repo_root()
    repo = _os.environ.get("ZIDON_REPO") or detect_repo(root)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zidon-promoter",
        "Content-Type": "application/json",
    }

    def call(method: str, url: str, body: dict | None = None):
        data = _json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, (_json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, _json.loads(raw)
            except Exception:  # noqa: BLE001
                return e.code, {"message": raw[:200]}

    pushed = 0
    base = f"https://api.github.com/repos/{repo}/contents"
    # git status 对未跟踪目录只报一个目录项，这里展开成文件，避免静默漏传；
    # 同时过滤掉不该入库的东西（__pycache__/.pyc/dist 等），否则 API 通道会绕过 .gitignore。
    skip_dirs = {"__pycache__", ".git", "dist", "build", "_site", ".venv", "venv",
                 "node_modules", ".pytest_cache", ".idea", ".vscode"}
    files: list[Path] = []

    def _keep(p: Path) -> bool:
        if any(part in skip_dirs for part in p.parts):
            return False
        return p.suffix.lower() not in {".pyc", ".pyo"}

    for p in paths:
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.is_file() and _keep(q.relative_to(root))))
        elif p.is_file() and _keep(p.relative_to(root)):
            files.append(p)
    for p in files:
        rel = p.relative_to(root).as_posix()
        code, cur = call("GET", f"{base}/{rel}?ref={branch}")
        body = {
            "message": message,
            "content": base64.b64encode(p.read_bytes()).decode(),
            "branch": branch,
        }
        if code == 200 and cur.get("sha"):
            body["sha"] = cur["sha"]
        code, res = call("PUT", f"{base}/{rel}", body)
        if code not in (200, 201):
            raise RuntimeError(f"API 推送 {rel} 失败：HTTP {code} {res.get('message')}")
        pushed += 1
    return pushed


def git_add_commit_push(paths: list[Path], message: str, push: bool = True) -> str:
    """在本地做一次最小的 add/commit/push。

    push 阶段：先试 git push；若因网络（git-over-HTTPS 被重置）失败，
    自动退回 GitHub Contents API，保证「审批 → 上传 → 触发云端」在受限网络下也能走通。
    """
    root = repo_root()
    rel = [str(p.relative_to(root)) for p in paths if p.exists()]

    def run(args: list[str]) -> str:
        r = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} 失败: {(r.stderr or r.stdout).strip()}")
        return (r.stdout or "").strip()

    if rel:
        run(["add", "--", *rel])
    status = run(["status", "--porcelain", "--", *rel]) if rel else ""
    if not status:
        return "没有需要提交的变更"

    # 仓库若没配 git 身份，commit 会直接失败（Author identity unknown）。
    # 只在缺失时补一份仓库本地身份，不动全局配置。
    ident = subprocess.run(["git", "config", "user.email"], cwd=str(root),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ident.returncode != 0 or not (ident.stdout or "").strip():
        run(["config", "user.email", "zidon-bot@users.noreply.github.com"])
        run(["config", "user.name", "zidon-bot"])

    run(["commit", "-m", message])
    info = run(["log", "-1", "--format=%h %s"])
    if not push:
        return info
    try:
        run(["push"])
        return f"{info}（已 push）"
    except RuntimeError as exc:
        try:
            n = api_push([root / r for r in rel], message)
        except Exception as exc2:  # noqa: BLE001
            raise RuntimeError(f"git push 失败（{exc}）；API 兜底也失败：{exc2}") from exc2
        return f"{info}（git push 失败，已改用 GitHub API 推送 {n} 个文件）"


def copy_tree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)