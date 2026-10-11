"""对外平台适配：字符上限 + 通过官方 API 发帖（仅在 CI/用户显式执行时调用）。

每个平台都要求显式的环境变量（token），没配就当没开启，绝不静默尝试。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime

LIMITS: dict[str, int] = {
    "mastodon": 500,
    "bluesky": 300,
    "telegram": 4096,
    "discord": 2000,
    "generic": 0,      # 0 = 不限制
}

REQUIRED_ENV: dict[str, list[str]] = {
    "mastodon": ["MASTODON_BASE_URL", "MASTODON_TOKEN"],
    "bluesky": ["BSKY_HANDLE", "BSKY_APP_PASSWORD"],
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    "discord": ["DISCORD_WEBHOOK_URL"],
    "generic": [],
}


def _req(url: str, headers: dict, payload: dict | None = None, method: str = "POST") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    h = {"User-Agent": "zidon-promoter/0.1", **headers}
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {"raw": raw}


def post(platform: str, text: str, env: dict) -> tuple[bool, str]:
    """返回 (是否成功, 详情)。所有调用都走平台官方公开 API。"""
    missing = [k for k in REQUIRED_ENV.get(platform, []) if not env.get(k)]
    if missing:
        return False, f"缺少环境变量 {', '.join(missing)}，跳过"

    if platform == "mastodon":
        base = env["MASTODON_BASE_URL"].rstrip("/")
        body = _req(f"{base}/api/v1/statuses", {"Authorization": f"Bearer {env['MASTODON_TOKEN']}"}, {"status": text})
        return True, body.get("url", "ok")

    if platform == "bluesky":
        pds = env.get("BSKY_PDS", "https://bsky.social").rstrip("/")
        session = _req(
            f"{pds}/xrpc/com.atproto.server.createSession",
            {},
            {"identifier": env["BSKY_HANDLE"], "password": env["BSKY_APP_PASSWORD"]},
        )
        jwt, did = session.get("accessJwt"), session.get("did")
        if not jwt or not did:
            return False, f"登录失败: {session}"
        rec = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        out = _req(
            f"{pds}/xrpc/com.atproto.repo.createRecord",
            {"Authorization": f"Bearer {jwt}"},
            {"repo": did, "collection": "app.bsky.feed.post", "record": rec},
        )
        return True, out.get("uri", "ok")

    if platform == "telegram":
        token = env["TELEGRAM_BOT_TOKEN"]
        q = urllib.parse.urlencode({"chat_id": env["TELEGRAM_CHAT_ID"], "text": text,
                                    "disable_web_page_preview": "false"})
        out = _req(f"https://api.telegram.org/bot{token}/sendMessage?{q}", {}, None, method="POST")
        return bool(out.get("ok")), str(out.get("description") or out.get("result", {}).get("message_id", "ok"))

    if platform == "discord":
        out = _req(env["DISCORD_WEBHOOK_URL"], {}, {"content": text})
        return True, str(out.get("id", "ok"))

    return False, f"平台 {platform} 没有自动发布实现，只保留草稿"


def fits(platform: str, text: str) -> tuple[bool, int]:
    limit = LIMITS.get(platform, 0)
    n = len(text)
    return (limit == 0 or n <= limit), limit


def next_allowed(state: dict, platform: str, cfg: dict, now: datetime | None = None) -> tuple[bool, str]:
    """频率闸门：最小间隔 + 每日上限，防止机器刷屏。"""
    now = now or datetime.now(timezone.utc)
    social = cfg.get("social", {})
    min_gap = int(social.get("min_interval_minutes", 60) or 0)
    max_day = int(social.get("max_posts_per_day", 3) or 0)
    posts = [p for p in state.get("posted", []) if p.get("platform") == platform]
    stamps = []
    for p in posts:
        raw = p.get("at") or ""
        try:
            # 兼容 2026-10-11T10:00:00+0800 / +08:00 两种写法
            s = raw.replace("Z", "+00:00")
            if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
                s = s[:-2] + ":" + s[-2:]
            dt = datetime.fromisoformat(s)
            stamps.append(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
        except Exception:
            continue
    stamps.sort()
    if min_gap and stamps:
        gap = (now - stamps[-1]).total_seconds() / 60
        if gap < min_gap:
            return False, f"距上次发帖 {gap:.0f} 分钟 < 最小间隔 {min_gap} 分钟"
    if max_day:
        today = [s for s in stamps if s.date() == now.date()]
        if len(today) >= max_day:
            return False, f"今日已发 {len(today)} 条 ≥ 上限 {max_day}"
    return True, "ok"


def rfc2822(dt: datetime) -> str:
    return format_datetime(dt)