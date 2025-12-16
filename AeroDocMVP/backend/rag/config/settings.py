from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    # paths
    documents_dir: str = os.getenv("DOCUMENTS_DIR", "documents")
    exports_dir: str = os.getenv("EXPORTS_DIR", "exports")

    fts_db_path: str = os.getenv("FTS_DB_PATH", "exports/fts.sqlite3")
    # qdrant
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection: str = os.getenv("QDRANT_COLLECTION", "my_documents")
    vector_name: str = os.getenv("VECTOR_NAME", "dense")

    # embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
    encode_batch_size: int = int(os.getenv("ENCODE_BATCH_SIZE", "32"))

    # chunking
    target_chunk_chars: int = int(os.getenv("CHUNK_CHARS", "1800"))
    min_chunk_chars: int = int(os.getenv("MIN_CHUNK_CHARS", "300"))
    overlap_chars: int = int(os.getenv("OVERLAP_CHARS", "200"))

    # ingest behavior
    upsert_batch_size: int = int(os.getenv("UPSERT_BATCH_SIZE", "128"))
    wipe_collection: bool = os.getenv("WIPE_COLLECTION", "false").lower() in ("1", "true", "yes")

    # retries
    qdrant_ready_timeout_s: int = int(os.getenv("QDRANT_READY_TIMEOUT_S", "120"))
    qdrant_retry_count: int = int(os.getenv("QDRANT_RETRY_COUNT", "15"))
    qdrant_retry_sleep_s: float = float(os.getenv("QDRANT_RETRY_SLEEP_S", "2.0"))

    