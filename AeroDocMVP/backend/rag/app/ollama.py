from __future__ import annotations

import json
from urllib.request import Request, urlopen

DEFAULT_SYSTEM = (
    "Ты помощник по технической документаци. Старайся отвечать по предоставленным данным. Делай ссылки на страницы"
)

def ollama_chat(
    prompt: str,
    *,
    model: str,
    base_url: str = "http://localhost:11434",
    timeout: int = 120,
    system: str = DEFAULT_SYSTEM,
    temperature: float = 0.1,
) -> str:
    """
    Ollama /api/chat, non-stream.
    """
    url = base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": temperature},
    }

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        resp = json.loads(body)
        return (resp.get("message") or {}).get("content") or ""
