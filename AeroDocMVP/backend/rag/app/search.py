from __future__ import annotations

from typing import Any, Dict, List, Optional

from embed.embeddings import Embedder
from utils.qdrant_store import QdrantStore
from utils.sqlite_fts import connect_db, init_fts, bm25_search


def search_qdrant(
    store: QdrantStore,
    embedder: Embedder,
    question: str,
    *,
    limit: int = 5,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    qvec = embedder.embed([question])[0]
    hits = store.search(
        query_vector=qvec,
        limit=limit,
        query_filter=None,
        score_threshold=score_threshold,
    )

    out: List[Dict[str, Any]] = []
    for h in hits:
        out.append(
            {
                "id": getattr(h, "id", None),
                "score": getattr(h, "score", None),
                "payload": getattr(h, "payload", None),
            }
        )
    return out


def rrf_fuse(
    dense_hits: List[Dict[str, Any]],
    bm25_hits: List[Dict[str, Any]],
    *,
    limit: int = 5,
    k: int = 60,
) -> List[Dict[str, Any]]:
    scores: Dict[Any, float] = {}
    payloads: Dict[Any, Dict[str, Any]] = {}

    def add_hits(hits: List[Dict[str, Any]]):
        for rank, h in enumerate(hits, start=1):
            hid = h.get("id")
            if hid is None:
                continue
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (k + rank)

            p = h.get("payload") or {}
            if hid not in payloads or len(str(payloads[hid])) < len(str(p)):
                payloads[hid] = p

    add_hits(dense_hits)
    add_hits(bm25_hits)

    fused_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"id": hid, "score": fused_score, "payload": payloads.get(hid)} for hid, fused_score in fused_ids]


def search_hybrid(
    store: QdrantStore,
    embedder: Embedder,
    question: str,
    *,
    fts_db_path: str,
    limit: int = 5,
    prefetch_dense: int = 30,
    prefetch_bm25: int = 30,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    dense_hits = search_qdrant(
        store,
        embedder,
        question,
        limit=prefetch_dense,
        score_threshold=score_threshold,
    )

    conn = connect_db(fts_db_path)
    init_fts(conn)
    try:
        bm25_hits = bm25_search(conn, question, limit=prefetch_bm25)
    finally:
        conn.close()

    return rrf_fuse(dense_hits, bm25_hits, limit=limit)
