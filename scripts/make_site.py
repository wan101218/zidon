"""生成静态落地页 + sitemap/robots + IndexNow 载荷。

为什么要有落地页：搜索引擎和社交平台的链接最终都要落到一个能打开的页面上，
README 里的安装命令就是转化点。没有 site/ 时用 README.md 自动生成，省事且够用。

用法（本地可跑）：
    python scripts/make_site.py                    # 输出到 _site/
    python scripts/make_site.py --out _site --root .
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DEFAULT))

from promoter import config as cfg_mod  # noqa: E402
from promoter import store  # noqa: E402

CSS = """*{box-sizing:border-box}
body{margin:0;font:16px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#1f2328;background:#fff}
.wrap{max-width:840px;margin:0 auto;padding:48px 20px 80px}
header{border-bottom:1px solid #d8dee4;padding-bottom:24px;margin-bottom:32px}
h1{font-size:2rem;margin:0 0 8px}
.tagline{color:#59636e;margin:0 0 20px}
.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.install{background:#f6f8fa;border:1px solid #d8dee4;border-radius:6px;padding:8px 12px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14px}
a.btn{display:inline-block;padding:8px 14px;border-radius:6px;background:#1f883d;color:#fff;text-decoration:none;font-weight:600}
a.btn.alt{background:#f6f8fa;color:#1f2328;border:1px solid #d8dee4}
article h2{font-size:1.35rem;margin-top:36px;border-bottom:1px solid #d8dee4;padding-bottom:6px}
article h3{font-size:1.1rem;margin-top:28px}
pre{background:#f6f8fa;padding:14px;border-radius:6px;overflow:auto}
code{background:#f6f8fa;padding:.15em .35em;border-radius:4px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #d8dee4;padding:6px 10px;text-align:left}
footer{margin-top:56px;color:#59636e;font-size:14px;border-top:1px solid #d8dee4;padding-top:16px}
@media (prefers-color-scheme:dark){body{background:#0d1117;color:#e6edf3}header,article h2,footer{border-color:#30363d}.tagline,footer{color:#9198a1}pre,code,.install{background:#161b22;border-color:#30363d}a.btn.alt{background:#21262d;color:#e6edf3;border-color:#30363d}th,td{border-color:#30363d}}
"""


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def md_to_html(md: str) -> str:
    """极简 Markdown 子集渲染：标题/列表/围栏代码/行内代码/粗体/链接/表格分隔行。"""
    out: list[str] = []
    in_code = False
    in_ul = in_ol = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            out.append(esc(line))
            continue
        if not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_ol:
                out.append("</ol>")
                in_ol = False
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_ol:
                out.append("</ol>")
                in_ol = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(re.sub(r'^\s*[-*]\s+', '', line))}</li>")
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(re.sub(r'^\s*\d+\.\s+', '', line))}</li>")
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if line.strip().startswith("|") and set(line.strip()) <= set("|-: "):
            continue  # 表格分隔行，跳过
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        out.append(f"<p>{inline(line)}</p>")
    if in_code:
        out.append("</code></pre>")
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)


def inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"(?<![\"'>=])(https?://[^\s<)]+)", r'<a href="\1">\1</a>', s)
    return s


def index_page(cfg: dict, body_html: str) -> str:
    proj = cfg["project"]
    name = proj.get("name") or "项目"
    one = proj.get("one_liner") or ""
    repo = proj.get("repo") or ""
    install = proj.get("install") or ""
    homepage = (proj.get("homepage") or "").rstrip("/")
    actions = []
    if repo:
        actions.append(f'<a class="btn" href="https://github.com/{esc(repo)}">在 GitHub 上查看</a>')
        actions.append(f'<a class="btn alt" href="https://github.com/{esc(repo)}/releases">Release 记录</a>')
    if install:
        actions.append(f'<span class="install">{esc(install)}</span>')
    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)} — {esc(one)}</title>
<meta name="description" content="{esc(one)}">
<meta property="og:title" content="{esc(name)}">
<meta property="og:description" content="{esc(one)}">
<meta property="og:type" content="website">
<link rel="canonical" href="{esc(homepage)}/">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(name)}</h1>
  {f'<p class="tagline">{esc(one)}</p>' if one else ''}
  <div class="actions">{''.join(actions)}</div>
</header>
<article>{body_html}</article>
<footer>本页由 zidon 自动生成 · <a href="{esc(homepage)}/sitemap.xml">sitemap</a></footer>
</div>
</body>
</html>
"""


def guess_site(root: Path) -> str:
    """没填 homepage 时，从 git remote 推断 GitHub Pages 默认地址。"""
    import subprocess
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        url = (r.stdout or "").strip()
    except Exception:
        return ""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$", url)
    if not m:
        return ""
    owner, name = m.group(1), m.group(2)
    return f"https://{owner}.github.io/{name}"


def build(root: Path, out: Path, cfg: dict) -> str:
    out.mkdir(parents=True, exist_ok=True)
    site_src = root / "site"
    if site_src.is_dir() and any(site_src.iterdir()):
        shutil.copytree(site_src, out, dirs_exist_ok=True)
        print(f"使用现有 site/（{len(list(site_src.rglob('*')))} 个文件）")
    else:
        readme = root / "README.md"
        md = readme.read_text(encoding="utf-8") if readme.exists() else "# 项目\n\n还没有 README。\n"
        (out / "index.html").write_text(index_page(cfg, md_to_html(md)), encoding="utf-8")
        print("没有 site/，已用 README.md 生成 index.html")

    site = (cfg["project"].get("homepage") or "").rstrip("/")
    if not site:
        site = guess_site(root) or ""
        if site:
            print(f"project.homepage 为空，按 git remote 推断：{site}")
        else:
            print("::warning::无法确定站点地址（config/promoter.json 的 project.homepage 为空），sitemap 链接会是占位值")
            site = "https://example.invalid"

    key = store.sha256(site)[:32]
    (root / "indexnow.key").write_text(key + "\n", encoding="utf-8")
    (out / f"{key}.txt").write_text(key + "\n", encoding="utf-8")

    pages = sorted({p.relative_to(out).as_posix() for p in out.rglob("*.html")} | {"docs/", "changelog/"})
    # index.html 就是站点根，别再列一份
    pages = ["" if p == "index.html" else p for p in pages]
    today = store.now_iso()[:10]
    urls = "\n".join(
        f"  <url><loc>{site}/{p}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>"
        for p in pages
    )
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>\n",
        encoding="utf-8",
    )
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n", encoding="utf-8"
    )

    payload = {
        "host": site.split("//")[-1].split("/")[0],
        "key": key,
        "keyLocation": f"{site}/{key}.txt",
        "urlList": [f"{site}/{p}" for p in pages],
    }
    (root / "indexnow.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"站点根：{site}  IndexNow key：{key}  页面数：{len(pages)}")
    return site


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cfg = cfg_mod.load(root / "config" / "promoter.json")
    build(root, (root / args.out) if not Path(args.out).is_absolute() else Path(args.out), cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())