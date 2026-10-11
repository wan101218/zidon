"""issue 收件箱：本地拉取 issue -> 本地模型写回复草稿 -> 你审批 -> 再回复。

注意：回复也走人工审批，不做自动秒回（那样既容易出错，也容易被判为机器人刷屏）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import generate, github_api, store

REPLIED_STATE = ("content", "state", "replied.json")

_BUG = ("bug", "crash", "error", "报错", "崩溃", "失败", "exception", "traceback", "不工作")
_FEATURE = ("feature", "enhancement", "request", "建议", "希望", "支持", "能加")


def guess_kind(issue: dict) -> str:
    labels = " ".join(l.get("name", "") for l in issue.get("labels", []) or []).lower()
    blob = f"{labels} {issue.get('title', '')}".lower()
    if any(k in blob for k in _BUG):
        return "bug"
    if any(k in blob for k in _FEATURE):
        return "feature"
    return "question"


def _state_path() -> Path:
    return store.repo_root().joinpath(*REPLIED_STATE)


def _load_replied() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(store.read_text(p))
        except Exception:
            pass
    return {"replied": []}


def _save_replied(state: dict) -> None:
    store.write_text(_state_path(), json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _already_replied(state: dict, repo: str, number: int) -> bool:
    return any(r.get("repo") == repo and int(r.get("number", 0)) == int(number) for r in state.get("replied", []))


def pull(cfg: dict, repo: str, limit: int = 5, label: str | None = None, engine_state: dict | None = None) -> list[dict]:
    """抓取待处理 issue 并为每条生成一份回复草稿。"""
    issues = github_api.list_issues(repo, limit=limit, label=label)
    state = _load_replied()
    made = []
    for it in issues:
        num = int(it.get("number", 0))
        if _already_replied(state, repo, num):
            print(f"[跳过] #{num} 已有回复记录")
            continue
        existing = list(store.drafts_dir().rglob(f"issue-{num}.md"))
        if existing or (store.approved_dir() / "reply" / f"issue-{num}.md").exists():
            print(f"[跳过] #{num} 已有回复草稿")
            continue

        kind = guess_kind(it)
        author = (it.get("user") or {}).get("login", "")

        class A:  # 复用 generate 的参数协议
            pass

        a = A()
        a.issue, a.title, a.body, a.author = num, it.get("title", ""), it.get("body", "") or "", author
        a.issue_kind, a.label = kind, [l.get("name", "") for l in it.get("labels", []) or []]
        a.kind = "reply"

        path, meta = generate.generate("reply", cfg, a, engine_state if engine_state is not None else {})
        # 追加 issue 链接，方便你点开看上下文
        store.write_text(path, store.read_text(path).rstrip()
                         + f"\n\n<!-- issue: {it.get('html_url', '')} 作者: {author} -->\n")
        meta["issue_url"] = it.get("html_url", "")
        store.write_text(path.with_suffix(".json"), json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"[草稿] #{num} {it.get('title', '')}  -> {path}")
        made.append(meta)
    if not made:
        print("没有新的 issue 需要回复草稿。")
    else:
        print(f"\n下一步：python -m promoter review   （逐条审批，或 python -m promoter reject reply/issue-N）")
    return made


def _extract(body: str) -> str:
    """去掉草稿末尾我们自动加的 issue 注释行，其余照原样发出。"""
    return re.sub(r"\n*<!--\s*issue:.*?-->\s*$", "", body, flags=re.S).strip()


def push(cfg: dict, repo: str, slugs: list[str] | None = None, dry_run: bool = True) -> int:
    """把已批准的回复发到 GitHub。默认 dry-run，只打印将要发送的内容。"""
    items = []
    for md in sorted((store.approved_dir() / "reply").glob("*.md")) if (store.approved_dir() / "reply").exists() else []:
        slug = f"reply/{md.stem}"
        if slugs and slug not in slugs and md.stem not in slugs:
            continue
        meta_path = md.with_suffix(".json")
        meta = json.loads(store.read_text(meta_path)) if meta_path.exists() else {}
        num = int(meta.get("issue_number") or re.sub(r"\D", "", md.stem) or 0)
        if num:
            items.append((num, md, meta))

    if not items:
        print("没有已批准的回复。流程：python -m promoter review 审批后再执行本命令。")
        return 0

    state = _load_replied()
    rc = 0
    for num, md, meta in items:
        body = _extract(store.read_text(md))
        if _already_replied(state, repo, num):
            print(f"[跳过] #{num} 已回复过（幂等）")
            continue
        if dry_run:
            print(f"--- 将要评论 #{num} {meta.get('issue_title', '')} ---")
            print(body)
            print("--- 结束（dry-run，未发送）---")
            continue
        try:
            out = github_api.comment_issue(repo, num, body)
        except github_api.ApiError as e:
            print(f"[失败] #{num}: {e}")
            rc = 1
            continue
        state.setdefault("replied", []).append({"repo": repo, "number": num, "at": store.now_iso(),
                                                "url": out.get("html_url", ""), "slug": md.stem})
        _save_replied(state)
        print(f"[已回复] #{num} -> {out.get('html_url', '')}")
    return rc