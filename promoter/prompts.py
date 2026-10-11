"""提示词构造。给 0.6B 小模型的提示词要短、要具体、要禁止编造。"""

from __future__ import annotations

SYSTEM = (
    "你是一个开源项目的宣传助手。你只为下面这个项目写文案。\n"
    "硬性规则：\n"
    "1) 只使用我给你的事实，绝不编造功能、用户数、性能数字或他人评价。\n"
    "2) 不夸大（禁止“最强/第一/颠覆”），不承诺未实现的功能。\n"
    "3) 语气平实、像开发者之间的分享，不说废话，不加 Emoji 堆砌。\n"
    "4) 直接输出正文，不要解释你在做什么，不要用 Markdown 代码块包裹。\n"
)

LIMITS = {
    "mastodon": 500,
    "bluesky": 300,
    "telegram": 4096,
    "discord": 2000,
    "generic": 700,
    "release": 4000,
    "awesome": 1200,
    "reply": 1200,
}


def _facts(ctx: dict) -> str:
    lines = []
    for k, v in ctx.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (list, tuple)):
            v = "；".join(str(x) for x in v)
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def build(kind: str, ctx: dict) -> list[dict]:
    """返回 Ollama /api/chat 的 messages。"""
    limit = LIMITS.get(kind, 700)
    if kind == "release":
        task = (
            "写一份 GitHub Release Notes，Markdown 格式。结构：\n"
            "## 这次更新\n（2-3 句说明改了什么、对谁有用）\n"
            "## 变更\n（用 - 列表，逐条来自我给的变更点，不要新增）\n"
            "## 升级方式\n（一句话，用我给的安装/升级命令）\n"
            f"全文控制在 {limit} 字符以内。"
        )
    elif kind == "social":
        task = (
            f"写一条{ctx.get('locale_label', '中文')}社交媒体动态，用于在 {ctx.get('platform')} 宣传这个项目。\n"
            "结构：第 1 行说明它解决什么问题；第 2-3 行核心卖点（最多 3 条）；最后一行给出链接。\n"
            "不要话题标签轰炸，最多 3 个标签。\n"
            f"全文必须少于 {limit} 字符。"
        )
    elif kind == "awesome":
        task = (
            "为一个“Awesome 列表”仓库写一条 Pull Request 的说明与条目。\n"
            "第一部分：一行 Markdown 列表项（格式：- [名称](链接) - 一句话介绍）。\n"
            "第二部分：PR 描述，说明这个项目是什么、为什么符合该列表的收录标准、以及自查清单。\n"
            f"全文 {limit} 字符以内。"
        )
    elif kind == "reply":
        task = (
            "为一个 GitHub issue 写一条回复草稿。\n"
            "要求：先确认对方的场景；如果对方报了 bug，给出 1-3 条可执行的排查步骤"
            "（询问版本/系统/复现步骤/报错日志）；不要承诺具体修复时间；"
            "不确定的地方明确说“需要更多信息”。结尾用一句礼貌的收尾。\n"
            "如果信息不足以判断，就只写一段追问，不要硬猜。\n"
            f"全文 {limit} 字符以内，直接输出回复正文。"
        )
    else:
        task = f"写一段{ctx.get('locale_label', '中文')}的项目介绍，{limit} 字符以内。"

    user = f"{task}\n\n项目事实（只能用这些）：\n{_facts(ctx)}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]