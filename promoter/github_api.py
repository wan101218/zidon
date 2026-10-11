"""极简 GitHub REST 客户端（纯标准库）。只做「读 issue / 发评论」这类必要动作。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class ApiError(RuntimeError):
    pass


def token() -> str:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def api(method: str, path: str, data: dict | None = None, params: dict | None = None,
        tk: str | None = None) -> object:
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zidon-promoter/0.1",
    }
    t = tk if tk is not None else token()
    if t:
        headers["Authorization"] = f"Bearer {t}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code == 401:
            raise ApiError("GitHub 认证失败（401）：本地请设置 GH_TOKEN 环境变量，classic/fine-grained 均需 repo 权限") from e
        if e.code == 403:
            raise ApiError(f"GitHub 拒绝（403，多为核心限流或权限不足）：{detail}") from e
        raise ApiError(f"GitHub HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise ApiError(f"请求 GitHub 失败：{e}") from e
    return json.loads(raw) if raw else {}


def list_issues(repo: str, limit: int = 5, label: str | None = None, tk: str | None = None) -> list[dict]:
    """列出待处理 issue（自动排除 PR）。"""
    params = {"state": "open", "per_page": str(max(1, min(limit * 3, 100))),
              "sort": "created", "direction": "desc"}
    if label:
        params["labels"] = label
    items = api("GET", f"/repos/{repo}/issues", params=params, tk=tk)
    out = [i for i in items if "pull_request" not in i]  # type: ignore[union-attr]
    return out[:limit]


def issue_comments(repo: str, number: int, tk: str | None = None) -> list[dict]:
    items = api("GET", f"/repos/{repo}/issues/{number}/comments", params={"per_page": "20"}, tk=tk)
    return items  # type: ignore[return-value]


def comment_issue(repo: str, number: int, body: str, tk: str | None = None) -> dict:
    return api("POST", f"/repos/{repo}/issues/{number}/comments", data={"body": body}, tk=tk)  # type: ignore[return-value]


def add_labels(repo: str, number: int, labels: list[str], tk: str | None = None) -> dict:
    return api("POST", f"/repos/{repo}/issues/{number}/labels", data={"labels": labels}, tk=tk)  # type: ignore[return-value]