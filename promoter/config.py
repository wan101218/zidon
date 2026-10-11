"""配置：config/promoter.json（缺省值内置于此，文件可只写要覆盖的部分）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .store import read_text, repo_root, write_text

DEFAULTS: dict = {
    "project": {
        "name": "zidon",
        "repo": "",                 # 例：yourname/zidon
        "one_liner": "一句话说清楚这个项目解决什么问题",
        "homepage": "",             # 例：https://yourname.github.io/zidon/
        "install": "",              # 例：pip install zidon
        "keywords": [],
        "license": "MIT",
    },
    "llm": {
        "engine": "ollama",         # ollama | template
        "fallback_to_template": True,
        "model": "qwen3:0.6b",
        "host": "http://127.0.0.1:11434",
        "timeout": 180,
        "num_predict": 512,
        "temperature": 0.6,
        "keep_alive": "5m",
    },
    "social": {
        "dry_run": True,            # 安全模式：true 时云端只写文件，不发帖
        # 默认不启用任何外部社交平台 —— 本项目仅用于自己的 Release Notes 与文档站点。
        # 如需启用，请显式填写平台名，并自行配置对应 token 环境变量。
        "enabled_platforms": [],
        "locales": ["zh"],
        "min_interval_minutes": 60,     # 同一平台两次发帖的最小间隔
        "max_posts_per_day": 3,         # 每平台每日上限（反刷屏）
        "append_url": True,
    },
    "compliance": {
        "human_approval_required": True,
        "allow_auto_follow": False,
        "allow_auto_dm": False,
        "allow_scraping": False,
        "allow_mass_comment": False,
        "allow_social_posting": False,
        "allow_public_reply": False,
        "allow_awesome_pr": False,
        "note": "仅宣传自己的项目内容；不自动关注/私信/群发评论；遵守各平台 ToS 与频率限制；不伪造数据与用户评价。",
    },
}


def config_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "config" / "promoter.json"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict:
    cfg = DEFAULTS
    p = path or config_path()
    if Path(p).exists():
        cfg = _merge(DEFAULTS, json.loads(read_text(Path(p))))
    # 环境变量覆盖，方便 CI / 临时调试
    engine = os.environ.get("PROMOTER_LLM_ENGINE")
    if engine:
        cfg["llm"]["engine"] = engine
    if os.environ.get("PROMOTER_DRY_RUN", "").lower() in ("1", "true", "yes"):
        cfg["social"]["dry_run"] = True
    return cfg


def save(cfg: dict, path: Path | None = None) -> Path:
    p = path or config_path()
    return write_text(Path(p), json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


def project_url(cfg: dict) -> str:
    proj = cfg.get("project", {})
    repo = (proj.get("repo") or "").strip()
    return f"https://github.com/{repo}" if repo else (proj.get("homepage") or "").strip()