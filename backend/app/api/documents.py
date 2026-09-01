"""Document upload, listing, and management endpoints."""

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from psycopg.rows import dict_row

from app.config import config
from app.db import get_pool
from app.ingest.pipeline import process_document

router = APIRouter(prefix="/api/documents")

# Strong references keep finished tasks out of GC limbo; the done callback
# discards each task so the set does not grow unbounded.
tasks: set[asyncio.Task] = set()

_SELECT_COLUMNS = "id, filename, status, chunk_count, error, created_at"


def _validate_upload(file: UploadFile) -> None:
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="only .pdf files are accepted")
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415, detail="content-type must be application/pdf"
        )


async def _save_upload(file: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)


@router.post("", status_code=201)
async def upload_document(file: UploadFile) -> dict[str, str]:
    _validate_upload(file)
    doc_id = uuid.uuid4()
    dest = config.UPLOAD_DIR / f"{doc_id}.pdf"
    await _save_upload(file, dest)

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO documents (id, filename, filepath) VALUES (%s, %s, %s)",
            (doc_id, file.filename, str(dest)),
        )

    task = asyncio.create_task(process_document(doc_id, dest))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"id": str(doc_id), "status": "processing"}


@router.get("")
async def list_documents() -> list[dict[str, object]]:
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_SELECT_COLUMNS} FROM documents ORDER BY created_at DESC"
        )
        return list(await cur.fetchall())


@router.get("/{doc_id}")
async def get_document(doc_id: uuid.UUID) -> dict[str, object]:
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_SELECT_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
        )
        if (row := await cur.fetchone()) is None:
            raise HTTPException(status_code=404, detail="document not found")
        return dict(row)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID) -> None:
    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT filepath FROM documents WHERE id = %s", (doc_id,))
        if (row := await cur.fetchone()) is None:
            raise HTTPException(status_code=404, detail="document not found")
        await cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    Path(str(row["filepath"])).unlink(missing_ok=True)
