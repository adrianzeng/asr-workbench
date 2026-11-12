"""Draft-rewrite extension point (reserved, deliberately not implemented).

ASR Workbench stays fully local in this version. This module defines the
contract for an optional OpenAI-compatible "polish the transcript" step so
that the UI, config and documentation have a stable place to grow into.
It makes **no network requests** and never changes the transcript.

Future implementation sketch (standard library only, no SDK needed)::

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]

Privacy contract (must hold when this is implemented):
  * Only the transcript TEXT may be sent. Audio never leaves the machine.
  * The UI must state clearly which service receives the text.
  * The feature stays off unless the user explicitly enables it.
"""

from __future__ import annotations

OFF = "off"
OPENAI_COMPAT = "openai"
NOT_IMPLEMENTED = "not_implemented"

SYSTEM_PROMPT = (
    "你是文稿整理助手。把下面这份语音转写草稿整理成通顺、分段合理、带标点的中文文稿；"
    "只顺句子、去口水词、补标点、改明显错别字，不要新增内容，不要改写原意。"
    "只输出整理后的文稿。"
)


def rewrite_status(cfg: dict) -> dict:
    """Report the reserved engine's state. Pure introspection, no I/O."""
    engine = str(cfg.get("rewrite_engine", OFF)).strip().lower()
    if engine not in (OFF, OPENAI_COMPAT):
        engine = OFF
    configured = bool(cfg.get("rewrite_base_url")) and bool(cfg.get("rewrite_model"))
    return {
        "engine": engine,
        "configured": configured,
        "enabled": False,   # hard-wired off in this version
        "network": False,   # this version never sends anything
        "status": OFF if engine == OFF else NOT_IMPLEMENTED,
        "note": "接口预留：本版本不发起任何网络请求，文稿不会离开本机。",
    }


def rewrite_draft(text: str, cfg: dict) -> dict:
    """Reserved entry point.

    Returns the original text untouched plus an explicit status, so callers
    can render an honest message instead of pretending a rewrite happened.
    """
    state = rewrite_status(cfg)
    return {
        "text": text,
        "changed": False,
        "status": state["status"],
        "engine": state["engine"],
        "note": state["note"],
    }
