"""Background document ingestion: extract -> chunk -> embed -> persist."""

import asyncio
import uuid
from pathlib import Path

from app.config import config
from app.db import get_pool
from app.ingest.chunker import recursive_chunk
from app.ingest.embedder import embed_texts
from app.ingest.pdf_parser import extract_pages

# Embeddings are computed in batches; between batches `await asyncio.sleep(0)`
# yields to the event loop so API requests stay responsive.
_EMBED_BATCH_SIZE = 32


async def process_document(doc_id: uuid.UUID, filepath: Path) -> None:
    """Ingest one stored PDF, then mark it ready (or failed with the error).

    CPU-heavy extraction and embedding run in a worker thread via
    asyncio.to_thread so the event loop is never blocked.
    """
    try:
        pages = await asyncio.to_thread(extract_pages, filepath)
        chunks = recursive_chunk(
            pages, size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP
        )

        count = 0
        for start in range(0, len(chunks), _EMBED_BATCH_SIZE):
            batch = chunks[start : start + _EMBED_BATCH_SIZE]
            vectors = await asyncio.to_thread(
                embed_texts, [chunk.text for chunk in batch]
            )
            rows = [
                (doc_id, chunk.text, chunk.page, vector)
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
            pool = await get_pool()
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO chunks (document_id, content, page, embedding)"
                    " VALUES (%s, %s, %s, %s)",
                    rows,
                )
            count += len(rows)
            await asyncio.sleep(0)

        pool = await get_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE documents SET status = 'ready', chunk_count = %s WHERE id = %s",
                (count, doc_id),
            )
    except Exception as exc:
        pool = await get_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE documents SET status = 'failed', error = %s WHERE id = %s",
                (str(exc), doc_id),
            )
