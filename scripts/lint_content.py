"""CI 内容校验：保证云端发布的东西是经过审批的、合规的、不会被平台截断的。

在 GitHub Actions 里执行（见 .github/workflows/zidon-content.yml），也可以本地跑：
    python scripts/lint_content.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promoter import platforms  # noqa: E402

errors: list[str] = []
warnings: list[str] = []


def _check_drafts_not_tracked() -> None:
    """drafts/ 是未审批的本地草稿，绝不能进仓库（防止泄露/误发）。"""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "drafts"], cwd=str(ROOT),
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        tracked = [x for x in (out.stdout or "").splitlines() if x.strip()]
    except Exception:
        return
    if tracked:
        errors.append(f"drafts/ 有 {len(tracked)} 个文件被 git 跟踪了，未审批内容不应该入库：{tracked[:3]}")


def _check_approved() -> None:
    base = ROOT / "content" / "approved"
    if not base.exists():
        return
    for md in sorted(base.rglob("*.md")):
        meta_path = md.with_suffix(".json")
        rel = md.relative_to(ROOT)
        if not meta_path.exists():
            errors.append(f"{rel}: 缺少同名 {md.stem}.json（审批信息丢失）")
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel}: meta JSON 解析失败 {e}")
            continue

        text = md.read_text(encoding="utf-8").strip()
        if not text:
            errors.append(f"{rel}: 内容为空")
            continue
        if meta.get("status") != "approved":
            errors.append(f"{rel}: status={meta.get('status')!r}，必须是 approved（请走 promoter approve）")
        if not meta.get("approved_at"):
            errors.append(f"{rel}: 缺少 approved_at（说明不是经由审批流程入库）")
        if not meta.get("hash"):
            warnings.append(f"{rel}: 缺少内容指纹 hash，幂等去重会退化，建议重新 approve")

        platform = meta.get("platform")
        if platform:
            ok, limit = platforms.fits(platform, text)
            if not ok:
                errors.append(f"{rel}: 长度 {len(text)} 超过 {platform} 上限 {limit}，会被平台截断")
        if len(text) < 20:
            warnings.append(f"{rel}: 内容过短（{len(text)} 字符），是不是漏填了？")

        # 合规红线：不允许出现自动化骚扰/刷量的表述
        lowered = text.lower()
        for bad in ("dm me", "私信我", "免费刷", "刷量", "关注返"):
            if bad in lowered:
                errors.append(f"{rel}: 命中合规红线关键词 {bad!r}")


def _check_compliance_switch() -> None:
    cfg_file = ROOT / "config" / "promoter.json"
    if not cfg_file.exists():
        warnings.append("config/promoter.json 不存在，将使用内置默认值")
        return
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    comp = cfg.get("compliance", {})
    if not comp.get("human_approval_required", True):
        errors.append("compliance.human_approval_required 被关闭：本项目要求所有对外内容必须人工审批")
    for flag in ("allow_auto_follow", "allow_auto_dm", "allow_scraping", "allow_mass_comment"):
        if comp.get(flag):
            errors.append(f"compliance.{flag}=true：违反本项目合规原则，已阻止发布")

    # 开关与平台列表必须一致，否则「配置里写着禁用、代码里却能发」这种矛盾会一直藏着
    enabled = [p for p in cfg.get("social", {}).get("enabled_platforms", []) if p]
    if enabled and not comp.get("allow_social_posting", False):
        errors.append(f"配置矛盾：social.enabled_platforms={enabled} 但 compliance.allow_social_posting=false，"
                      "发布会被 promoter 直接拦下；两者必须一致")
    if not enabled and comp.get("allow_social_posting", False):
        errors.append("配置矛盾：compliance.allow_social_posting=true 但 social.enabled_platforms 为空，"
                      "没有任何平台会被发布")

    proj = cfg.get("project", {})
    if not (proj.get("repo") or "").strip():
        warnings.append("project.repo 为空：Release Notes 与落地页里不会出现仓库链接，外部找不到入口")
    if not (proj.get("homepage") or "").strip():
        warnings.append("project.homepage 为空：sitemap / IndexNow 只能推断地址，搜索引擎收录会不准")
    if not (proj.get("install") or "").strip():
        warnings.append("project.install 为空：落地页与 Release Notes 缺少「怎么用」这一步")


def main() -> int:
    _check_drafts_not_tracked()
    _check_approved()
    _check_compliance_switch()

    for w in warnings:
        print(f"::warning::{w}")
    for e in errors:
        print(f"::error::{e}")
    print(f"内容校验完成：{len(errors)} 个错误，{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())