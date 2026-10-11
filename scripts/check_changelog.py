#!/usr/bin/env python3
"""推 tag 前的 CHANGELOG 守卫。

作用：检查即将发布的版本在 CHANGELOG.md 里是否已经写了对应条目，
      避免"发了版本但用户看不到更新说明"。

用法：
    python scripts/check_changelog.py --version v0.2.0
    python scripts/check_changelog.py --version 0.2.0 --changelog CHANGELOG.md

退出码：
    0  = 已写条目（或跳过检查）
    1  = 缺少条目（会拦住发布）
    2  = 用法错误 / 文件缺失
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def norm(v: str) -> str:
    """去掉前导 v/V，便于 v0.2.0 与 0.2.0 互相匹配。"""
    return v.strip().lstrip("vV").strip()


def find_version_heading(text: str, version: str) -> tuple[bool, int | None]:
    """在 CHANGELOG 里找版本标题，返回 (是否找到, 行号)。"""
    v = norm(version)
    # 常见写法：[0.2.0] - 2026-10-11 / 0.2.0 / v0.2.0 / ## 0.2.0
    patterns = [
        re.compile(rf"^\s*#+\s*\[?v?{re.escape(v)}\]?", re.M),
        re.compile(rf"^\s*#+\s*\[?v?{re.escape(v)}\]?\s*[-–—(]", re.M),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            line = text[: m.start()].count("\n") + 1
            return True, line
    # 退化匹配：整行只有版本号
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip().strip("#").strip()
        if norm(s) == v:
            return True, i
    return False, None


def parse_changelog_versions(text: str) -> list[str]:
    """列出 CHANGELOG 里所有已记录的版本号。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("#"):
            continue
        s2 = s.lstrip("#").strip()
        m = re.match(r"^\[?v?(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)\]?", s2)
        if m:
            out.append(m.group(1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="推 tag 前检查 CHANGELOG 是否漏写")
    ap.add_argument("--version", required=True, help="即将发布的版本，如 v0.2.0")
    ap.add_argument("--changelog", default="CHANGELOG.md", help="CHANGELOG 文件路径")
    ap.add_argument("--allow-missing", action="store_true",
                    help="找不到 CHANGELOG 文件时也放行（默认放行，便于新仓库首次发布）")
    args = ap.parse_args(argv)

    cl = Path(args.changelog)
    if not cl.exists():
        if args.allow_missing:
            print(f"[skip] 未找到 {cl}，跳过检查")
            return 0
        print(f"[error] 未找到 {cl}", file=sys.stderr)
        return 2

    text = cl.read_text(encoding="utf-8", errors="replace")
    found, line = find_version_heading(text, args.version)

    if found:
        print(f"[ok] CHANGELOG 已包含 {args.version}（第 {line} 行）")
        return 0

    known = parse_changelog_versions(text)
    print(f"[fail] CHANGELOG 里没有 {args.version} 的条目。", file=sys.stderr)
    if known:
        print(f"       已记录的版本：{', '.join(known[:12])}", file=sys.stderr)
    print("       请在 CHANGELOG.md 顶部补一段，例如：", file=sys.stderr)
    print(f"         ## {args.version} - {__import__('datetime').date.today().isoformat()}", file=sys.stderr)
    print("         - 本次改动要点…", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
