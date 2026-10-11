"""草稿生成：组装事实上下文 -> 调本地模型 -> 后处理 -> 落盘到 drafts/。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import config as cfg_mod
from . import llm as llm_mod
from . import platforms, prompts, store, templates

LOCALE_LABEL = {"zh": "中文", "en": "English", "ja": "日本語"}


def git(args: list[str], root: Path | None = None) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(root or store.repo_root()),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def latest_tag(root: Path | None = None) -> str:
    return git(["describe", "--tags", "--abbrev=0"], root) or "v0.1.0"


def recent_changes(count: int = 12, root: Path | None = None) -> list[str]:
    out = git(["log", f"-{count}", "--pretty=- %s"], root)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def base_context(cfg: dict) -> dict:
    proj = cfg.get("project", {})
    return {
        "project": proj.get("name", "项目"),
        "url": cfg_mod.project_url(cfg),
        "one_liner": proj.get("one_liner", ""),
        "install": proj.get("install", ""),
        "keywords": proj.get("keywords", []),
        "license": proj.get("license", ""),
    }


def build_context(kind: str, cfg: dict, args) -> dict:
    ctx = base_context(cfg)
    if kind == "release":
        version = getattr(args, "version", None) or latest_tag()
        ctx.update({
            "version": version,
            "summary": getattr(args, "summary", "") or "",
            "highlights": [h.strip() for h in (getattr(args, "highlight", None) or [])],
            "changes": recent_changes(),
        })
    elif kind in ("social", "announce"):
        enabled = [p for p in cfg["social"].get("enabled_platforms", []) if p]
        locales = [x for x in cfg["social"].get("locales", []) if x]
        # 平台列表可以为空（此时只产出通用文案，供你手动复制到任何地方，不会自动外发）
        platform = getattr(args, "platform", None) or (enabled[0] if enabled else "generic")
        locale = getattr(args, "locale", None) or (locales[0] if locales else "zh")
        ctx.update({
            "platform": platform,
            "locale": locale,
            "locale_label": LOCALE_LABEL.get(locale, locale),
            "version": getattr(args, "version", None) or "",
            "highlights": [h.strip() for h in (getattr(args, "highlight", None) or [])] or recent_changes(5),
        })
    elif kind == "awesome":
        ctx.update({
            "list_name": getattr(args, "list", None) or "awesome-list",
            "summary": getattr(args, "summary", "") or "",
        })
    elif kind == "reply":
        ctx.update({
            "issue_number": getattr(args, "issue", None) or "?",
            "issue_title": getattr(args, "title", "") or "",
            "issue_body": (getattr(args, "body", "") or "")[:2000],
            "issue_author": getattr(args, "author", "") or "",
            "issue_kind": getattr(args, "issue_kind", None) or "unknown",
            "issue_labels": [x.strip() for x in (getattr(args, "label", None) or [])],
        })
    return ctx


def _template_for(kind: str, ctx: dict) -> str:
    fn = {
        "release": templates.release,
        "social": templates.social,
        "announce": lambda c: templates.social({**c, "locale": "zh"}),
        "awesome": templates.awesome,
        "reply": templates.reply,
    }[kind]
    return fn(ctx)


def _postprocess(kind: str, text: str, ctx: dict, cfg: dict) -> str:
    text = (text or "").strip()
    if kind in ("social", "announce"):
        platform = ctx.get("platform", "generic")
        if cfg["social"].get("append_url") and ctx.get("url") and ctx["url"] not in text:
            text = f"{text}\n{ctx['url']}"
        ok, limit = platforms.fits(platform, text)
        if not ok:
            keep = max(0, limit - 2)
            text = text[:keep].rsplit("\n", 1)[0].rstrip() + " …"
    return text


def generate(kind: str, cfg: dict, args, engine_state: dict) -> tuple[Path, dict]:
    """生成并落盘。engine_state 用于把“本批次用了哪个引擎”回传给调用方。"""
    if kind not in store.KINDS:
        raise ValueError(f"未知类型 {kind}，支持：{', '.join(store.KINDS)}")
    ctx = build_context(kind, cfg, args)

    body, engine, note = None, "template", ""
    if cfg["llm"].get("engine") == "ollama":
        try:
            body = llm_mod.chat(prompts.build(kind, ctx), cfg)
            engine = f"ollama:{cfg['llm']['model']}"
        except llm_mod.LLMError as e:
            if not cfg["llm"].get("fallback_to_template", True):
                raise
            note = f"模型不可用，已回退模板：{e}"
    if body is None:
        body = _template_for(kind, ctx)

    body = _postprocess(kind, body, ctx, cfg)
    if kind == "release":
        # 用 safe_name 而不是 slugify：文件名与 git tag 保持一致（v0.2.0.md）
        slug = store.safe_name(ctx.get("version") or "release")
    elif kind == "social":
        slug = store.slugify(f"{ctx.get('platform')}-{ctx.get('locale')}-{ctx.get('version') or ''}")
    elif kind == "reply":
        slug = store.slugify(f"issue-{ctx.get('issue_number')}")
    else:
        slug = store.slugify(ctx.get("version") or ctx.get("title") or ctx.get("locale") or kind)

    meta = {**ctx, "engine": engine, "note": note, "template_used": engine == "template"}
    path = store.write_draft(kind, slug, body, meta)
    # write_draft 可能为避免重名而改名，回读最终 slug
    meta["slug"] = f"{path.parent.name}/{path.stem}"
    engine_state["engine"] = engine
    engine_state["note"] = note
    return path, meta