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

from ..config.settings import Settings
from ..config.settings import settings as default_settings
from ..contracts.enums import DetectionMethod
from ..contracts.llm import BatchPlan, TokenBudget
from ..contracts.pipeline import ChapterInfo, ChunkPayload
from .constants import CHAPTER_RE, CHUNK_MAX_TOKENS, ROMAN_VALUES
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

    def detect_chapters(self, document: DoclingDocument) -> list[ChapterInfo]:
        """Return the chapter headings found in a document, in document order.

        Args:
            document: A converted document.

        Returns:
            One entry per detected chapter heading.
        """
        chapters = [
            info for _item, info in self._prepare_chapters(document) if info.is_chapter
        ]

        return chapters

    def generate_chunks(
        self, document: DoclingDocument, *, embed: bool = True
    ) -> list[ChunkPayload]:
        """Split a document into persistable chunks carrying page provenance.

        Chunks inherit the most recently seen chapter heading, so a mid-chapter
        chunk with no heading of its own still knows which chapter it is in.

        Args:
            document: A converted document.
            embed: Whether to compute embeddings. ``False`` skips loading
                BGE-M3 entirely, which is what the chunk-only stage wants.

        Returns:
            Chunks in document order.

        Raises:
            MissingProvenanceError: If a chunk carries no page provenance.
        """
        tokenizer = _tokenizer(self.settings.embedding_model_id, CHUNK_MAX_TOKENS)
        chunker = HybridChunker(tokenizer=tokenizer)
        chunks: list[DocChunk] = cast(
            list[DocChunk], list(chunker.chunk(dl_doc=document))
        )

        contextualized_texts = [chunker.contextualize(chunk) for chunk in chunks]
        embeddings = (
            self.embed_texts(contextualized_texts) if embed else [None] * len(chunks)
        )

        previous_chapter = ChapterInfo(is_chapter=False)
        result_chunks: list[ChunkPayload] = []
        ordered_headings = self._prepare_chapters(document)
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

    def _prepare_chapters(
        self, document: DoclingDocument
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
            classified = self._classify_headings([texts[index] for index in ambiguous])
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

    def _parse_chapter_heading(self, text: str) -> ChapterInfo:
        text = re.sub(r"\s+", " ", text).strip()
        matched = self._match_chapter_regex(text)

        if matched is not None:
            return matched

        return self._classify_chapter_heading(text)

    def _classify_headings(self, texts: list[str]) -> list[ChapterInfo]:
        """Classify every heading regex could not resolve, batched per call.

        Args:
            texts: Normalised heading strings, in document order.

        Returns:
            One ``ChapterInfo`` per input text, in the same order.
        """
        if not self.llm_classify:
            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

        results: list[ChapterInfo] = []
        for batch in _plan_heading_batches(
            texts,
            max_context=self.settings.llm_max_context,
            output_reserve=self.settings.llm_output_reserve,
        ):
            results.extend(self._classify_heading_batch(batch.items))

        return results

    def _classify_chapter_heading(self, text: str) -> ChapterInfo:
        results = self._classify_heading_batch([text])

        return results[0]

    def _classify_heading_batch(self, texts: list[str]) -> list[ChapterInfo]:
        if not self.llm_classify:
            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

        # Imported here, not at module scope: importing ``api.llm`` constructs a
        # client and a Langfuse handler, and the chunker must stay importable in
        # a test process that has neither.
        #
        # This calls the Sprint 1 ``api/llm.py`` prototype directly rather than
        # be2's ``api.llm.structured_call`` (S2.7) — the latter did not exist
        # yet in this worktree when this landed. Swapping the two lines below
        # for the real helper once it does should not need anything else here
        # to change; see plans/sprint-2/HANDOFF.md.
        from langchain.messages import SystemMessage

        from ..llm import langfuse_handler, llm
        from .constants import ChapterBatchStructuredOutput

        structured_llm = llm.with_structured_output(ChapterBatchStructuredOutput)
        callbacks = [langfuse_handler] if langfuse_handler else []
        prompt = _BATCH_HEADING_PROMPT.format(
            headings="\n".join(f"{i + 1}. {text}" for i, text in enumerate(texts))
        )

        try:
            result = cast(
                ChapterBatchStructuredOutput,
                structured_llm.invoke(
                    [SystemMessage(prompt)], config={"callbacks": callbacks}
                ),
            )
        except Exception:
            logger.warning(
                "batched heading classification failed for %d headings",
                len(texts),
                exc_info=True,
            )

            return [ChapterInfo(is_chapter=False, text=text) for text in texts]

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


def _plan_heading_batches(
    texts: list[str], *, max_context: int, output_reserve: int
) -> list[BatchPlan[str]]:
    """Group headings into as few LLM calls as fit the model's context window.

    A stopgap ahead of be2's ``api.llm.plan_batches`` (S2.7), against the
    frozen ``TokenBudget``/``BatchPlan`` contracts rather than an invented
    shape — swap this call site for the real helper once it lands (see
    ``plans/sprint-2/HANDOFF.md``). Sized with a chars/4 estimate rather than
    the model's own tokenizer: acceptable here only because a heading is a
    handful of words and the failure mode of underestimating is an extra call,
    not a truncated prompt.

    Args:
        texts: Headings needing classification, in document order.
        max_context: The model's context window, in tokens.
        output_reserve: Tokens held back for the response.

    Returns:
        Batches covering every heading exactly once, none split (a heading is
        never too large to fit alone).
    """
    if not texts:
        return []

    budget = TokenBudget(
        max_context=max_context,
        prompt_tokens=len(_BATCH_HEADING_PROMPT) // 4,
        output_reserve=output_reserve,
    )
    item_budget = max(1, budget.item_budget)

    batches: list[BatchPlan[str]] = []
    current: list[str] = []
    current_tokens = 0

    for text in texts:
        text_tokens = max(1, len(text) // 4)

        if current and current_tokens + text_tokens > item_budget:
            batches.append(BatchPlan(items=current, token_count=current_tokens))
            current, current_tokens = [], 0

        current.append(text)
        current_tokens += text_tokens

    if current:
        batches.append(BatchPlan(items=current, token_count=current_tokens))

    return batches
