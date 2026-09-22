"""Title/author extraction for an uploaded PDF, ahead of the parse stage.

Uses ``pypdfium2`` directly rather than Docling's own conversion — reading the
``/Info`` dictionary is milliseconds against a 400-page file, versus the full
convert Docling would need to do the same. No new dependency: ``pypdfium2`` is
already pulled in transitively as Docling's PDF backend.
"""

import logging
import re
from pathlib import Path

import pypdfium2 as pdfium

logger = logging.getLogger(__name__)


def extract_title_author(
    path: Path, *, fallback_filename: str
) -> tuple[str, str | None]:
    """Return ``(title, author)`` for an uploaded PDF.

    Args:
        path: Local path to the uploaded file.
        fallback_filename: The client's original filename, used to derive a
            title when the PDF carries none — a scanned or stripped PDF often
            has an empty ``/Info`` dictionary.

    Returns:
        A title (never empty) and an author, if the PDF declares one.
    """
    title: str | None = None
    author: str | None = None

    try:
        document = pdfium.PdfDocument(str(path))
        try:
            info = document.get_metadata_dict()
        finally:
            document.close()
        title = (info.get("Title") or "").strip() or None
        author = (info.get("Author") or "").strip() or None
    except Exception:
        # A PDF too damaged for pdfium to open its metadata is not rejected
        # here — that is the parse stage's job (DocumentParseError). Upload
        # only needs a display title, which the filename can still supply.
        logger.warning("could not read PDF metadata from %s", path, exc_info=True)

    if not title:
        title = _title_from_filename(fallback_filename)

    return title, author


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    words = [word for word in re.split(r"[_\-\s]+", stem) if word]

    if not words:
        return "Untitled"

    title = " ".join(word if word.isupper() else word.capitalize() for word in words)

    return title
