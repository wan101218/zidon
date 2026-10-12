# -*- coding: utf-8 -*-
"""本地发布 GitHub Release —— .github/workflows/release.yml 的等价实现。

为什么要有这个：release.yml 需要推到 .github/workflows/ 才能跑，而细粒度 PAT 缺
Workflows 权限会 403；同时部分网络下 git-over-HTTPS 也会被重置。
于是把「发布」这一步搬到本地，只依赖 api.github.com / uploads.github.com
（这两个在本机都正常），让系统不依赖 GitHub Actions 也能真正发布内容。

流程与 release.yml 对齐：
  1. CHANGELOG 守卫（scripts/check_changelog.py --version <tag>）
  2. 取 content/approved/release/<tag>.md 作为 Release Notes
  3. 打源码包 dist/src-zidon-<tag>.tar.gz
  4. 创建或更新 Release（标题 = tag）
  5. 上传源码包为附件
  6. 打印 Release URL
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import github_api
from .store import repo_root

EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "build", "node_modules", ".idea", ".vscode"}


def _tok() -> str:
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("ZIDON_GITHUB_TOKEN")
    if not t:
        raise github_api.ApiError("缺少 GH_TOKEN / GITHUB_TOKEN 环境变量（需 Contents: Read and write）")
    return t


def changelog_guard(root: Path, tag: str) -> tuple[bool, str]:
    """调用仓库自带的 CHANGELOG 守卫。返回 (是否通过, 说明)。"""
    script = root / "scripts" / "check_changelog.py"
    if not script.exists():
        return True, "无 CHANGELOG 守卫脚本，跳过"
    r = subprocess.run([sys.executable, str(script), "--version", tag],
                       cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, out


def build_tarball(root: Path, tag: str) -> Path:
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"src-zidon-{tag}.tar.gz"
    with tarfile.open(out, "w:gz") as tf:
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            tf.add(p, arcname=str(Path("zidon") / rel))
    return out


def find_notes(root: Path, tag: str) -> Path | None:
    base = root / "content" / "approved" / "release"
    for cand in (base / f"{tag}.md", base / f"{tag.lstrip('v')}.md"):
        if cand.exists():
            return cand
    return None


def _asset_upload(repo: str, release_id: int, path: Path, tk: str) -> str:
    """上传 Release 附件（走 uploads.github.com，需二进制体）。"""
    url = f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?" + urllib.parse.urlencode({"name": path.name})
    headers = {
        "Authorization": f"Bearer {tk}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zidon-promoter",
        "Content-Type": "application/gzip",
        "Content-Length": str(path.stat().st_size),
    }
    req = urllib.request.Request(url, data=path.read_bytes(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode()).get("browser_download_url", "ok")
    except urllib.error.HTTPError as e:
        # 同名附件已存在时先删后传
        if e.code == 422:
            return _asset_replace(repo, release_id, path, tk)
        raise github_api.ApiError(f"上传附件失败 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e


def _asset_replace(repo: str, release_id: int, path: Path, tk: str) -> str:
    assets = github_api.api("GET", f"/repos/{repo}/releases/{release_id}/assets", tk=tk)
    for a in assets:  # type: ignore[union-attr]
        if a.get("name") == path.name:
            github_api.api("DELETE", f"/repos/{repo}/releases/assets/{a['id']}", tk=tk)
    return _asset_upload(repo, release_id, path, tk)


def publish(repo: str, tag: str, notes: str | None, tarball: Path | None,
            draft: bool = False, tk: str | None = None) -> dict:
    """创建或更新 Release，返回 {id, url, created}。"""
    token = tk or _tok()
    created = False
    try:
        rel = github_api.api("GET", f"/repos/{repo}/releases/tags/{tag}", tk=token)
    except github_api.ApiError:
        rel = None

    body = {
        "tag_name": tag,
        "name": tag,
        "notes": notes or "",
        "body": notes or "",
        "draft": draft,
        "prerelease": False,
        "generate_release_notes": not bool(notes),
    }
    if rel and rel.get("id"):  # type: ignore[union-attr]
        rel_id = int(rel["id"])  # type: ignore[index]
        github_api.api("PATCH", f"/repos/{repo}/releases/{rel_id}", data=body, tk=token)
    else:
        rel = github_api.api("POST", f"/repos/{repo}/releases", data=body, tk=token)
        rel_id = int(rel["id"])  # type: ignore[index]
        created = True

    asset_url = ""
    if tarball and tarball.exists():
        asset_url = _asset_upload(repo, rel_id, tarball, token)
    return {"id": rel_id, "url": f"https://github.com/{repo}/releases/tag/{tag}", "asset": asset_url, "created": created}


def run_release(version: str, draft: bool = False, skip_guard: bool = False,
                no_asset: bool = False) -> int:
    root = repo_root()
    cfg_path = root / "config" / "promoter.json"
    repo = ""
    if cfg_path.exists():
        repo = (json.loads(cfg_path.read_text(encoding="utf-8")) or {}).get("repo", "")
    if not repo:
        from .store import detect_repo
        repo = detect_repo(root)

    tag = version if version.startswith("v") else f"v{version}"
    print(f"→ 发布 {repo} @ {tag}")

    if not skip_guard:
        ok, msg = changelog_guard(root, tag)
        print(f"  CHANGELOG 守卫：{'通过' if ok else '未通过'}")
        if msg:
            print("    " + msg.replace("\n", "\n    "))
        if not ok:
            print("  已停止：请先在本版本 CHANGELOG 里补上对应段落（与 release.yml 的守卫一致）")
            return 2

    notes_file = find_notes(root, tag)
    notes = notes_file.read_text(encoding="utf-8") if notes_file else None
    print(f"  Release Notes：{notes_file if notes_file else '（无，交给 GitHub 自动生成）'}")

    tarball = None
    if not no_asset:
        tarball = build_tarball(root, tag)
        print(f"  源码包：{tarball}（{tarball.stat().st_size / 1024:.0f}KB）")

    res = publish(repo, tag, notes, tarball, draft=draft)
    print(f"  {'已创建' if res['created'] else '已更新'} Release：{res['url']}")
    if res["asset"]:
        print(f"  附件：{res['asset']}")
    return 0
