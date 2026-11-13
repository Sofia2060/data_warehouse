"""
api.py - Dich vu HTTP cua container groq-agent (cong 8000).

    GET  /health   kiem tra dich vu song (dung cho healthcheck Docker)
    POST /ask      {"question": "..."} -> cau SQL, bang ket qua va cau tra loi
"""
from fastapi import FastAPI
from pydantic import BaseModel

from agent import core
from common import config

app = FastAPI(title="Groq LLM Agent - Text-to-SQL tren tang Gold")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "model": config.GROQ_MODEL, "groq_key_configured": bool(config.GROQ_API_KEY)}


@app.post("/ask")
def ask(req: AskRequest):
    return core.ask(req.question)
