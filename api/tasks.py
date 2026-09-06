import asyncio
import logging
from io import BytesIO
from pathlib import Path
from typing import cast

from celery import Celery
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.utils.model_downloader import download_models
from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from sentence_transformers import SentenceTransformer
from sqlmodel import insert
from transformers import AutoTokenizer

from .db.engine import session_context
from .db.models.document_model import Document, DocumentChunk

celery_app = Celery(
    "tasks", broker="pyamqp://user:password@localhost:5672//", backend="rpc://"
)


logger = logging.getLogger(__name__)


@celery_app.task
def embed_file(file: bytes):
    return asyncio.run(async_embed_file(file))


async def async_embed_file(file: bytes):
    EMBEDDING_MODEL_ID = "BAAI/bge-m3"
    CACHE_DIR = Path("/home/prinzz/main/my-projects/traverse/api/.cache/")

    download_models(output_dir=CACHE_DIR)

    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_MODEL_ID), max_tokens=1024
    )
    bytes_io = BytesIO(file)
    doc_stream = DocumentStream(name="document.pdf", stream=bytes_io)
    pipeline_options = PdfPipelineOptions(artifacts_path=CACHE_DIR)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    document = converter.convert(doc_stream).document
    chunker = HybridChunker(tokenizer=tokenizer)
    chunks: list[DocChunk] = cast(list[DocChunk], list(chunker.chunk(dl_doc=document)))

    model = SentenceTransformer(EMBEDDING_MODEL_ID, device="cuda")
    texts = [chunker.contextualize(chunk=chunk) for chunk in chunks]
    vectors = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    records = []
    async with session_context() as session:
        doc = Document(name="Random")
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

    for chunk, vector in zip(chunks, vectors, strict=False):
        prov = [p for it in chunk.meta.doc_items for p in it.prov]
        pages = sorted({p.page_no for p in prov})
        records.append(
            {
                "text": chunk.text,
                "headings": chunk.meta.headings,
                "pages": pages,
                "page_start": pages[0] if pages else None,
                "page_end": pages[-1] if pages else None,
                "text_embedding": vector,
                "document_id": doc.id,
            }
        )

    async with session_context() as session:
        await session.exec(insert(DocumentChunk).values(records))
        await session.commit()

    return
