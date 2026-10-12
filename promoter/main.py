"""promoter CLI。

  本地（草稿）：
    python -m promoter doctor
    python -m promoter gen --kind social --platform mastodon --locale zh
    python -m promoter gen --kind release --version v0.2.0 --summary "修复了..."
    python -m promoter queue
    python -m promoter approve release/v0-2-0 [--push]
    python -m promoter reject social/mastodon-zh-v0-2-0
    python -m promoter push --draft release/v0-2-0

  云端（GitHub Actions 调用，见 .github/workflows/）：
    python -m promoter publish --platform mastodon -f content/approved/social/x.md
    python -m promoter sitelinks --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config as cfg_mod
from . import generate, llm as llm_mod, platforms, store

# Windows 控制台默认 GBK，强制 UTF-8 避免中文草稿乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


# ---------------------------------------------------------------- 合规闸门

def _outbound_blocked(cfg: dict, flag: str, action: str) -> bool:
    """对外发送类动作的统一闸门：开关为 false 时直接拒绝执行，绝不静默放行。"""
    if cfg.get("compliance", {}).get(flag, False):
        return False
    print(f"[已禁用] {action} 被 config/promoter.json 的 compliance.{flag}=false 拦下，未发送任何内容。",
          file=sys.stderr)
    print(f"           本项目当前策略是只做自己的 Release Notes 与文档站点；"
          f"确需启用请把 {flag} 改为 true，并自行确认符合对应平台规则。", file=sys.stderr)
    return True


# ---------------------------------------------------------------- doctor

def cmd_doctor(args) -> int:
    cfg = cfg_mod.load()
    print("== 环境自检 ==")
    print(f"[OK] Python {sys.version.split()[0]}")

    ok, info = llm_mod.ping(cfg)
    if ok:
        print(f"[OK] Ollama 可用，模型：{info}")
    else:
        print(f"[--] Ollama 不可用：{info}")
        print("     → 不影响使用，草稿会自动回退到模板；装了模型质量更好：")
        print(f"       ollama pull {cfg['llm']['model']}")

    dry = cfg["social"].get("dry_run", True)
    print(f"[{'OK' if dry else '!!'}] 社交发布 dry-run = {dry}  （安全模式建议保持 true，直到你验证过草稿）")
    print(f"[--] 已启用平台：{', '.join(cfg['social'].get('enabled_platforms', [])) or '（无）'}")
    for pf in cfg["social"].get("enabled_platforms", []):
        need = platforms.REQUIRED_ENV.get(pf, [])
        have = [k for k in need if os.environ.get(k)]
        print(f"      {pf}: 本地 {'/'.join(need)} → {len(have)}/{len(need)} 已设置"
              f"（本地无需设置，token 放在 GitHub Secrets）")
    print(f"[OK] 待审批草稿：{len(store.pending_drafts())} 份 -> {store.drafts_dir()}")
    c = cfg["compliance"]
    print("[合规开关] 人工审批=%s 自动关注=%s 自动私信=%s 抓取=%s 群发评论=%s"
          % (c.get("human_approval_required"), c.get("allow_auto_follow"),
             c.get("allow_auto_dm"), c.get("allow_scraping"), c.get("allow_mass_comment")))
    for flag, label in (("allow_social_posting", "对外社交发布"),
                        ("allow_public_reply", "issue 公开回复"),
                        ("allow_awesome_pr", "Awesome 列表 PR")):
        on = c.get(flag, False)
        print(f"[{'!!' if on else '--'}] {label}：{'已启用' if on else '已禁用（相关命令会被直接拦下）'}")
    return 0


# ---------------------------------------------------------------- gen

def cmd_gen(args) -> int:
    cfg = cfg_mod.load()
    engine_state: dict = {}
    path, meta = generate.generate(args.kind, cfg, args, engine_state)
    print(f"[生成] {path}")
    print(f"       引擎：{engine_state.get('engine')}")
    if engine_state.get("note"):
        print(f"       注意：{engine_state['note']}")
    print("       ---- 草稿预览 ----")
    for line in store.read_text(path).splitlines():
        print("       " + line)
    print("       ------------------")
    if args.kind == "awesome" and not cfg["compliance"].get("allow_awesome_pr", False):
        print("[提示] compliance.allow_awesome_pr=false：这份草稿仅供本地参考，不要提交到外部 Awesome 列表。")
    print(f"\n下一步：审阅后执行  python -m promoter approve {meta['slug']} --push")
    return 0


# ---------------------------------------------------------------- queue

def cmd_queue(args) -> int:
    drafts = store.pending_drafts()
    if not drafts:
        print("没有待审批草稿。先生成：python -m promoter gen --kind social")
        return 0
    print(f"待审批草稿 {len(drafts)} 份：\n")
    for i, d in enumerate(drafts, 1):
        body = d["_body"].strip().replace("\n", " ")
        if len(body) > 100:
            body = body[:100] + "…"
        print(f"{i}. [{d.get('kind')}] {d.get('slug')}")
        print(f"   引擎: {d.get('engine', '-')}   创建: {d.get('created_at', '-')}")
        print(f"   预览: {body}\n")
    print("审批：python -m promoter approve <slug> --push    丢弃：python -m promoter reject <slug>")
    print("批量交互审批：python -m promoter review")
    return 0


# ---------------------------------------------------------------- review（交互式审批）

def cmd_review(args) -> int:
    drafts = store.pending_drafts()
    if not drafts:
        print("没有待审批草稿。")
        return 0
    approved: list[Path] = []
    for d in drafts:
        print("=" * 66)
        print(f"[{d.get('kind')}] {d.get('slug')}  (engine={d.get('engine', '-')})")
        print("-" * 66)
        print(d["_body"].rstrip())
        print("-" * 66)
        try:
            ans = input("批准并入库？[y] 批准 / [e] 用编辑器改 / [n] 丢弃 / [s] 跳过 / [q] 退出 > ").strip().lower()
        except EOFError:
            break
        if ans == "q":
            break
        if ans == "e":
            _open_editor(Path(d["_md"]))
            print("已用编辑器打开。改完请重跑 review 再确认。")
            continue
        if ans == "y":
            approved.append(store.approve(d["slug"]))
        elif ans == "n":
            store.reject(d["slug"])
            print(f"已丢弃 {d['slug']}")
        else:
            print(f"已跳过 {d['slug']}")
    if approved:
        print(f"\n已入库 {len(approved)} 份 -> {store.approved_dir()}")
        if not args.no_push:
            try:
                msg = f"content: approve {len(approved)} draft(s)"
                print(store.git_add_commit_push(approved + [p.with_suffix('.json') for p in approved], msg, push=True))
            except Exception as e:  # noqa: BLE001
                print(f"push 失败（可稍后手动 git push）：{e}", file=sys.stderr)
    return 0


def _open_editor(path: Path) -> None:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        os.startfile(str(path))  # type: ignore[attr-defined]  # Windows 用默认程序打开
        return
    import subprocess
    subprocess.run([editor, str(path)], check=False)


# ---------------------------------------------------------------- approve / reject / push

def cmd_approve(args) -> int:
    paths = []
    for slug in args.slug:
        dst = store.approve(slug)
        paths.append(dst)
        paths.append(dst.with_suffix(".json"))
        print(f"[批准] {slug} -> {dst}")
    if args.push:
        try:
            print(store.git_add_commit_push(paths, f"content: approve {', '.join(args.slug)}", push=True))
        except Exception as e:  # noqa: BLE001
            print(f"push 失败：{e}", file=sys.stderr)
            return 1
    else:
        print("\n提示：加 --push 可直接提交并推送，触发云端发布。")
    return 0


def cmd_reject(args) -> int:
    for slug in args.slug:
        store.reject(slug, delete=not args.keep)
        print(f"[丢弃] {slug}")
    return 0


def cmd_push(args) -> int:
    if args.draft:
        paths: list[Path] = []
        for slug in args.draft:
            md, meta = store.resolve(slug)
            paths += [md, meta]
    else:
        paths = list(store.approved_dir().rglob("*"))
    paths = [p for p in paths if p.is_file()]
    try:
        print(store.git_add_commit_push(paths, args.message, push=not args.no_push))
    except Exception as e:  # noqa: BLE001
        print(f"失败：{e}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- publish（CI 用）

def _publish_one(cfg: dict, platform: str, src: Path, text: str, dry: bool) -> int:
    """发布单条内容。返回 0=成功/跳过，1=失败。"""
    text = text.strip()
    ok, limit = platforms.fits(platform, text)
    if not ok:
        print(f"[失败] 超过 {platform} 上限 {limit} 字符（当前 {len(text)}）：{src.name}", file=sys.stderr)
        return 1

    state = store.load_state()
    digest = store.sha256(f"{platform}:{src.name}:{text}")
    if store.already_posted(state, platform, digest):
        print(f"[跳过] {platform} 已发布过同样内容（幂等）：{src.name}")
        return 0

    allowed, why = platforms.next_allowed(state, platform, cfg)
    if not allowed:
        print(f"[跳过] 频率闸门：{why}（{src.name}）")
        return 0

    if dry:
        out_dir = store.repo_root() / "publish" / platform
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / f"{src.stem}.txt"
        store.write_text(dst, text + "\n")
        store.record_post(state, platform, digest, src.stem, detail="dry-run")
        store.save_state(state)
        print(f"[dry-run] 未发帖，已写入 {dst}")
        return 0

    success, detail = platforms.post(platform, text, os.environ)
    if not success:
        print(f"[失败] {platform}: {detail}（{src.name}）", file=sys.stderr)
        return 1
    store.record_post(state, platform, digest, src.stem, detail=detail)
    store.save_state(state)
    print(f"[已发布] {platform}: {detail}")
    return 0


def cmd_publish(args) -> int:
    cfg = cfg_mod.load()
    src = Path(args.file)
    if not src.exists():
        print(f"找不到草稿文件 {src}", file=sys.stderr)
        return 2
    dry = args.dry_run or cfg["social"].get("dry_run", True)
    if not dry and _outbound_blocked(cfg, "allow_social_posting", f"发布到 {args.platform}"):
        return 1
    rc = _publish_one(cfg, args.platform, src, store.read_text(src), dry)
    if rc == 0 and dry and not args.dry_run:
        print("          确认无误后，把 GitHub 变量 DRY_RUN 设为 false 即可真实发布。")
    return rc


def cmd_publish_batch(args) -> int:
    """按平台批量发布已批准内容，支持按版本/语言过滤（避免旧内容被重复推送）。"""
    cfg = cfg_mod.load()
    dry = args.dry_run or cfg["social"].get("dry_run", True)
    if not dry and _outbound_blocked(cfg, "allow_social_posting", f"批量发布到 {args.platform}"):
        return 1
    base = Path(args.dir)
    if not base.is_absolute():
        base = store.repo_root() / base
    if not base.exists():
        print(f"[跳过] 没有目录 {base}（还没有已批准的 {args.platform} 内容）")
        return 0

    files = sorted(base.rglob("*.md"))
    picked = []
    for md in files:
        meta_path = md.with_suffix(".json")
        meta = json.loads(store.read_text(meta_path)) if meta_path.exists() else {}
        if args.version and meta.get("version") and meta["version"] != args.version:
            continue
        if args.locale and meta.get("locale") and meta["locale"] != args.locale:
            continue
        if meta.get("platform") and meta["platform"] != args.platform:
            continue
        picked.append((md, meta))

    if not picked:
        print(f"[跳过] 没有匹配的 {args.platform} 内容（version={args.version} locale={args.locale}）")
        return 0

    print(f"[批量发布] {args.platform} 命中 {len(picked)} 条，dry_run={dry}")
    rc = 0
    for md, meta in picked:
        rc |= _publish_one(cfg, args.platform, md, store.read_text(md), dry)
    return rc


# ---------------------------------------------------------------- inbox（issue 回复闭环）

def cmd_inbox_pull(args) -> int:
    cfg = cfg_mod.load()
    repo = args.repo or cfg["project"].get("repo") or ""
    if not repo:
        print("请先用 --repo owner/name 指定仓库（或填进 config/promoter.json 的 project.repo）", file=sys.stderr)
        return 2
    from . import inbox
    try:
        inbox.pull(cfg, repo, limit=args.limit, label=args.label)
    except Exception as e:  # noqa: BLE001
        print(f"拉取失败：{e}", file=sys.stderr)
        return 1
    return 0


def cmd_inbox_push(args) -> int:
    cfg = cfg_mod.load()
    repo = args.repo or cfg["project"].get("repo") or ""
    if not repo:
        print("请先用 --repo owner/name 指定仓库", file=sys.stderr)
        return 2
    if args.send and _outbound_blocked(cfg, "allow_public_reply", "在 issue 下公开回复"):
        return 1
    from . import inbox
    try:
        return inbox.push(cfg, repo, slugs=args.slug or None, dry_run=not args.send)
    except Exception as e:  # noqa: BLE001
        print(f"回复失败：{e}", file=sys.stderr)
        return 1


def cmd_sitelinks(args) -> int:
    """生成 sitemap.xml / robots.txt / IndexNow key，并把 IndexNow key 写进仓库根目录。"""
    cfg = cfg_mod.load()
    root = store.repo_root()
    site = (cfg["project"].get("homepage") or "").rstrip("/")
    if not site:
        print("请先在 config/promoter.json 里填 project.homepage", file=sys.stderr)
        return 2

    key_file = root / "indexnow.key"
    key = store.read_text(key_file).strip() if key_file.exists() else store.sha256(site)[:32]
    if not key_file.exists():
        store.write_text(key_file, key + "\n")
    store.write_text(root / f"{key}.txt", key + "\n")

    pages = ["", "docs/", "changelog/"] + list(args.extra or [])
    today = store.now_iso()[:10]
    urls = "\n".join(
        f"  <url><loc>{site}/{p.lstrip('/')}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>weekly</changefreq></url>" for p in pages
    )
    sitemap = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'
    store.write_text(root / "sitemap.xml", sitemap)
    store.write_text(root / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n")

    if args.write:
        host = site.split("//")[-1].split("/")[0]
        payload = {"host": host, "key": key, "keyLocation": f"{site}/{key}.txt",
                   "urlList": [f"{site}/{p.lstrip('/')}" for p in pages]}
        store.write_text(root / "content" / "indexnow.json", __import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(f"[OK] 已生成 sitemap.xml / robots.txt / {key}.txt / content/indexnow.json")
    print(f"[OK] IndexNow host={site.split('//')[-1].split('/')[0]} key={key}")
    return 0


# ---------------------------------------------------------------- release

def cmd_release(args) -> int:
    """本地发布 GitHub Release（release.yml 的等价实现，只走 api.github.com）。"""
    from . import release as rel_mod
    return rel_mod.run_release(
        args.version,
        draft=getattr(args, "draft", False),
        skip_guard=getattr(args, "skip_guard", False),
        no_asset=getattr(args, "no_asset", False),
    )


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("promoter", description="本地生成宣传草稿，云端自动发布（人工审批，合法合规）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境自检").set_defaults(func=cmd_doctor)

    g = sub.add_parser("gen", help="生成本地草稿")
    g.add_argument("--kind", required=True, choices=list(store.KINDS))
    g.add_argument("--platform", help="social/announce 目标平台")
    g.add_argument("--locale", choices=["zh", "en", "ja"], help="文案语言")
    g.add_argument("--version", help="版本号，如 v0.2.0")
    g.add_argument("--summary", help="一句话总结（release/awesome）")
    g.add_argument("--highlight", action="append", help="变更点，可重复")
    g.add_argument("--list", dest="list", help="Awesome 列表名")
    g.add_argument("--issue", help="issue 编号")
    g.add_argument("--title", help="issue 标题")
    g.add_argument("--body", help="issue 正文")
    g.add_argument("--author", help="issue 作者")
    g.add_argument("--label", action="append", help="issue 标签，可重复")
    g.add_argument("--issue-kind", dest="issue_kind", choices=["bug", "feature", "question", "unknown"],
                   help="issue 类型，影响回复草稿的追问方式")
    g.set_defaults(func=cmd_gen)

    sub.add_parser("queue", help="列出待审批草稿").set_defaults(func=cmd_queue)

    r = sub.add_parser("review", help="交互式逐条审批")
    r.add_argument("--no-push", action="store_true", help="只入库不 push")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("approve", help="批准草稿入库")
    a.add_argument("slug", nargs="+")
    a.add_argument("--push", action="store_true", help="入库后直接 commit+push")
    a.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject", help="丢弃草稿")
    rj.add_argument("slug", nargs="+")
    rj.add_argument("--keep", action="store_true", help="保留草稿文件，只做标记")
    rj.set_defaults(func=cmd_reject)

    pu = sub.add_parser("push", help="提交并推送已批准内容")
    pu.add_argument("--draft", action="append", help="指定草稿 slug（默认推送所有已批准内容）")
    pu.add_argument("-m", "--message", default="content: publish approved drafts")
    pu.add_argument("--no-push", action="store_true", help="只 commit 不 push")
    pu.set_defaults(func=cmd_push)

    pb = sub.add_parser("publish", help="发布一条已批准内容到某平台（CI 调用）")
    pb.add_argument("--platform", required=True)
    pb.add_argument("-f", "--file", required=True)
    pb.add_argument("--dry-run", action="store_true")
    pb.set_defaults(func=cmd_publish)

    pbb = sub.add_parser("publish-batch", help="批量发布已批准内容（CI 调用，支持按版本过滤）")
    pbb.add_argument("--platform", required=True)
    pbb.add_argument("--dir", default="content/approved/social")
    pbb.add_argument("--version", help="只发这个版本的内容，如 v0.2.0")
    pbb.add_argument("--locale", choices=["zh", "en", "ja"])
    pbb.add_argument("--dry-run", action="store_true")
    pbb.set_defaults(func=cmd_publish_batch)

    ib = sub.add_parser("inbox", help="issue 回复闭环：拉取 -> 本地写草稿 -> 你审批 -> 回复")
    ib_sub = ib.add_subparsers(dest="action", required=True)
    ibp = ib_sub.add_parser("pull", help="拉取 issue 并生成回复草稿（本地模型）")
    ibp.add_argument("--repo", help="owner/name")
    ibp.add_argument("--limit", type=int, default=5)
    ibp.add_argument("--label", help="只拉取带该标签的 issue")
    ibp.set_defaults(func=cmd_inbox_pull)
    ibs = ib_sub.add_parser("push", help="发布已批准的回复（默认 dry-run）")
    ibs.add_argument("slug", nargs="*", help="只发指定草稿，如 reply/issue-42")
    ibs.add_argument("--repo", help="owner/name")
    ibs.add_argument("--send", action="store_true", help="真正发送（不加则只打印，不发出去）")
    ibs.set_defaults(func=cmd_inbox_push)

    s = sub.add_parser("sitelinks", help="生成 sitemap/robots/IndexNow key")
    s.add_argument("--write", action="store_true", help="同时写 IndexNow payload")
    s.add_argument("--extra", action="append", help="额外页面路径")
    s.set_defaults(func=cmd_sitelinks)

    rl = sub.add_parser("release", help="本地发布 GitHub Release（release.yml 的等价实现，走 API）")
    rl.add_argument("--version", required=True, help="版本号，如 v0.2.1（不带 v 会自动补）")
    rl.add_argument("--draft", action="store_true", help="建为草稿 Release")
    rl.add_argument("--skip-guard", action="store_true", help="跳过 CHANGELOG 守卫（不推荐）")
    rl.add_argument("--no-asset", action="store_true", help="不打包上传源码包")
    rl.set_defaults(func=cmd_release)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())