from __future__ import annotations
import sys

from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm
from dotenv import load_dotenv

from config.settings import Settings
from preprocessor.docling_reader import read_with_docling
from preprocessor.chef import preprocess_doc_text
from preprocessor.chunking import chunk_with_chonkie, Chunk as SrcChunk
from embed.embeddings import Embedder
from utils.qdrant_store import QdrantStore

from utils.batch import batched
from utils.export import export_rows_jsonl_append
from utils.qdrant_retry import wait_qdrant_ready, retry
from utils.proxy import disable_proxies_for_localhost
from utils.sqlite_fts import connect_db, init_fts, upsert_chunks, delete_by_doc_id as sqlite_delete_by_doc_id


def chunk_to_row(ch: SrcChunk) -> Dict[str, Any]:
    return {"id": ch.id, "text": ch.text, **(ch.meta or {})}


def run_ingest(s: Settings) -> Path:
    load_dotenv()
    disable_proxies_for_localhost()
    docs_dir = Path(s.documents_dir)
    exports_dir = Path(s.exports_dir)
    export_path = exports_dir / "chunks.jsonl"

    sqlite_conn = connect_db(s.fts_db_path)
    init_fts(sqlite_conn)

    if not docs_dir.exists():
        raise FileNotFoundError(f"Documents dir not found: {docs_dir.resolve()}")

    files = [p for p in docs_dir.rglob("*") if p.is_file()]
    if not files:
        print(f"No files in {docs_dir.resolve()}")
        return export_path

    store = QdrantStore(url=s.qdrant_url, collection=s.collection, vector_name=s.vector_name)

    print("\n=== QDRANT CONNECT ===")
    wait_qdrant_ready(store, timeout_s=s.qdrant_ready_timeout_s)
    print("Qdrant ready:", s.qdrant_url, "| collection:", s.collection, "| vector:", s.vector_name)

    if s.wipe_collection:
        print(f"⚠️ WIPE_COLLECTION=True → deleting collection '{s.collection}'")
        retry(
            lambda: store.client.delete_collection(collection_name=s.collection),
            what="delete_collection",
            retry_count=s.qdrant_retry_count,
            sleep_s=s.qdrant_retry_sleep_s,
        )

    embedder = Embedder(s.embedding_model, batch_size=s.encode_batch_size)

    exports_dir.mkdir(parents=True, exist_ok=True)
    if export_path.exists():
        export_path.unlink()
    print("Export:", export_path.resolve())

    collection_ready = False
    total_chunks = 0

    print("\n=== STREAMING INGEST (docling -> chef -> chunking -> embeddings -> qdrant) ===")

    for path in tqdm(files, desc="Ingest"):
        try:
            doc = read_with_docling(path)
            raw_text = doc["text"]
            meta: Dict[str, Any] = doc["meta"]

            doc_id = meta.get("doc_id")
            if not doc_id:
                raise ValueError("doc meta must contain doc_id (add it in preprocessor/docling_reader.py)")

            text = preprocess_doc_text(raw_text, table_mode="linearize")

            chunks = chunk_with_chonkie(
                text,
                meta=meta,
                target_chars=s.target_chunk_chars,
                min_chars=s.min_chunk_chars,
                overlap=s.overlap_chars,
            )
            if not chunks:
                continue

            vecs = embedder.embed([c.text for c in chunks])
            if not vecs:
                continue

            if not collection_ready:
                retry(
                    lambda: store.ensure_collection(embedder.dim()),
                    what="ensure_collection",
                    retry_count=s.qdrant_retry_count,
                    sleep_s=s.qdrant_retry_sleep_s,
                )
                collection_ready = True

            retry(
                lambda: store.delete_by_doc_id(doc_id),
                what=f"delete_by_doc_id({doc_id})",
                retry_count=s.qdrant_retry_count,
                sleep_s=s.qdrant_retry_sleep_s,
            )
            sqlite_delete_by_doc_id(sqlite_conn, doc_id)

            points: List[Dict[str, Any]] = []
            for c, v in zip(chunks, vecs):
                points.append({"id": c.id, "vector": v, "payload": {"text": c.text, **c.meta}})

            for batch in batched(points, s.upsert_batch_size):
                retry(
                    lambda b=batch: store.upsert(b),
                    what=f"upsert({path.name})",
                    retry_count=s.qdrant_retry_count,
                    sleep_s=s.qdrant_retry_sleep_s,
                )

            export_rows_jsonl_append([chunk_to_row(c) for c in chunks], export_path)
            total_chunks += len(chunks)

        except Exception as e:
            print(f"[ERROR] {path.name}: {repr(e)}")

    print("\n=== DONE ===")
    print("Files:", len(files))
    print("Total chunks:", total_chunks)
    print("Export:", export_path.resolve())
    try:
        sqlite_conn.close()
    except Exception:
        pass
    return export_path


def main() -> None:
    load_dotenv()
    s = Settings()
    run_ingest(s)

if __name__ == "__main__":
    main()