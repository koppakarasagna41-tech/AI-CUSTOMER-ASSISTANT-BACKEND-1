"""
app/knowledge/services/upload_service.py
──────────────────────────────────────────
Document Upload Pipeline Orchestrator.

Full pipeline for every uploaded document:

  1.  Validate file type & size
  2.  Save original file to disk
  3.  Create MongoDB document record (status=PENDING)
  4.  Select correct parser (PDF / DOCX / TXT / CSV / JSON / MD / URL)
  5.  Extract text  →  list[ParsedPage]
  6.  Clean & chunk →  list[TextChunk]
  7.  Save chunks   →  MongoDB knowledge_chunks
  8.  Generate embeddings  (Gemini text-embedding-004)
  9.  Upsert vectors       (ChromaDB)
  10. Mark chunks embedded (MongoDB)
  11. Update document record  status=COMPLETED  +  stats
  12. On any failure: status=FAILED + error message

The pipeline runs in a background asyncio task so the HTTP response
returns immediately after step 3 (non-blocking upload UX).
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorCollection

from app.config   import settings
from app.utils.helpers import utc_now

from app.knowledge.models.document    import DocumentStatus, DocumentType
from app.knowledge.utils.id_generator import generate_document_id
from app.knowledge.parsers            import (
    PdfParser, DocxParser, TxtParser, CsvParser, UrlLoader, ParsedPage,
)
from app.knowledge.chunking.chunking_service import chunk_document
from app.knowledge.embeddings.embedding_service import (
    embed_texts, is_embedding_configured, EmbeddingError,
)
from app.knowledge.vector_store.chroma_service import upsert_chunks as chroma_upsert
from app.knowledge.services.mongo_service import (
    create_knowledge_document,
    update_document_status,
    save_chunks,
    mark_chunks_embedded,
    delete_chunks_by_document_id,
    delete_document_record,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────
_EXT_TO_DOC_TYPE = {
    "pdf":  DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "txt":  DocumentType.TXT,
    "csv":  DocumentType.CSV,
    "json": DocumentType.JSON,
    "md":   DocumentType.MARKDOWN,
}
_ALLOWED_EXTS = set(settings.KB_ALLOWED_EXTENSIONS.split(","))
_MAX_BYTES    = settings.KB_MAX_FILE_SIZE_MB * 1024 * 1024

# ── Embedding batch size ──────────────────────────────────────
_EMBED_BATCH  = 20   # embed this many chunks per API call


# ── Public API ────────────────────────────────────────────────

async def handle_file_upload(
    *,
    file:         UploadFile,
    category:     str,
    description:  Optional[str],
    tags:         list[str],
    uploaded_by:  str,
    docs_col:     AsyncIOMotorCollection,
    chunks_col:   AsyncIOMotorCollection,
) -> dict:
    """
    Entry point for POST /knowledge/upload.

    Validates, saves, creates the DB record, then fires the
    processing pipeline in the background.

    Returns the document metadata dict (status=PENDING).
    """
    # ── Validate ──────────────────────────────────────────────
    ext = _get_extension(file.filename or "")
    _validate_extension(ext)

    content = await file.read()
    _validate_size(len(content), file.filename)

    # ── Persist file ──────────────────────────────────────────
    document_id = generate_document_id()
    saved_path  = _save_file(content, document_id, file.filename or "upload")
    filename    = Path(saved_path).name

    # ── MongoDB record ────────────────────────────────────────
    now     = utc_now()
    doc_rec = {
        "document_id":   document_id,
        "filename":      filename,
        "original_name": file.filename or filename,
        "file_path":     saved_path,
        "source_url":    None,
        "doc_type":      _EXT_TO_DOC_TYPE.get(ext, DocumentType.TXT).value,
        "category":      category,
        "status":        DocumentStatus.PENDING.value,
        "file_size":     len(content),
        "total_chunks":  0,
        "embedded_chunks": 0,
        "total_chars":   0,
        "processing_error": None,
        "uploaded_by":   uploaded_by,
        "uploaded_at":   now,
        "description":   description,
        "tags":          tags,
        "created_at":    now,
        "updated_at":    now,
    }
    inserted_id = await create_knowledge_document(docs_col, doc_rec)
    doc_rec["_id"] = inserted_id

    logger.info(
        "Document uploaded | id=%s file=%s category=%s size=%d bytes",
        document_id, file.filename, category, len(content),
    )

    # ── Fire pipeline in background ───────────────────────────
    asyncio.create_task(
        _run_pipeline(
            document_id=document_id,
            file_path=saved_path,
            doc_type=_EXT_TO_DOC_TYPE.get(ext, DocumentType.TXT),
            category=category,
            original_name=file.filename or filename,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            docs_col=docs_col,
            chunks_col=chunks_col,
        )
    )

    return doc_rec


async def handle_url_upload(
    *,
    url:          str,
    category:     str,
    description:  Optional[str],
    tags:         list[str],
    uploaded_by:  str,
    docs_col:     AsyncIOMotorCollection,
    chunks_col:   AsyncIOMotorCollection,
) -> dict:
    """
    Entry point for URL-based document ingestion.
    Same pipeline — no file saved to disk.
    """
    document_id = generate_document_id()
    filename    = f"url_{document_id}.html"
    now         = utc_now()

    doc_rec = {
        "document_id":   document_id,
        "filename":      filename,
        "original_name": url,
        "file_path":     None,
        "source_url":    url,
        "doc_type":      DocumentType.URL.value,
        "category":      category,
        "status":        DocumentStatus.PENDING.value,
        "file_size":     None,
        "total_chunks":  0,
        "embedded_chunks": 0,
        "total_chars":   0,
        "processing_error": None,
        "uploaded_by":   uploaded_by,
        "uploaded_at":   now,
        "description":   description,
        "tags":          tags,
        "created_at":    now,
        "updated_at":    now,
    }
    inserted_id = await create_knowledge_document(docs_col, doc_rec)
    doc_rec["_id"] = inserted_id

    asyncio.create_task(
        _run_url_pipeline(
            document_id=document_id,
            url=url,
            category=category,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            docs_col=docs_col,
            chunks_col=chunks_col,
        )
    )
    return doc_rec


# ── Pipeline internals ────────────────────────────────────────

async def _run_pipeline(
    *,
    document_id:   str,
    file_path:     str,
    doc_type:      DocumentType,
    category:      str,
    original_name: str,
    uploaded_by:   str,
    uploaded_at:   datetime,
    docs_col:      AsyncIOMotorCollection,
    chunks_col:    AsyncIOMotorCollection,
) -> None:
    """Background task: parse → clean → chunk → embed → store."""
    try:
        await update_document_status(docs_col, document_id, DocumentStatus.PROCESSING)

        # 1. Parse
        loop  = asyncio.get_event_loop()
        pages = await loop.run_in_executor(
            None, lambda: _parse_file(file_path, doc_type)
        )

        await _process_pages(
            pages=pages,
            document_id=document_id,
            filename=Path(file_path).name,
            original_name=original_name,
            source=file_path,
            category=category,
            uploaded_by=uploaded_by,
            uploaded_at=uploaded_at,
            docs_col=docs_col,
            chunks_col=chunks_col,
        )

    except Exception as exc:
        logger.error("Pipeline failed | document_id=%s | %s", document_id, exc)
        await update_document_status(
            docs_col, document_id, DocumentStatus.FAILED,
            error=str(exc)[:500],
        )


async def _run_url_pipeline(
    *,
    document_id: str,
    url:         str,
    category:    str,
    uploaded_by: str,
    uploaded_at: datetime,
    docs_col:    AsyncIOMotorCollection,
    chunks_col:  AsyncIOMotorCollection,
) -> None:
    try:
        await update_document_status(docs_col, document_id, DocumentStatus.PROCESSING)

        loader = UrlLoader(timeout=settings.GEMINI_TIMEOUT)
        pages  = await loader.load(url)

        await _process_pages(
            pages=pages,
            document_id=document_id,
            filename=f"url_{document_id}",
            original_name=url,
            source=url,
            category=category,
            uploaded_by=uploaded_by,
            uploaded_at=uploaded_at,
            docs_col=docs_col,
            chunks_col=chunks_col,
        )

    except Exception as exc:
        logger.error("URL pipeline failed | %s | %s", url, exc)
        await update_document_status(
            docs_col, document_id, DocumentStatus.FAILED,
            error=str(exc)[:500],
        )


async def _process_pages(
    *,
    pages:         list[ParsedPage],
    document_id:   str,
    filename:      str,
    original_name: str,
    source:        str,
    category:      str,
    uploaded_by:   str,
    uploaded_at:   datetime,
    docs_col:      AsyncIOMotorCollection,
    chunks_col:    AsyncIOMotorCollection,
) -> None:
    """Shared chunk→embed→store logic for both file and URL pipelines."""

    # 2. Chunk
    chunks = chunk_document(
        pages=pages,
        document_id=document_id,
        filename=filename,
        original_name=original_name,
        source=source,
        category=category,
        uploaded_by=uploaded_by,
        uploaded_at=uploaded_at,
    )

    if not chunks:
        await update_document_status(
            docs_col, document_id, DocumentStatus.FAILED,
            error="No usable text could be extracted from this document.",
        )
        return

    total_chars = sum(c.char_count for c in chunks)

    # 3. Save chunks to MongoDB
    await save_chunks(chunks_col, chunks)

    # 4. Update doc with chunk count
    await update_document_status(
        docs_col, document_id, DocumentStatus.PROCESSING,
        extra={"total_chunks": len(chunks), "total_chars": total_chars},
    )

    # 5. Embed + store in ChromaDB
    embedded_count = 0

    if is_embedding_configured():
        embedded_count = await _embed_and_store(chunks, chunks_col)
    else:
        logger.warning(
            "GEMINI_API_KEY not set — skipping embeddings for document %s",
            document_id,
        )

    # 6. Mark document COMPLETED
    await update_document_status(
        docs_col, document_id, DocumentStatus.COMPLETED,
        extra={
            "total_chunks":    len(chunks),
            "embedded_chunks": embedded_count,
            "total_chars":     total_chars,
        },
    )
    logger.info(
        "Pipeline complete | document_id=%s chunks=%d embedded=%d chars=%d",
        document_id, len(chunks), embedded_count, total_chars,
    )


async def _embed_and_store(chunks, chunks_col) -> int:
    """Embed chunks in batches and upsert to ChromaDB. Returns embedded count."""
    embedded_count = 0
    model_name     = settings.GEMINI_EMBEDDING_MODEL

    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[i : i + _EMBED_BATCH]
        texts = [c.content for c in batch]

        try:
            vectors = await embed_texts(texts, task_type="retrieval_document")

            # Build ChromaDB payload
            ids       = [c.chunk_id for c in batch]
            docs_text = texts
            metas     = [
                {
                    "document_id":  c.document_id,
                    "filename":     c.filename,
                    "original_name": c.original_name,
                    "source":       c.source,
                    "category":     c.category,
                    "page_number":  c.page_number or 0,
                    "uploaded_by":  c.uploaded_by,
                    "chunk_index":  c.chunk_index,
                }
                for c in batch
            ]

            await chroma_upsert(
                chunk_ids=ids,
                embeddings=vectors,
                documents=docs_text,
                metadatas=metas,
            )

            await mark_chunks_embedded(
                chunks_col,
                [c.chunk_id for c in batch],
                model_name,
            )
            embedded_count += len(batch)
            logger.debug("Embedded batch %d-%d", i, i + len(batch))

        except EmbeddingError as exc:
            logger.warning(
                "Embedding batch %d failed (non-fatal): %s", i, exc.message
            )

    return embedded_count


# ── File helpers ──────────────────────────────────────────────

def _get_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def _validate_extension(ext: str) -> None:
    if ext not in _ALLOWED_EXTS:
        raise ValueError(
            f"File type '.{ext}' is not supported. "
            f"Allowed: {', '.join(sorted(_ALLOWED_EXTS))}"
        )


def _validate_size(size: int, filename: str) -> None:
    if size > _MAX_BYTES:
        raise ValueError(
            f"File '{filename}' is {size // (1024*1024)}MB, "
            f"exceeds the {settings.KB_MAX_FILE_SIZE_MB}MB limit."
        )


def _save_file(content: bytes, document_id: str, original_name: str) -> str:
    """Save raw bytes to the uploads directory. Returns absolute path."""
    upload_dir = Path(settings.KB_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext      = Path(original_name).suffix.lower()
    filename = f"{document_id}{ext}"
    dest     = upload_dir / filename
    dest.write_bytes(content)
    return str(dest.resolve())


def _parse_file(file_path: str, doc_type: DocumentType) -> list[ParsedPage]:
    """Select the correct parser and extract pages."""
    parser_map = {
        DocumentType.PDF:      PdfParser(),
        DocumentType.DOCX:     DocxParser(),
        DocumentType.TXT:      TxtParser(),
        DocumentType.CSV:      CsvParser(),
        DocumentType.JSON:     TxtParser(),      # JSON FAQ uses TxtParser
        DocumentType.MARKDOWN: TxtParser(),
    }
    parser = parser_map.get(doc_type)
    if parser is None:
        raise ValueError(f"No parser available for doc_type: {doc_type}")
    return parser.parse(file_path)
