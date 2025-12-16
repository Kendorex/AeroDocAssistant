# qdrant_store.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


PointDict = Dict[str, Any]


class QdrantStore:
    """
    Цельный store-слой с:
    - multi-vector (vector_name)
    - нормализацией payload (метаданные + text)
    - удобными фильтрами
    - батчевым upsert
    """

    def __init__(
        self,
        url: str,
        collection: str,
        vector_name: str = "dense",
        *,
        timeout: Optional[float] = None,
    ):
        # check_compatibility=False -> меньше сюрпризов по версиям клиента/сервера
        self.client = QdrantClient(url=url, timeout=timeout, check_compatibility=False)
        self.collection = collection
        self.vector_name = vector_name

    # ---------------------------
    # Collection management
    # ---------------------------

    def ensure_collection(self, vector_size: int) -> None:
        cols = self.client.get_collections().collections
        if any(c.name == self.collection for c in cols):
            return

        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                self.vector_name: qm.VectorParams(
                    size=vector_size,
                    distance=qm.Distance.COSINE,
                )
            },
        )

    def recreate_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config={
                self.vector_name: qm.VectorParams(
                    size=vector_size,
                    distance=qm.Distance.COSINE,
                )
            },
        )

    # ---------------------------
    # Payload contract helpers
    # ---------------------------

    def _normalize_payload(
        self,
        *,
        point_id: Union[str, int],
        payload: Optional[Dict[str, Any]],
        text: Optional[str],
        meta: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Единый контракт payload:
        - payload["text"] хранит чанк (для удобства retrieval/ответов)
        - payload содержит meta-поля (doc_id, file_name, chunk_index, ...)
        - payload["chunk_id"] по умолчанию равен id точки
        """
        out: Dict[str, Any] = {}
        if payload:
            out.update(payload)
        if meta:
            out.update(meta)

        # гарантируем наличие текста в payload
        if "text" not in out and text is not None:
            out["text"] = text

        # базовые системные поля
        out.setdefault("chunk_id", str(point_id))
        out.setdefault("vector_name", self.vector_name)

        return out

    def _normalize_point(self, p: PointDict) -> PointDict:
        """
        Принимаем несколько возможных форматов входных points:
        1) {"id":..., "vector":..., "payload": {...}}
        2) {"id":..., "vector":..., "text": "...", "meta": {...}}
        3) {"id":..., "vector":..., "payload": {...}, "text": "...", "meta": {...}}  (смешанный)
        """
        if "id" not in p or "vector" not in p:
            raise ValueError("Each point must contain keys: 'id' and 'vector'")

        pid = p["id"]
        vec = p["vector"]
        if not isinstance(vec, (list, tuple)) or len(vec) == 0:
            raise ValueError("Point 'vector' must be a non-empty list/tuple")

        payload = p.get("payload")
        text = p.get("text")
        meta = p.get("meta")

        norm_payload = self._normalize_payload(
            point_id=pid,
            payload=payload if isinstance(payload, dict) else None,
            text=text if isinstance(text, str) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

        return {"id": pid, "vector": list(vec), "payload": norm_payload}

    # ---------------------------
    # Upsert
    # ---------------------------

    def upsert(
        self,
        points: Sequence[PointDict],
        *,
        batch_size: int = 128,
    ) -> None:
        """
        Upsert батчами.
        points: список словарей с хотя бы {"id":..., "vector":...}
        """
        if not points:
            return

        # нормализуем все точки
        norm_points = [self._normalize_point(p) for p in points]

        for i in range(0, len(norm_points), batch_size):
            batch = norm_points[i : i + batch_size]
            self.client.upsert(
                collection_name=self.collection,
                points=[
                    qm.PointStruct(
                        id=p["id"],
                        vector={self.vector_name: p["vector"]},
                        payload=p["payload"],
                    )
                    for p in batch
                ],
            )

    # ---------------------------
    # Search / Filters
    # ---------------------------

    @staticmethod
    def filter_match_value(key: str, value: Any) -> qm.Filter:
        return qm.Filter(
            must=[qm.FieldCondition(key=key, match=qm.MatchValue(value=value))]
        )

    @staticmethod
    def filter_match_any(key: str, values: List[Any]) -> qm.Filter:
        return qm.Filter(
            must=[qm.FieldCondition(key=key, match=qm.MatchAny(any=values))]
        )

    @staticmethod
    def filter_doc_id(doc_id: str) -> qm.Filter:
        return QdrantStore.filter_match_value("doc_id", doc_id)

    def search(
        self,
        query_vector: List[float],
        *,
        limit: int = 5,
        query_filter: Optional[qm.Filter] = None,
        score_threshold: Optional[float] = None,
    ) -> List[qm.ScoredPoint]:
        """
        Возвращает список ScoredPoint (payload внутри).
        score_threshold: если задан — отсекаем слабые совпадения.
        """
        res = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            using=self.vector_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
        return list(res.points)

    # ---------------------------
    # Delete helpers (optional but useful)
    # ---------------------------

    def delete_by_filter(self, flt: qm.Filter) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(filter=flt),
        )

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.delete_by_filter(self.filter_doc_id(doc_id))
