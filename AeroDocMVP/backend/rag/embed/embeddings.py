from __future__ import annotations
from typing import List, Optional


class Embedder:

    def __init__(self, model_name: str, *, batch_size: int = 32):
        self.model_name = model_name
        self.batch_size = batch_size

        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)
        self._dim_cache: Optional[int] = None

    def embed(self, texts: List[str]) -> List[list]:
        if not texts:
            return []
        
        safe_texts = [t for t in texts if t and t.strip()]
        if not safe_texts:
            return []

        vectors = self._model.encode( 
            safe_texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    def dim(self) -> int:
        if self._dim_cache is None:
            self._dim_cache = int(self._model.get_sentence_embedding_dimension())  # type: ignore
        return self._dim_cache
