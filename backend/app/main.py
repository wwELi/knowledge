import sys
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print("Running database migration...")
    try:
        command.upgrade(Config("alembic.ini"), "head")
    except Exception as exc:
        # Do not block startup: DB may be temporarily unreachable during dev.
        print(f"Database migration failed: {exc}", file=sys.stderr)
    else:
        print("Database migration OK")
    yield


app = FastAPI(title="Knowledge Base RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(documents.router)
app.include_router(chat.router)
