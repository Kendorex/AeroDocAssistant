# src/chunking.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List
from chonkie import TokenChunker


def _sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def _u64_from_sha1(s: str) -> int:
    h = hashlib.sha1(s.encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(h[:8], byteorder="big", signed=False)


@dataclass
class Chunk:
    id: int               
    text: str
    chunk_index: int
    meta: Dict[str, Any]


def chunk_with_chonkie(
    text: str,
    *,
    meta: Dict[str, Any],
    target_chars: int,
    min_chars: int,
    overlap: int,
    tokenizer: str = "character",
) -> List[Chunk]:
    doc_id = meta.get("doc_id")
    if not doc_id:
        raise ValueError("meta must contain doc_id")

    spans = meta.get("page_spans") or []

    def _pages_for_range(a: int, b: int):
        if not spans:
            return None, None
        ps = None
        pe = None
        for sp in spans:
            if sp["end"] <= a:
                continue
            if sp["start"] >= b:
                break
            if ps is None:
                ps = sp["page"]
            pe = sp["page"]
        return ps, pe

    chunker = TokenChunker(
        tokenizer=tokenizer,
        chunk_size=target_chars,
        chunk_overlap=overlap,
    )
    parts = chunker.chunk(text)

    chunks: List[Chunk] = []
    cursor = 0

    for i, p in enumerate(parts, start=1):
        chunk_text = (p.text if hasattr(p, "text") else str(p)).strip()
        if not chunk_text or len(chunk_text) < min_chars:
            continue

        pos = text.find(chunk_text, cursor)
        if pos == -1:
            pos = cursor
        start = pos
        end = start + len(chunk_text)
        cursor = end

        chunk_id = _sha1_hex(f"{doc_id}|{i}|{_sha1_hex(chunk_text)}")
        point_id = _u64_from_sha1(chunk_id)

        page_start, page_end = _pages_for_range(start, end)

        chunk_meta = {k: v for k, v in meta.items() if k != "page_spans"}
        chunk_meta.update(
            {
                "chunk_id": chunk_id,
                "chunk_index": i,
                "char_start": start,
                "char_end": end,
                "page_start": page_start,
                "page_end": page_end,
            }
        )

        chunks.append(Chunk(id=point_id, text=chunk_text, chunk_index=i, meta=chunk_meta))

    return chunks

