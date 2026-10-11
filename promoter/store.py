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


def git_add_commit_push(paths: list[Path], message: str, push: bool = True) -> str:
    """在本地做一次最小的 add/commit/push。"""
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
    run(["commit", "-m", message])
    info = run(["log", "-1", "--format=%h %s"])
    if push:
        run(["push"])
        return f"{info}（已 push）"
    return info


def copy_tree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)