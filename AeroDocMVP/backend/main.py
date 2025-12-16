from pathlib import Path
import sys
import anyio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import re

from rag_service import answer_question

app = FastAPI(title="AeroDoc MVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANT: use 127.0.0.1 (IPv4) to avoid localhost/IPv6 issues on Windows
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "llama3:8b"

LABELS = {"rag_query", "greeting", "junk"}

SYSTEM_PROMPT = """
Ты — классификатор пользовательских сообщений для чат-ассистента по авиационной документации.
Верни ТОЛЬКО один label из списка:
- rag_query: реальный вопрос по авиа-теме/процедурам/документации/эксплуатации
- greeting: приветствие, small talk, кто ты, как дела
- junk: мусор/непонятно/случайные символы/не по теме
Никаких пояснений. Только label.
""".strip()


class ClassifyRequest(BaseModel):
    text: str


class ClassifyResponse(BaseModel):
    label: str


def normalize_label(s: str) -> str:
    t = s.strip().lower()
    t = re.sub(r"[^a-z_]", "", t)
    return t if t in LABELS else "junk"


async def ollama_chat(system_prompt: str, user_text: str) -> str:
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "options": {"temperature": 0.0},
    }

    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            r = await client.post(OLLAMA_URL, json=payload)
            if r.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama HTTP {r.status_code}. Body: {r.text}",
                )
            data = r.json()

        msg = data.get("message") or {}
        content = msg.get("content")
        if not content:
            raise HTTPException(status_code=502, detail=f"Unexpected Ollama response: {data}")

        return content

    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Ollama at {OLLAMA_URL}. {e}")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Timeout calling Ollama")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error calling Ollama: {repr(e)}")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest):
    text = (req.text or "").strip()
    if not text:
        return {"label": "junk"}

    raw = await ollama_chat(SYSTEM_PROMPT, text)
    label = normalize_label(raw)
    return {"label": label}





from typing import List, Optional
from pydantic import BaseModel

class ChatRequest(BaseModel):
    text: str
    file_name: Optional[str] = None
    top_k: Optional[int] = None
    score_threshold: Optional[float] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []


from functools import partial

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    text = (req.text or "").strip()
    if not text:
        return {"answer": "Пустой запрос.", "sources": []}

    fn = partial(
        answer_question,
        text,
        file_name=req.file_name,
        top_k=req.top_k,
        score_threshold=req.score_threshold,
    )

    answer, sources = await anyio.to_thread.run_sync(fn)
    return {"answer": answer, "sources": sources}


@app.get("/models")
async def models():
    return {"ollama_model": MODEL, "ollama_url": OLLAMA_URL}
