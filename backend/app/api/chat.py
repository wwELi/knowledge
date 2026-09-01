"""Streaming RAG chat endpoint: vector retrieval + LLM proxy over SSE.

SSE contract (parsed by the frontend in useRagChat.ts):
  event: citations  data: [{index, filename, page, score, snippet}, ...]
  data: {"choices":[{"delta":{"content":"..."}}]}   (forwarded upstream frames)
  event: error      data: {"message": "..."}
  data: [DONE]      (terminal frame on every path)
"""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pgvector import Vector
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.config import config
from app.db import get_pool
from app.ingest.embedder import embed_query

router = APIRouter(prefix="/api/chat")

# Cosine-distance KNN over chunks of ready documents; nearest first.
_KNN_SQL = """
SELECT c.content, c.page, d.filename, d.id, (c.embedding <=> %s::vector) AS score
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE d.status = 'ready'
ORDER BY score
LIMIT %s
"""

_SYSTEM_PROMPT = """你是知识库问答助手。请仅依据下面提供的资料回答用户问题：
- 每个论断后标注引用角标 [n]，编号 n 与资料编号一致。
- 如果资料与问题无关或不足以回答，请明确说明未找到相关内容。
- 不要编造资料中不存在的信息。

资料：
{context}"""

_MAX_SNIPPET = 200
_LLM_TIMEOUT = 120.0
_DATA_PREFIX = "data: "


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    top_k: int | None = None


def _sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _sse_data(data: str) -> str:
    return f"data: {data}\n\n"


def _error_frames(message: str) -> list[str]:
    payload = json.dumps({"message": message}, ensure_ascii=False)
    return [_sse_event("error", payload), _sse_data("[DONE]")]


def _delta_frame(content: str) -> str:
    payload = json.dumps({"choices": [{"delta": {"content": content}}]}, ensure_ascii=False)
    return _sse_data(payload)


async def _retrieve(question: str, top_k: int) -> list[dict]:
    """Embed the question and run KNN; returns raw hits with full content."""
    # Embedding is CPU-bound ONNX inference; keep it off the event loop (same
    # as the ingest pipeline).
    query_vec = await asyncio.to_thread(embed_query, question)
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_KNN_SQL, (Vector(query_vec), top_k))
        rows = await cur.fetchall()
    return [
        {
            "filename": row["filename"],
            "page": row["page"],
            "content": row["content"],
            "score": row["score"],
        }
        for row in rows
    ]


def _citations(hits: list[dict]) -> list[dict]:
    return [
        {
            "index": i + 1,
            "filename": hit["filename"],
            "page": hit["page"],
            "score": hit["score"],
            "snippet": hit["content"][:_MAX_SNIPPET],
        }
        for i, hit in enumerate(hits)
    ]


def _context(hits: list[dict]) -> str:
    return "\n".join(
        f"[{i + 1}] （{hit['filename']} 第{hit['page']}页）{hit['content']}"
        for i, hit in enumerate(hits)
    )


async def _stream(request: Request, body: ChatRequest, top_k: int) -> AsyncIterator[str]:
    question = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), None
    )
    if question is None or not question.strip():
        for frame in _error_frames("请求中没有用户消息。"):
            yield frame
        return

    try:
        hits = await _retrieve(question, top_k)
    except psycopg.Error:
        for frame in _error_frames("检索知识库失败，请稍后重试。"):
            yield frame
        return

    yield _sse_event("citations", json.dumps(_citations(hits), ensure_ascii=False))

    if not hits:
        yield _delta_frame("知识库中未找到相关内容。")
        yield _sse_data("[DONE]")
        return

    payload = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT.format(context=_context(hits))},
            *[{"role": m.role, "content": m.content} for m in body.messages],
        ],
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{config.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    for frame in _error_frames(f"模型服务返回异常（HTTP {response.status_code}）。"):
                        yield frame
                    return
                async for line in response.aiter_lines():
                    if await request.is_disconnected():
                        # Leaving the generator closes both async-with blocks,
                        # releasing the upstream stream context.
                        return
                    if not line.startswith(_DATA_PREFIX):
                        continue
                    data = line[len(_DATA_PREFIX) :]
                    yield _sse_data(data)
                    if data == "[DONE]":
                        return
    except httpx.HTTPError:
        for frame in _error_frames("调用模型服务失败，请稍后重试。"):
            yield frame
        return

    # Upstream ended without the terminal frame and without client disconnect.
    for frame in _error_frames("模型服务连接中断。"):
        yield frame


@router.post("")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    # top_k in the body overrides config.TOP_K; clamp to >= 0.
    top_k = max(body.top_k, 0) if body.top_k is not None else config.TOP_K
    return StreamingResponse(
        _stream(request, body, top_k),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
