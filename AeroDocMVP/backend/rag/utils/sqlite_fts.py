# utils/sqlite_fts.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def connect_db(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_fts(conn: sqlite3.Connection) -> None:
    # Основная таблица с метой
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id          INTEGER PRIMARY KEY,
            text        TEXT NOT NULL,
            doc_id      TEXT,
            file_name   TEXT,
            chunk_id    TEXT,
            chunk_index INTEGER,
            page_start  INTEGER,
            page_end    INTEGER,
            char_start  INTEGER,
            char_end    INTEGER
        );
        """
    )

    # FTS5 индекс по text (BM25 доступен через bm25(chunks_fts))
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(
            text,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61'
        );
        """
    )

    # Индексы для фильтров/джойнов
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_name ON chunks(file_name);")
    conn.commit()


def upsert_chunks(conn: sqlite3.Connection, rows: Iterable[Dict[str, Any]]) -> None:
    """
    rows: {"id": int, "text": str, ...meta fields...}
    Держим chunks и chunks_fts синхронно.
    """
    cur = conn.cursor()
    cur.execute("BEGIN;")

    for r in rows:
        cid = int(r["id"])
        text = str(r.get("text") or "")

        doc_id = r.get("doc_id")
        file_name = r.get("file_name") or r.get("source_file")
        chunk_id = r.get("chunk_id")
        chunk_index = r.get("chunk_index")
        page_start = r.get("page_start")
        page_end = r.get("page_end")
        char_start = r.get("char_start")
        char_end = r.get("char_end")

        # upsert meta+text
        cur.execute(
            """
            INSERT OR REPLACE INTO chunks
            (id, text, doc_id, file_name, chunk_id, chunk_index, page_start, page_end, char_start, char_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                text,
                doc_id,
                file_name,
                chunk_id,
                chunk_index,
                page_start,
                page_end,
                char_start,
                char_end,
            ),
        )

        # обновляем fts: delete старое и вставляем новое
        cur.execute("INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', ?, '')", (cid,))
        cur.execute("INSERT INTO chunks_fts(rowid, text) VALUES(?, ?)", (cid, text))

    cur.execute("COMMIT;")


def delete_by_doc_id(conn: sqlite3.Connection, doc_id: str) -> None:
    """
    Синхронное удаление чанков документа из chunks и fts.
    """
    cur = conn.cursor()
    cur.execute("BEGIN;")
    ids = [row["id"] for row in cur.execute("SELECT id FROM chunks WHERE doc_id = ?", (doc_id,)).fetchall()]

    for cid in ids:
        cur.execute("INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', ?, '')", (cid,))
        cur.execute("DELETE FROM chunks WHERE id = ?", (cid,))

    cur.execute("COMMIT;")


def bm25_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 10,
    file_name: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Возвращает список словарей как у dense:
      {"id": ..., "score": ..., "payload": {...}}
    В SQLite FTS5 bm25() — меньше = лучше, поэтому score делаем отрицательным.
    """
    q = (query or "").strip()
    if not q:
        return []

    where = ["chunks_fts MATCH ?"]
    params: List[Any] = [q]

    if file_name:
        where.append("c.file_name = ?")
        params.append(file_name)

    if doc_id:
        where.append("c.doc_id = ?")
        params.append(doc_id)

    sql = f"""
        SELECT
            c.id AS id,
            c.text AS text,
            c.doc_id AS doc_id,
            c.file_name AS file_name,
            c.chunk_id AS chunk_id,
            c.chunk_index AS chunk_index,
            c.page_start AS page_start,
            c.page_end AS page_end,
            c.char_start AS char_start,
            c.char_end AS char_end,
            bm25(chunks_fts) AS bm25_score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE {" AND ".join(where)}
        ORDER BY bm25_score ASC
        LIMIT ?
    """
    params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        payload = {
            "text": r["text"],
            "doc_id": r["doc_id"],
            "file_name": r["file_name"],
            "chunk_id": r["chunk_id"],
            "chunk_index": r["chunk_index"],
            "page_start": r["page_start"],
            "page_end": r["page_end"],
            "char_start": r["char_start"],
            "char_end": r["char_end"],
        }
        out.append(
            {
                "id": r["id"],
                "score": float(-r["bm25_score"]),  # больше = лучше
                "payload": payload,
            }
        )
    return out
