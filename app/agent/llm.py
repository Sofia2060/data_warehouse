"""
llm.py - Goi Groq Cloud API (OpenAI-compatible chat completions).
"""
import json

from common import config


class LLMError(Exception):
    pass


_client = None


def _get_client():
    global _client
    if not config.GROQ_API_KEY:
        raise LLMError("Chưa cấu hình GROQ_API_KEY (xem file .env).")
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=config.GROQ_API_KEY, timeout=60, max_retries=2)
    return _client


def chat(messages: list, json_mode: bool = False, max_tokens: int = 4096) -> str:
    kwargs = {"model": config.GROQ_MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = _get_client().chat.completions.create(**kwargs)
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 - loi mang, sai khoa, het han muc...
        raise LLMError(f"Gọi Groq API thất bại: {exc}") from exc
    return (resp.choices[0].message.content or "").strip()


def chat_json(messages: list) -> dict:
    raw = chat(messages, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM không trả về JSON hợp lệ: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM trả về JSON không phải đối tượng.")
    return data
