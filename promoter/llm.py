"""Ollama 本地调用（纯标准库）。只生成文字，绝不接触任何账号。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


def _post(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ping(cfg: dict) -> tuple[bool, str]:
    host = cfg["llm"]["host"].rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name", "") for m in body.get("models", [])]
        return True, ", ".join(names) or "（没有任何模型，请先 ollama pull）"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def chat(messages: list[dict], cfg: dict) -> str:
    """调用 /api/chat，非流式。失败抛 LLMError，由 cli 决定是否回退模板。"""
    llm = cfg["llm"]
    host = llm["host"].rstrip("/")
    payload = {
        "model": llm["model"],
        "messages": messages,
        "stream": False,
        "keep_alive": llm.get("keep_alive", "5m"),
        "options": {
            "temperature": llm.get("temperature", 0.6),
            "num_predict": llm.get("num_predict", 512),
            "num_ctx": llm.get("num_ctx", 2048),  # 小模型 + 低配机，上下文开小一点
        },
    }
    try:
        body = _post(f"{host}/api/chat", payload, int(llm.get("timeout", 180)))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"Ollama HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"连不上 Ollama（{host}）：{e}") from e

    text = (body.get("message") or {}).get("content", "")
    text = strip_wrapper(text)
    if not text.strip():
        raise LLMError("模型返回空内容")
    return text.strip()


def strip_wrapper(text: str) -> str:
    """小模型爱把答案塞进 ``` 代码块，剥掉。"""
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    for tag in ("<|im_end|>", "<|endoftext|>", "</s>"):
        t = t.replace(tag, "")
    return t.strip()