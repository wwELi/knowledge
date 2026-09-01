"""PDF text extraction with pdfplumber fallback."""

from collections.abc import Callable
from pathlib import Path


class ParseError(Exception):
    """Raised when no PDF backend can extract text from the file."""


# Minimum characters for pymupdf output to be considered a success.
_MIN_CHARS = 50


def _try_pymupdf(path: Path) -> list[tuple[int, str]]:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore[no-redef]

    pages: list[tuple[int, str]] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            pages.append((i + 1, page.get_text("text")))
    return pages


def _try_pdfplumber(path: Path) -> list[tuple[int, str]]:
    import pdfplumber

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append((i + 1, page.extract_text() or ""))
    return pages


def _extract_with(backend: Callable[[Path], list[tuple[int, str]]], path: Path) -> list[tuple[int, str]]:
    pages = backend(path)
    if sum(len(text) for _, text in pages) < _MIN_CHARS:
        raise ValueError("extraction yielded too few characters")
    return [(n, text) for n, text in pages if text.strip()]


def extract_pages(path: str | Path) -> list[tuple[int, str]]:
    """Extract (page_number, text) from a PDF, page numbers starting at 1.

    Tries pymupdf first; on failure or near-empty output falls back to
    pdfplumber. Raises ParseError when both fail. Empty-text pages are skipped.
    """
    path = Path(path)
    errors: list[str] = []
    for name, backend in (("pymupdf", _try_pymupdf), ("pdfplumber", _try_pdfplumber)):
        try:
            return _extract_with(backend, path)
        except Exception as exc:  # noqa: BLE001 - any backend failure triggers fallback
            errors.append(f"{name}: {exc}")
    raise ParseError(f"failed to parse {path}: " + "; ".join(errors))
