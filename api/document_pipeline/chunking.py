import re
from pathlib import Path
from typing import cast

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import (
    DoclingDocument,
)
from docling_core.types.doc.labels import DocItemLabel
from langchain.messages import SystemMessage
from langchain_openai import ChatOpenAI
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from ..llm import langfuse_handler, llm
from .constants import CHAPTER_RE, ChapterInfo, ChapterInfoStructuredOutput, Chunk

EMBEDDING_MODEL_ID = "BAAI/bge-m3"
CACHE_DIR = Path("/home/prinzz/main/my-projects/traverse/api/.cache/")
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


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
    # Public methods.
    def load_document(self, document_path: Path) -> DoclingDocument:
        pipeline_options = PdfPipelineOptions(artifacts_path=CACHE_DIR)
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        document = converter.convert(document_path).document

        return document

    def generate_chunks(self, document: DoclingDocument) -> list[Chunk]:
        tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_MODEL_ID), max_tokens=1024
        )
        chunker = HybridChunker(tokenizer=tokenizer)
        chunks: list[DocChunk] = cast(
            list[DocChunk], list(chunker.chunk(dl_doc=document))
        )
        model = SentenceTransformer(EMBEDDING_MODEL_ID, device="cuda")

        contextualized_texts = [chunker.contextualize(chunk) for chunk in chunks]
        embeddings = model.encode(
            contextualized_texts,
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

        previous_chapter = ChapterInfo(is_chapter=False)
        result_chunks = []
        chapters_map = self._prepare_chapters(document)

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            if chunk.meta.headings:
                for heading in chunk.meta.headings:
                    for value in chapters_map.values():
                        if (
                            value[1].text == heading
                            and heading != previous_chapter.text
                        ):
                            previous_chapter = value[1]

            provenance_list = [
                provenance
                for doc_item in chunk.meta.doc_items
                for provenance in doc_item.prov
            ]

            pages = sorted([provenance.page_no for provenance in provenance_list])

            result_chunks.append(
                Chunk(
                    text_embedding=embedding.tolist(),
                    text=chunk.text,
                    pages=pages,
                    page_start=pages[0] if pages else 0,
                    page_end=pages[-1] if pages else 0,
                    chapter=previous_chapter,
                )
            )

        return result_chunks

    # Private methods
    def _prepare_chapters(self, document: DoclingDocument):
        chapters_map = {}

        for page_no in document.pages:
            for count, (doc_item, _level) in enumerate(
                document.iterate_items(page_no=page_no)
            ):
                if count >= 1:
                    break

                if doc_item.label in {
                    DocItemLabel.SECTION_HEADER,
                    DocItemLabel.TITLE,
                }:
                    chapter_info = self._parse_chapter_heading(doc_item.text)
                    chapters_map[doc_item.self_ref] = (doc_item, chapter_info)

        return chapters_map

    def _parse_chapter_heading(self, text: str):
        text = re.sub(r"\s+", " ", text).strip()

        match = CHAPTER_RE.match(text)

        if not match:
            llm_result = self._llm_classify_chapter_heading(llm, text)

            if llm_result.is_chapter:
                return ChapterInfo(**llm_result.model_dump(), text=text)

            return ChapterInfo(is_chapter=False)

        number = _normalize_chapter_number(match.group("number"))
        title = match.group("title").strip(" :-–—.")

        return ChapterInfo(
            is_chapter=True, number=number, title=title or None, text=text
        )

    def _llm_classify_chapter_heading(self, llm: ChatOpenAI, text: str):
        structured_llm = llm.with_structured_output(ChapterInfoStructuredOutput)
        prompt = (
            "You are analyzing a heading extracted from a novel to decide "
            "whether it marks the start of a new chapter, as opposed to a "
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
            f'Heading to classify: "{text}"'
        )

        result = structured_llm.invoke(
            [SystemMessage(prompt)], config={"callbacks": [langfuse_handler]}
        )

        return cast(ChapterInfoStructuredOutput, result)


# if __name__ == "__main__":
#     documentChunker = DocumentChunker()
#     documentChunker.load_document(
#         Path("api/sample_docs/before_the_coffee_gets_cold.pdf")
#     )
