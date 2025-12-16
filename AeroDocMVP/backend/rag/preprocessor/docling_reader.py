from pathlib import Path
from typing import Dict, Any, List
import hashlib
from datetime import datetime, timezone
import json

import fitz  # PyMuPDF
from docling.document_converter import DocumentConverter

fitz.TOOLS.mupdf_display_errors(False)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def _make_pseudo_page_spans_by_lines(text: str, *, lines_per_page: int = 80) -> List[Dict[str, int]]:
    """
    Делает псевдо-страницы по строкам, но хранит start/end в символах (как для PDF).
    """
    if not text:
        return []

    spans: List[Dict[str, int]] = []
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    total_lines = len(line_starts)
    page = 1
    line_idx = 0

    while line_idx < total_lines:
        start = line_starts[line_idx]
        next_line_idx = min(line_idx + lines_per_page, total_lines)
        end = line_starts[next_line_idx] if next_line_idx < total_lines else len(text)
        spans.append({"page": page, "start": start, "end": end})
        page += 1
        line_idx = next_line_idx

    return spans


def read_with_docling(path: Path) -> Dict[str, Any]:
    st = path.stat()
    modified_at = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
    doc_id = _sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime}")

    suffix = path.suffix.lower()
    mime_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xml": "application/xml",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")

    meta: Dict[str, Any] = {
        "doc_id": doc_id,
        "file_name": path.name,
        "file_path": str(path),
        "suffix": suffix,
        "mime_type": mime_type,
        "file_size_bytes": int(st.st_size),
        "modified_at": modified_at,
        "loader": "docling",
        "source_type": "pdf" if suffix == ".pdf" else ("docx" if suffix == ".docx" else "file"),
        "ocr_used": "unknown",
        "language_hint": "unknown",
    }

    # ✅ PDF: реальные страницы
    if suffix == ".pdf":
        d = fitz.open(str(path))
        parts = []
        spans = []
        cursor = 0

        for i in range(d.page_count):
            t = d.load_page(i).get_text("text") or ""
            if i != d.page_count - 1:
                t += "\n\n"
            start = cursor
            parts.append(t)
            cursor += len(t)
            end = cursor
            spans.append({"page": i + 1, "start": start, "end": end})

        text = "".join(parts)
        meta["page_count"] = d.page_count
        meta["page_spans"] = spans
        meta["stats"] = {"chars": len(text), "lines": text.count("\n") + 1}
        return {"text": text, "meta": meta}

    # ✅ JSON: pretty + псевдо-страницы
    if suffix == ".json":
        raw = path.read_text(encoding="utf-8", errors="ignore")
        try:
            obj = json.loads(raw)
            text = json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            # если битый JSON — просто используем сырой текст
            text = raw

        spans = _make_pseudo_page_spans_by_lines(text, lines_per_page=80)
        meta["page_spans"] = spans
        meta["page_count"] = len(spans) if spans else 1
        meta["stats"] = {"chars": len(text), "lines": text.count("\n") + 1}
        return {"text": text, "meta": meta}

    # ✅ XML: как текст + псевдо-страницы
    if suffix == ".xml":
        text = path.read_text(encoding="utf-8", errors="ignore")
        spans = _make_pseudo_page_spans_by_lines(text, lines_per_page=80)
        meta["page_spans"] = spans
        meta["page_count"] = len(spans) if spans else 1
        meta["stats"] = {"chars": len(text), "lines": text.count("\n") + 1}
        return {"text": text, "meta": meta}

    # ✅ Все остальные форматы (DOCX, TXT и др.) через docling с псевдо-страницами
    converter = DocumentConverter()
    result = converter.convert(str(path))
    text = (
        result.document.export_to_markdown()
        if hasattr(result.document, "export_to_markdown")
        else str(result.document)
    )
    
    # Добавляем псевдо-страницы для всех не-PDF файлов
    spans = _make_pseudo_page_spans_by_lines(text, lines_per_page=80)
    meta["page_spans"] = spans
    meta["page_count"] = len(spans) if spans else 1
    meta["stats"] = {"chars": len(text), "lines": text.count("\n") + 1}
    
    return {"text": text, "meta": meta}