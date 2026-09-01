from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents

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
app.include_router(chat.router)
