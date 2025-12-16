from __future__ import annotations

from typing import Any, Dict, List


def format_sources(hits: List[Dict[str, Any]]) -> str:
    """
    Красивые источники для ответа.
    Только: название файла + страницы (если есть).
    """
    lines: List[str] = []

    for idx, h in enumerate(hits, start=1):
        payload = h.get("payload") or {}
        file_name = payload.get("file_name") or payload.get("source_file") or "unknown"

        page_start = payload.get("page_start")
        page_end = payload.get("page_end")

        if page_start is None and page_end is None:
            lines.append(f"[{idx}] {file_name}")
        else:
            ps = page_start if page_start is not None else page_end
            pe = page_end if page_end is not None else page_start
            lines.append(f"[{idx}] {file_name}, pages={ps}-{pe}")

    return "\n".join(lines)


def build_prompt(question: str, hits: List[Dict[str, Any]], max_chars: int = 4000) -> str:
    parts: List[str] = []
    used = 0

    meta_lines = []
    for i, h in enumerate(hits, start=1):
        p = h.get("payload") or {}
        fn = p.get("file_name") or "unknown"
        ps = p.get("page_start")
        pe = p.get("page_end")
        if ps is None and pe is None:
            meta_lines.append(f"[{i}] file={fn}")
        else:
            ps = ps if ps is not None else pe
            pe = pe if pe is not None else ps
            meta_lines.append(f"[{i}] file={fn}, pages={ps}-{pe}")

    meta_block = "\n".join(meta_lines)

    for i, h in enumerate(hits, start=1):
        payload = h.get("payload") or {}
        txt = (payload.get("text") or "").strip()
        if not txt:
            continue

        header = f"\n=== SOURCE [{i}] ===\n"
        block = header + txt + "\n"
        if used + len(block) > max_chars:
            break

        parts.append(block)
        used += len(block)

    context = "".join(parts).strip()

    return f"""Вопрос: {question}

Метаданные источников (их можно использовать как факты):
{meta_block}

Контекст (фрагменты из документов):
{context}

Инструкция:
1) Ответь кратко и по делу.
2) Старайся использовать факты из Контекста.
3) Из 10 предоставленных источников выбери лучшие по смыслу
3) В тексте ответа после каждого утверждения указывай источник в формате: ([номер источника, стр. X–Y]).
   Если факт взят из метаданных (например, из названия файла) — всё равно укажи: ([номер источника, metadata]).
4) В конце добавь "Источники:" — только файл и страницы.
"""


