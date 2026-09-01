"""Recursive character chunking (stdlib only)."""

from dataclasses import dataclass

from app.ingest.models import Chunk

_SEPARATORS = ["\n\n", "\n", "。", "．", ". ", " ", ""]


@dataclass(frozen=True, slots=True)
class _ChunkParams:
    size: int
    overlap: int


def _split_pieces(text: str, size: int, seps: list[str]) -> list[str]:
    """Split text into pieces, each with len <= size, concatenating back to text."""
    if len(text) <= size:
        return [text]
    sep = next((s for s in seps if s and s in text), "")
    if not sep:
        return [text[i : i + size] for i in range(0, len(text), size)]
    rest = seps[seps.index(sep) + 1 :]
    parts = text.split(sep)
    pieces = [part + sep for part in parts[:-1]] + [parts[-1]]
    return [
        sub
        for piece in pieces
        if piece
        for sub in _split_pieces(piece, size, rest)
    ]


def _pack(pieces: list[str], size: int, overlap: int) -> list[str]:
    """Pack pieces into chunks of len <= size; consecutive chunks share `overlap` chars."""
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        while piece:
            room = size - len(buf)
            if len(piece) <= room:
                buf += piece
                break
            buf += piece[:room]
            piece = piece[room:]
            chunks.append(buf)
            buf = buf[len(buf) - overlap :] if overlap else ""
    if buf:
        chunks.append(buf)
    return chunks


def recursive_chunk(
    pages: list[tuple[int, str]], size: int = 500, overlap: int = 80
) -> list[Chunk]:
    """Chunk page texts into Chunk(text, page), each chunk at most `size` chars.

    Adjacent chunks within a page share `overlap` characters. Pages whose text
    is empty after stripping are skipped. Each chunk belongs to a single page.
    """
    params = _ChunkParams(size=size, overlap=overlap)
    if params.size <= 0 or not 0 <= params.overlap < params.size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    chunks: list[Chunk] = []
    for page, text in pages:
        stripped = text.strip()
        if not stripped:
            continue
        pieces = _split_pieces(stripped, params.size, _SEPARATORS)
        chunks.extend(
            Chunk(text=packed, page=page)
            for packed in _pack(pieces, params.size, params.overlap)
            if packed.strip()
        )
    return chunks
