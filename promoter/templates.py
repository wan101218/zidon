"""无模型兜底模板：Ollama 没装/没跑时，也能产出结构化、可直接改的草稿。"""

from __future__ import annotations


def _bullets(items, prefix="- ") -> str:
    if not items:
        return f"{prefix}（在这里补一条变更）"
    return "\n".join(f"{prefix}{x}" for x in items)


def release(ctx: dict) -> str:
    name = ctx.get("project", "项目")
    ver = ctx.get("version", "v0.0.0")
    url = ctx.get("url", "")
    install = ctx.get("install", "")
    body = [
        f"## 这次更新（{ver}）",
        ctx.get("summary") or f"{name} 发布 {ver}。请在这里用 2-3 句话说明改了什么、对谁有用。",
        "",
        "## 变更",
        _bullets(ctx.get("highlights") or []),
        "",
        "## 升级方式",
        "```\n" + (install or "# 在这里写升级命令") + "\n```",
    ]
    if url:
        body += ["", f"仓库：{url}"]
    return "\n".join(body)


def social(ctx: dict) -> str:
    name = ctx.get("project", "项目")
    locale = ctx.get("locale", "zh")
    url = ctx.get("url", "")
    one = ctx.get("one_liner", "")
    highlights = ctx.get("highlights") or []
    tagline = "；".join(highlights[:3]) if highlights else ""
    if locale == "en":
        lines = [f"{name}: {one or 'one line about what it solves'}", tagline]
        if ctx.get("install"):
            lines.append(f"Install: {ctx['install']}")
    else:
        lines = [f"{name}：{one or '一句话说明它解决什么问题'}", tagline]
        if ctx.get("install"):
            lines.append(f"安装：{ctx['install']}")
    if url:
        lines.append(url)
    return "\n".join(x for x in lines if x)


def awesome(ctx: dict) -> str:
    name = ctx.get("project", "项目")
    url = ctx.get("url", "")
    one = ctx.get("one_liner", "")
    lst = ctx.get("list_name", "awesome-xxx")
    body = [
        "## 条目（一行）",
        "",
        f"- [{name}]({url}) - {one}",
        "",
        "## PR 描述",
        "",
        f"把 {name} 加入 {lst}。",
        "",
        "### 为什么符合收录标准",
        _bullets([
            "开源且许可证清晰",
            "有可运行的安装方式与文档",
            "接口/用法稳定，仍在维护",
        ], prefix="- "),
        "",
        "### 自查",
        "- [ ] 已通读该列表的 contributing 指南",
        "- [ ] 条目已插入到正确分类，且保持字母序",
        "- [ ] 未重复提交、非纯广告",
    ]
    return "\n".join(body)


def reply(ctx: dict) -> str:
    issue = ctx.get("issue_number", "?")
    title = ctx.get("issue_title", "")
    kind = (ctx.get("issue_kind") or "unknown").strip()
    if kind == "bug":
        lines = [
            f"感谢反馈 #{issue}（{title}）。",
            "",
            "为了定位这个问题，能否补充以下信息：",
            "1. 版本 / commit：",
            "2. 系统与运行环境：",
            "3. 最小复现步骤：",
            "4. 完整报错日志（脱敏后）：",
            "",
            "拿到这些信息后我再看，有结论会在这里同步。",
        ]
    elif kind == "feature":
        lines = [
            f"感谢建议 #{issue}（{title}）。",
            "",
            "想先确认一下使用场景：你期望解决的具体问题是什么？现在通常怎么绕过它？",
            "如果描述清楚，我会评估是否放进路线图，并在本 issue 同步结论。",
        ]
    else:
        lines = [
            f"感谢反馈 #{issue}（{title}）。",
            "",
            "我先按下面的信息来判断，麻烦补充：使用版本、运行环境、复现步骤。",
        ]
    return "\n".join(lines)