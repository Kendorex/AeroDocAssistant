from __future__ import annotations

import os
import sys
import time
from urllib.error import URLError, HTTPError

from config.settings import Settings
from embed.embeddings import Embedder
from utils.qdrant_store import QdrantStore

from app.ollama import ollama_chat
from app.promt import build_prompt, format_sources
from app.search import search_qdrant
from app.search import search_hybrid

def parse_args(argv: list[str]):
    # python -m rag_app.cli.answer "вопрос"
    # python -m rag_app.cli.answer --file RLE_An-2.pdf "вопрос"
    if not argv:
        return None, None

    file_name = None
    if len(argv) >= 2 and argv[0] in ("--file", "-f"):
        file_name = argv[1]
        argv = argv[2:]

    question = " ".join(argv).strip()
    return file_name, question


def disable_proxies_for_localhost():
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"


def main():
    file_name, question = parse_args(sys.argv[1:])
    if not question:
        print('Usage: python -m rag_app.cli.answer [--file FILE_NAME] "your question"')
        return

    disable_proxies_for_localhost()

    s = Settings()

    # LLM settings (env override)
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3:8b")
    top_k = int(os.getenv("TOP_K", "3"))
    score_th = os.getenv("SCORE_THRESHOLD")
    score_threshold = float(score_th) if score_th else None

    print("Qdrant:", s.qdrant_url, "| collection:", s.collection, "| vector:", s.vector_name)
    print("LLM:", ollama_url, "| model:", ollama_model)
    if file_name:
        print("Filter file_name:", file_name)

    store = QdrantStore(url=s.qdrant_url, collection=s.collection, vector_name=s.vector_name)
    embedder = Embedder(s.embedding_model, batch_size=32)

    t0 = time.time()
    hits = search_hybrid(
        store,
        embedder,
        question,
        fts_db_path=s.fts_db_path,
        limit=top_k,
        score_threshold=score_threshold,
    )

    dt = time.time() - t0

    print(f"\nRetrieved: {len(hits)} hits in {dt:.2f}s")
    if not hits:
        print("\nОтвет: в предоставленных фрагментах нет информации.")
        return

    prompt = build_prompt(question, hits, max_chars=12000)

    try:
        answer = ollama_chat(prompt, model=ollama_model, base_url=ollama_url)
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"HTTPError: {e.code} {e.reason}")
        print(err_body[:4000])
        return
    except (URLError, Exception) as e:
        print("LLM request failed:", repr(e))
        return

    print("\n" + answer.strip())
    print("\nИсточники (retrieval):")
    print(format_sources(hits))


if __name__ == "__main__":
    main()
