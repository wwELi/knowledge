"""Local embedding service backed by fastembed (BAAI/bge-small-zh-v1.5, 512-dim).

Passages and queries are embedded through the exact same code path (no query
prefix), so seed chunks and ingested chunks live in the same vector space.
"""

import sys

from fastembed import TextEmbedding

from app.config import config

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """Lazily construct the shared TextEmbedding singleton.

    First call downloads the model (~90MB) from HuggingFace. On a
    connection/download failure, hint at the HF mirror on stderr and retry once.
    """
    global _model
    if _model is None:
        try:
            _model = TextEmbedding(model_name=config.EMBED_MODEL)
        except Exception:
            # huggingface_hub surfaces network failures as different exception
            # types per version (ConnectionError, LocalEntryNotFoundError,
            # OSError, ...), so this boundary catches broadly; if the mirror
            # retry also fails, the second exception propagates untouched.
            print(
                "Model download failed. Retry with mirror: "
                "export HF_ENDPOINT=https://hf-mirror.com",
                file=sys.stderr,
            )
            _model = TextEmbedding(model_name=config.EMBED_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts as passages; returns one 512-dim vector per text."""
    if not texts:
        return []
    vectors = [v.tolist() for v in get_model().passage_embed(texts)]
    assert len(vectors) == len(texts)
    assert all(len(v) == config.EMBED_DIM for v in vectors)
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a query identically to ingest-side passages (same encoding, no prefix)."""
    return embed_texts([text])[0]
