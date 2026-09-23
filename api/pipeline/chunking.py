import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import cast

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from api.llm import plan_batches, structured_call

from ..config.settings import Settings
from ..config.settings import settings as default_settings
from ..contracts.enums import DetectionMethod, LLMPurpose
from ..contracts.pipeline import ChapterInfo, ChunkPayload
from .constants import (
    CHAPTER_RE,
    CHUNK_MAX_TOKENS,
    ROMAN_VALUES,
    ChapterBatchStructuredOutput,
)
from .errors import DocumentParseError, MissingProvenanceError, PageParseError

logger = logging.getLogger(__name__)


def resolve_device(requested: str) -> str:
    """Return the device to load models on, falling back to CPU when asked for a GPU.

    Two agents loading BGE-M3 onto one consumer card will OOM, so worktrees run
    on CPU; a machine with no CUDA at all must degrade rather than crash.

    Args:
        requested: Device from settings, e.g. ``cuda``, ``cuda:0``, ``cpu``.

    Returns:
        ``requested`` if it is usable, otherwise ``"cpu"``.
    """
    if not requested.startswith("cuda"):
        return requested

    try:
        import torch
    except ImportError:
        logger.warning("torch is not installed; falling back to CPU.")

        return "cpu"

    if not torch.cuda.is_available():
        logger.warning("%s requested but CUDA is unavailable; using CPU.", requested)

        return "cpu"

    return requested


@lru_cache(maxsize=4)
def _document_converter(artifacts_path: str | None, ocr: bool) -> DocumentConverter:
    pipeline_options = PdfPipelineOptions(
        artifacts_path=Path(artifacts_path) if artifacts_path else None,
        do_ocr=ocr,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


@lru_cache(maxsize=2)
def _tokenizer(model_id: str, max_tokens: int) -> HuggingFaceTokenizer:
    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(model_id), max_tokens=max_tokens
    )


@lru_cache(maxsize=2)
def _embedding_model(model_id: str, device: str) -> SentenceTransformer:
    return SentenceTransformer(model_id, device=device)


def _roman_to_int(roman: str) -> int:
    total = 0
    highest = 0

    for char in reversed(roman.upper()):
        value = ROMAN_VALUES[char]
        total += -value if value < highest else value
        highest = max(highest, value)

    return total


def _normalize_chapter_number(number: str) -> int | None:
    """Convert a matched chapter number ("3", "3.1", "IV") to an integer."""
    number = number.strip()
    leading = number.split(".")[0]

    if leading.isdigit():
        return int(leading)

    if number and set(number.upper()) <= ROMAN_VALUES.keys():
        return _roman_to_int(number)

    return None


class DocumentChunker:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        llm_classify: bool = True,
        ocr: bool = False,
    ) -> None:
        self.settings = settings or default_settings
        self.llm_classify = llm_classify
        # OCR is off by default because the corpus is digitally-typeset novels
        # with a real text layer. Turning it on pulls in RapidOCR, which
        # downloads its own weights from modelscope.cn outside the Hugging Face
        # cache and claims CUDA device 0 regardless of EMBEDDING_DEVICE — both
        # of which break a worktree run (BRANCH.md §9). A scanned book opts in.
        self.ocr = ocr

    # Public methods.
    def warm(self) -> None:
        """Load every model this chunker needs into the current process.

        Called once per worker process so the first task of a worker's life is
        not also the one that pays a multi-second model load.
        """
        _document_converter(self._artifacts_path(), self.ocr)
        _tokenizer(self.settings.embedding_model_id, CHUNK_MAX_TOKENS)
        _embedding_model(self.settings.embedding_model_id, self.device)

    @property
    def device(self) -> str:
        return resolve_device(self.settings.embedding_device)

    def load_document(self, document_path: Path) -> DoclingDocument:
        """Convert a file on disk into a Docling document.

        Args:
            document_path: Path to the source file.

        Returns:
            The converted document.

        Raises:
            DocumentParseError: If conversion fails outright. A file that
                cannot be parsed cannot be parsed on a retry either.
            PageParseError: If the backend dropped individual pages. This is
                transient: the same file converted twice in a row can yield
                pages [1, 3] and then [1, 2, 3], and a silently missing page is
                a citation that can never be made (PRD F1.3).
        """
        converter = _document_converter(self._artifacts_path(), self.ocr)

        try:
            result = converter.convert(document_path)
        except Exception as exc:
            raise DocumentParseError(f"cannot convert {document_path.name}") from exc

        failed = sorted(
            {error.page_no for error in result.errors if error.page_no is not None}
        )

        if failed:
            raise PageParseError(
                f"{document_path.name}: pages {failed} failed to parse"
            )

        return result.document

    async def prepare_chapters(
        self, document: DoclingDocument, *, book_id: str | None = None
    ) -> list[tuple[object, ChapterInfo]]:
        """Public entry to the heading pass shared by ``detect_chapters`` and
        ``generate_chunks``.

        A caller needing both (``pipeline.tasks._parse_and_chunk`` does, to
        write chunks and the chapter side-artifact from one document) should
        call this once and pass the result to both as ``prepared=`` — each
        recomputes it internally otherwise, doubling the LLM classification
        calls the batching in ``_classify_headings`` exists to minimise.
        """
        return await self._prepare_chapters(document, book_id=book_id)

    async def detect_chapters(
        self,
        document: DoclingDocument,
        *,
        book_id: str | None = None,
        prepared: list[tuple[object, ChapterInfo]] | None = None,
    ) -> list[ChapterInfo]:
        """Return the chapter headings found in a document, in document order.

        Args:
            document: A converted document.
            book_id: Tags the Langfuse trace of any LLM classification call.
            prepared: Reuse a prior ``prepare_chapters`` call instead of
                redoing the heading pass.

        Returns:
            One entry per detected chapter heading.
        """
        if prepared is None:
            prepared = await self.prepare_chapters(document, book_id=book_id)

        chapters = [info for _item, info in prepared if info.is_chapter]

        return chapters

    async def generate_chunks(
        self,
        document: DoclingDocument,
        *,
        embed: bool = True,
        book_id: str | None = None,
        prepared: list[tuple[object, ChapterInfo]] | None = None,
    ) -> list[ChunkPayload]:
        """Split a document into persistable chunks carrying page provenance.

        Chunks inherit the most recently seen chapter heading, so a mid-chapter
        chunk with no heading of its own still knows which chapter it is in.

        Args:
            document: A converted document.
            embed: Whether to compute embeddings. ``False`` skips loading
                BGE-M3 entirely, which is what the chunk-only stage wants.
            book_id: Tags the Langfuse trace of any LLM classification call.
            prepared: Reuse a prior ``prepare_chapters`` call instead of
                redoing the heading pass.

        Returns:
            Chunks in document order.

        Raises:
            MissingProvenanceError: If a chunk carries no page provenance.
        """
        tokenizer = _tokenizer(self.settings.embedding_model_id, CHUNK_MAX_TOKENS)
        # Docling drops a heading entirely (yields no chunk for it at all)
        # when nothing follows it before the next heading — real for a run of
        # very short chapters. Once dropped, the heading never appears in any
        # chunk's ``meta.headings``, and the cursor below can only step onto
        # headings it sees: skip one and it desyncs from ``ordered_headings``
        # for the rest of the document, misattributing every later chunk to
        # the last chapter it did see. ``always_emit_headings`` makes Docling
        # emit an empty-text chunk for such a heading instead, so it still
        # gets attributed to a chunk.
        chunker = HybridChunker(tokenizer=tokenizer, always_emit_headings=True)
        chunks: list[DocChunk] = cast(
            list[DocChunk], list(chunker.chunk(dl_doc=document))
        )

        contextualized_texts = [chunker.contextualize(chunk) for chunk in chunks]
        embeddings = (
            self.embed_texts(contextualized_texts) if embed else [None] * len(chunks)
        )

        previous_chapter = ChapterInfo(is_chapter=False)
        result_chunks: list[ChunkPayload] = []
        if prepared is None:
            prepared = await self.prepare_chapters(document, book_id=book_id)
        ordered_headings = prepared
        cursor = -1

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            for heading in chunk.meta.headings or []:
                # Advance strictly forward through the document's heading
                # order rather than searching the whole list by text: two
                # chapters that happen to share a title (a repeated "Prologue",
                # a part-title reused per volume) must never re-match an
                # earlier one just because their text is identical.
                while (
                    cursor + 1 < len(ordered_headings)
                    and ordered_headings[cursor + 1][1].text == heading
                ):
                    cursor += 1
                    if ordered_headings[cursor][1].is_chapter:
                        previous_chapter = ordered_headings[cursor][1]

            provenance_list = [
                provenance
                for doc_item in chunk.meta.doc_items
                for provenance in doc_item.prov
            ]
            pages = sorted({provenance.page_no for provenance in provenance_list})

            if not pages:
                raise MissingProvenanceError(
                    f"chunk has no page provenance: {chunk.text[:80]!r}"
                )

            result_chunks.append(
                ChunkPayload(
                    text=chunk.text,
                    text_embedding=embedding,
                    pages=pages,
                    page_start=pages[0],
                    page_end=pages[-1],
                    chapter_number=previous_chapter.number,
                    token_count=tokenizer.count_tokens(chunk.text),
                )
            )

        return result_chunks

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed already-contextualized passages.

        Embeddings are normalised because every cosine-distance query in the
        system assumes unit vectors; un-normalised vectors return wrong
        neighbours rather than an error.

        Args:
            texts: Passages to embed.

        Returns:
            One unit vector per passage.
        """
        if not texts:
            return []

        model = _embedding_model(self.settings.embedding_model_id, self.device)
        vectors = model.encode(
            texts,
            batch_size=self.settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return [vector.tolist() for vector in vectors]

    # Private methods.
    def _artifacts_path(self) -> str | None:
        configured = (
            self.settings.docling_artifacts_dir or self.settings.models_cache_dir
        )

        # An unset or absent cache means Docling downloads on first use; that is
        # correct for a developer machine and fatal in an offline test, which is
        # why MODELS_OFFLINE exists rather than a silent default.
        if configured is None or not Path(configured).exists():
            return None

        return str(configured)

    async def _prepare_chapters(
        self, document: DoclingDocument, *, book_id: str | None = None
    ) -> list[tuple[object, ChapterInfo]]:
        """Return every heading-like item in the document, in document order.

        Every item on a page is inspected, not just the first — a chapter
        heading that opens partway down a page (after a running header or a
        part-title) would otherwise be missed entirely.

        Every heading that regex cannot resolve is classified in as few LLM
        calls as fit the model's context window, not one call per heading —
        against a shared vLLM server that is the difference between seconds
        and minutes on a heading-heavy novel.
        """
        items = []

        for page_no in document.pages:
            for doc_item, _level in document.iterate_items(page_no=page_no):
                if doc_item.label in {
                    DocItemLabel.SECTION_HEADER,
                    DocItemLabel.TITLE,
                }:
                    items.append(doc_item)

        texts = [re.sub(r"\s+", " ", item.text).strip() for item in items]
        results: list[ChapterInfo | None] = [
            self._match_chapter_regex(t) for t in texts
        ]
        ambiguous = [index for index, result in enumerate(results) if result is None]

        if ambiguous:
            classified = await self._classify_headings(
                [texts[index] for index in ambiguous], book_id=book_id
            )
            for index, info in zip(ambiguous, classified, strict=True):
                results[index] = info

        return list(zip(items, cast(list[ChapterInfo], results), strict=True))

    def _match_chapter_regex(self, text: str) -> ChapterInfo | None:
        """Return a regex-matched chapter, or ``None`` if ``text`` needs the LLM."""
        match = CHAPTER_RE.match(text)

        if not match:
            return None

        number = _normalize_chapter_number(match.group("number"))
        title = match.group("title").strip(" :-–—.")

        return ChapterInfo(
            is_chapter=True,
            number=number,
            title=title or None,
            text=text,
            detection_method=DetectionMethod.REGEX,
            confidence=1.0,
        )

    async def _parse_chapter_heading(
        self, text: str, *, book_id: str | None = None
    ) -> ChapterInfo:
        text = re.sub(r"\s+", " ", text).strip()
        matched = self._match_chapter_regex(text)

        if matched is not None:
            return matched

        return await self._classify_chapter_heading(text, book_id=book_id)

    async def _classify_headings(
        self, texts: list[str], *, book_id: str | None = None
    ) -> list[ChapterInfo]:
        """Classify every heading regex could not resolve, batched per call.

        Args:
            texts: Normalised heading strings, in document order.
            book_id: Tags the Langfuse trace of each batch's call.

        Returns:
            One ``ChapterInfo`` per input text, in the same order.
        """
        if not self.llm_classify:
            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

        results: list[ChapterInfo] = []
        for batch in plan_batches(
            texts,
            prompt_tokens=len(_BATCH_HEADING_PROMPT) // 4,
            text_of=lambda text: text,
            max_context=self.settings.llm_max_context,
            output_reserve=self.settings.llm_output_reserve,
        ):
            results.extend(
                await self._classify_heading_batch(batch.items, book_id=book_id)
            )

        return results

    async def _classify_chapter_heading(
        self, text: str, *, book_id: str | None = None
    ) -> ChapterInfo:
        results = await self._classify_heading_batch([text], book_id=book_id)

        return results[0]

    async def _classify_heading_batch(
        self, texts: list[str], *, book_id: str | None = None
    ) -> list[ChapterInfo]:
        if not self.llm_classify:
            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

        prompt = _BATCH_HEADING_PROMPT.format(
            headings="\n".join(f"{i + 1}. {text}" for i, text in enumerate(texts))
        )
        result = await structured_call(
            prompt,
            ChapterBatchStructuredOutput,
            purpose=LLMPurpose.CHAPTER_CLASSIFY,
            book_id=book_id,
            stage="segment_chapters",
        )

        if len(result.items) != len(texts):
            logger.warning(
                "classifier returned %d results for %d headings; discarding batch",
                len(result.items),
                len(texts),
            )

            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

        classified = [
            ChapterInfo(
                is_chapter=True,
                number=item.number,
                title=item.title,
                text=text,
                detection_method=DetectionMethod.LLM,
            )
            if item.is_chapter
            else ChapterInfo(is_chapter=False, text=text)
            for item, text in zip(result.items, texts, strict=True)
        ]

        return classified


_BATCH_HEADING_PROMPT = (
    "You are analyzing headings extracted from a novel to decide, for each "
    "one, whether it marks the start of a new chapter, as opposed to a "
    "sub-heading, running header, or other non-chapter text.\n\n"
    "Rules:\n"
    "- A chapter heading may be a number word or digit alone (e.g. "
    '"One", "3", "IV"), a chapter label with a number (e.g. '
    '"Chapter 3"), a number with a title (e.g. "Three: A New '
    'Beginning"), or a title-only heading used to open a chapter '
    '(e.g. "Prologue", "Epilogue").\n'
    "- `number`: the chapter's numeric identifier, ALWAYS as an "
    "integer. Convert number words and Roman numerals to their "
    'integer value (e.g. "One" -> 1, "IV" -> 4, "XII" -> 12). Use '
    "null if the heading has no number.\n"
    "- `title`: ONLY the descriptive text that accompanies the "
    "number, or null if the heading is nothing more than the "
    "number itself. NEVER repeat the number (spelled out or as a "
    "digit) as the title.\n\n"
    "Examples:\n"
    '"One" -> is_chapter=true, number=1, title=null\n'
    '"Chapter 3" -> is_chapter=true, number=3, title=null\n'
    '"IV" -> is_chapter=true, number=4, title=null\n'
    '"Chapter XII: The Return" -> is_chapter=true, number=12, '
    'title="The Return"\n'
    '"Three: A New Beginning" -> is_chapter=true, number=3, '
    'title="A New Beginning"\n'
    '"Prologue" -> is_chapter=true, number=null, title="Prologue"\n'
    '"Contents" -> is_chapter=false\n'
    '"About the Author" -> is_chapter=false\n\n'
    "Return exactly one classification per heading below, in the same order, "
    "as `items`.\n\n"
    "Headings to classify:\n{headings}"
)
