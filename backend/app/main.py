from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents

app = FastAPI(title="Knowledge Base RAG")

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

# Router registration for T7 (query/chat API): app.include_router(...)
