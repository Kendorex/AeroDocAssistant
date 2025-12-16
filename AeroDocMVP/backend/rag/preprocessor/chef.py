# src/chef.py
from __future__ import annotations
import re
from typing import List

_RE_MULTI_SPACES = re.compile(r"[ \t]+")
_RE_MANY_NEWLINES = re.compile(r"\n{2,}")  # >=2 схлопнем (см. clean_text)
_RE_LEADERS_1 = re.compile(r"[.\u00B7]{5,}")
_RE_LEADERS_2 = re.compile(r"(?:\s*\.\s*){5,}")

def _split_md_row(row: str) -> List[str]:
    # "| a | b |" -> ["a","b"]
    row = row.strip().strip("|")
    return [c.strip() for c in row.split("|")]

def tables_to_text(md: str, mode: str = "linearize") -> str:
    """
    mode:
      - "drop": полностью выкидываем markdown-таблицы
      - "linearize": превращаем таблицы в читабельный текст (смысл сохраняется)
    """
    lines = md.splitlines()
    out: List[str] = []

    i = 0
    while i < len(lines):
        s = lines[i].strip()

        # детект таблицы: строка с |...| и следующая строка-сепаратор |---|
        is_table_row = s.startswith("|") and s.endswith("|") and s.count("|") >= 2
        if is_table_row and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            is_sep = sep.startswith("|") and sep.endswith("|") and re.fullmatch(r"[\s\|\-:]+", sep) is not None

            if is_sep:
                # читаем header + data rows
                header = _split_md_row(lines[i])
                i += 2
                rows: List[List[str]] = []
                while i < len(lines):
                    r = lines[i].strip()
                    if not (r.startswith("|") and r.endswith("|") and r.count("|") >= 2):
                        break
                    rows.append(_split_md_row(lines[i]))
                    i += 1

                if mode == "drop":
                    continue

                # linearize
                if header:
                    out.append("ТАБЛИЦА:")
                for r in rows:
                    # row to "H1: v1; H2: v2"
                    pairs = []
                    for idx in range(max(len(header), len(r))):
                        h = header[idx] if idx < len(header) else f"col_{idx+1}"
                        v = r[idx] if idx < len(r) else ""
                        if (h or "").strip() or (v or "").strip():
                            pairs.append(f"{h}: {v}".strip())
                    if pairs:
                        out.append("; ".join(pairs))
                out.append("")  # разделитель таблицы
                continue

        out.append(lines[i])
        i += 1

    return "\n".join(out)

def normalize_leaders(text: str) -> str:
    text = _RE_LEADERS_1.sub(" : ", text)
    text = _RE_LEADERS_2.sub(" : ", text)
    text = re.sub(r"\s*:\s*:\s*", " : ", text)
    text = _RE_MULTI_SPACES.sub(" ", text)
    return text

def clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = _RE_MULTI_SPACES.sub(" ", text)

    # Нормализуем пустые строки: любые серии \n\n\n... -> \n\n
    text = re.sub(r"\n{3,}", "\n\n", text)

    # убираем пробелы в конце строк
    text = "\n".join([ln.rstrip() for ln in text.splitlines()])

    # подчистим "пустые" строки из пробелов
    text = re.sub(r"\n[ \t]+\n", "\n\n", text)

    return text.strip()

def preprocess_doc_text(md_or_text: str, *, table_mode: str = "linearize") -> str:

    text = tables_to_text(md_or_text, mode=table_mode)
    text = normalize_leaders(text)
    text = clean_text(text)
    return text
