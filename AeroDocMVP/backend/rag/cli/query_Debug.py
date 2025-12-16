from __future__ import annotations

import os
from pathlib import Path
import sys
import json
import time
from typing import Any, Dict, Optional, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from config.settings import Settings
from embed.embeddings import Embedder


# -----------------------------
# HTTP helpers
# -----------------------------
def http_json(method: str, url: str, payload: dict | None = None, timeout: int = 30):
    data = None
    headers = {"Content-Type": "application/json", "User-Agent": "rag-http-client"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, body


def wait_root_ok(base_url: str, timeout_s: int = 30):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            status, body = http_json("GET", base_url.rstrip("/") + "/", timeout=10)
            if 200 <= status < 300:
                return
            last = f"HTTP {status}: {body[:300]}"
        except Exception as e:
            last = repr(e)
        time.sleep(1)
    raise RuntimeError(f"Qdrant root not OK after {timeout_s}s. Last: {last}")


# -----------------------------
# Filters (new schema: file_name/doc_id/chunk_id in payload)
# -----------------------------
def build_filter(
    *,
    file_name: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> Optional[dict]:
    must = []

    if file_name:
        must.append({
            "key": "file_name",
            "match": {"value": file_name},
        })

    if doc_id:
        must.append({
            "key": "doc_id",
            "match": {"value": doc_id},
        })

    if not must:
        return None

    return {"must": [{"field": m} for m in must]}


# -----------------------------
# Pretty output
# -----------------------------
def _first(payload: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in payload and payload[k] not in (None, "", []):
            return payload[k]
    return default


def print_hit(i: int, p: Dict[str, Any], max_text: int = 1500):
    score = p.get("score")
    payload = p.get("payload") or {}
    text = payload.get("text") or ""

    file_name = _first(payload, "file_name", "source_file")
    chunk_index = _first(payload, "chunk_index")
    doc_id = _first(payload, "doc_id")
    chunk_id = _first(payload, "chunk_id")
    page_start = _first(payload, "page_start")
    page_end = _first(payload, "page_end")
    char_start = _first(payload, "char_start")
    char_end = _first(payload, "char_end")

    print("=" * 100)
    print(
        f"[{i}] score={score} | file={file_name} | chunk={chunk_index} | "
        f"pages={page_start}-{page_end} | chars={char_start}-{char_end}"
    )
    print(f"doc_id={doc_id}")
    print(f"chunk_id={chunk_id}")
    if text:
        print(text[:max_text])
    else:
        print("(no text in payload)")


# -----------------------------
# CLI parsing
# -----------------------------
def parse_args(argv: List[str]) -> Dict[str, Any]:
    """
    Usage:
      python query.py "ваш запрос"
      python query.py --file "RLE_An-2.pdf" "ваш запрос"
      python query.py --doc <doc_id> "ваш запрос"
      python query.py --limit 10 --score 0.2 "ваш запрос"
    """
    args = {
        "query": "",
        "file_name": None,
        "doc_id": None,
        "limit": 5,
        "score_threshold": None,
        "max_text": 1500,
    }

    it = iter(argv)
    query_parts: List[str] = []

    for token in it:
        if token in ("--file", "-f"):
            args["file_name"] = next(it, None)
        elif token in ("--doc", "-d"):
            args["doc_id"] = next(it, None)
        elif token in ("--limit", "-k"):
            v = next(it, None)
            args["limit"] = int(v) if v is not None else args["limit"]
        elif token in ("--score", "-s"):
            v = next(it, None)
            args["score_threshold"] = float(v) if v is not None else None
        elif token in ("--max-text", "-m"):
            v = next(it, None)
            args["max_text"] = int(v) if v is not None else args["max_text"]
        else:
            query_parts.append(token)

    args["query"] = " ".join(query_parts).strip()
    return args


# -----------------------------
# Main
# -----------------------------
def main():
    # proxy off (как у тебя)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    args = parse_args(sys.argv[1:])
    q = args["query"]
    if not q:
        print('Usage: python query.py [--file "name.pdf"] [--doc <doc_id>] [--limit 5] [--score 0.2] "your question"')
        return

    s = Settings()
    base = s.qdrant_url.rstrip("/")
    collection = s.collection

    wait_root_ok(base)

    # В новой схеме мы НЕ угадываем имя вектора — берём из Settings (должно быть "dense")
    vector_name = getattr(s, "vector_name", "dense")

    print("Qdrant:", base)
    print("Collection:", collection)
    print("Vector name:", vector_name)

    # Embed (ST-only embedder)
    embedder = Embedder(s.embedding_model)
    qvec = embedder.embed([q])[0]
    print("Query vector dim:", len(qvec))

    # Build filter (optional)
    flt = build_filter(file_name=args["file_name"], doc_id=args["doc_id"])

    # Query
    url = f"{base}/collections/{collection}/points/query"
    payload: Dict[str, Any] = {
        "query": qvec,
        "limit": int(args["limit"]),
        "with_payload": True,
        "with_vector": False,
        "using": vector_name,  # multi-vector name from Settings
    }
    if flt is not None:
        payload["filter"] = flt
    if args["score_threshold"] is not None:
        payload["score_threshold"] = float(args["score_threshold"])

    try:
        status, body = http_json("POST", url, payload=payload, timeout=30)
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"HTTPError: {e.code} {e.reason}")
        print(err_body[:4000])
        return
    except (URLError, Exception) as e:
        print("Request failed:", repr(e))
        return

    if not (200 <= status < 300):
        print("Bad status:", status)
        print(body[:4000])
        return

    data = json.loads(body)
    result = data.get("result") or {}
    points = result.get("points") or []

    print("Hits:", len(points))
    if not points:
        print("No results.")
        return

    for i, p in enumerate(points, start=1):
        if isinstance(p, dict):
            print_hit(i, p, max_text=int(args["max_text"]))
        else:
            print(f"[{i}] Unexpected point type: {type(p)} value={str(p)[:200]}")


if __name__ == "__main__":
    main()
