# rag_service.py
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Optional, Tuple, List
from functools import lru_cache
BASE_DIR = Path(__file__).resolve().parent          
RAG_DIR = BASE_DIR / "rag"                          
sys.path.insert(0, str(RAG_DIR))
from rag.config.settings import Settings
from rag.embed.embeddings import Embedder
from rag.utils.qdrant_store import QdrantStore
from rag.app.search import search_hybrid
from rag.app.ollama import ollama_chat
from rag.app.promt import build_prompt, format_sources
from rag.app.search import search_qdrant


def disable_proxies_for_localhost() -> None:
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"


@lru_cache(maxsize=1)
def _get_runtime():
    """
    Кэшируем тяжёлые штуки: Settings / QdrantStore / Embedder
    чтобы не создавать их на каждый запрос.
    """
    disable_proxies_for_localhost()
    s = Settings()
    store = QdrantStore(url=s.qdrant_url, collection=s.collection, vector_name=s.vector_name)
    embedder = Embedder(s.embedding_model, batch_size=32)
    return s, store, embedder


def answer_question(
    question: str,
    *,
    file_name: Optional[str] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> Tuple[str, List[str]]:
    s, store, embedder = _get_runtime()

    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3:8b")

    k = top_k if top_k is not None else int(os.getenv("TOP_K", "3"))

    hits = search_hybrid(
            store,
            embedder,
            question,
            fts_db_path=s.fts_db_path,
            limit=k,
            score_threshold=score_threshold,
        )

    if not hits:
        return "в предоставленных фрагментах нет информации", []

    prompt = build_prompt(question, hits, max_chars=12000)

    answer = ollama_chat(prompt, model=ollama_model, base_url=ollama_base).strip()

    sources_list = [line.strip() for line in format_sources(hits).splitlines() if line.strip()]
    return answer, sources_list

