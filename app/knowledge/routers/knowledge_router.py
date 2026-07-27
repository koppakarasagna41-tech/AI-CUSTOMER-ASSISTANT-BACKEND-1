"""
app/knowledge/routers/knowledge_router.py
───────────────────────────────────────────
Knowledge Base Management API endpoints.

All write operations (upload, update, delete) require admin role.
Read operations require any authenticated user.

Routes:
  POST   /knowledge/upload          — upload file or URL
  GET    /knowledge                 — list documents (paginated + filtered)
  GET    /knowledge/categories      — distinct categories list
  GET    /knowledge/search          — keyword search across documents
  GET    /knowledge/{id}            — get single document
  PUT    /knowledge/{id}            — update metadata
  DELETE /knowledge/{id}            — delete document + chunks + vectors
  GET    /knowledge/{id}/chunks     — list chunks of a document
"""

import logging
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException,
    Query, UploadFile, status,
)
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, HttpUrl

from app.core.auth_deps  import get_current_user, require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import KnowledgeDocumentsCollection, KnowledgeChunksCollection
from app.knowledge.models.document  import DocumentStatus, DocumentType
from app.knowledge.schemas.document import (
    DocumentOut, DocumentListOut, DocumentUpdate, DocumentUploadResponse,
)
from app.knowledge.schemas.chunk    import ChunkOut
from app.knowledge.services         import mongo_service, upload_service
from app.knowledge.vector_store     import delete_by_document_id, get_collection_count
from app.utils.helpers              import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


# ── Helper ────────────────────────────────────────────────────

def _to_document_out(doc: dict) -> dict:
    doc.setdefault("id", doc.get("_id", ""))
    return DocumentOut(**{**doc, "id": doc.get("_id", doc.get("id", ""))}).model_dump()


def _to_list_out(doc: dict) -> dict:
    return DocumentListOut(**{**doc, "id": doc.get("_id", doc.get("id", ""))}).model_dump()


# ── Upload (file) ─────────────────────────────────────────────

@router.post(
    "/upload",
    status_code=201,
    summary="Upload a knowledge document (admin only)",
)
async def upload_document(
    file:        UploadFile    = File(..., description="PDF, DOCX, TXT, CSV, JSON, or MD"),
    category:    str           = Form("general"),
    description: Optional[str] = Form(None),
    tags:        str           = Form("",     description="Comma-separated tags"),
    current_user: dict         = Depends(require_admin),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
    chunks_col:   AsyncIOMotorCollection = Depends(KnowledgeChunksCollection),
):
    """
    Upload and process a document into the knowledge base.

    Processing runs asynchronously — the document record is created
    immediately with status=`pending`, and the pipeline runs in the background.
    Poll `GET /knowledge/{id}` to check when status becomes `completed`.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        doc = await upload_service.handle_file_upload(
            file=file,
            category=category.strip(),
            description=description,
            tags=tag_list,
            uploaded_by=current_user.get("_id", ""),
            docs_col=docs_col,
            chunks_col=chunks_col,
        )
    except ValueError as exc:
        raise BadRequestError(message=str(exc), error_code="UPLOAD_INVALID")

    return success_response(
        data=DocumentUploadResponse(
            document_id=doc["document_id"],
            filename=doc["filename"],
            doc_type=doc["doc_type"],
            category=doc["category"],
            status=DocumentStatus(doc["status"]),
            message="Document uploaded. Processing started in the background.",
        ).model_dump(),
        message="Upload accepted.",
    )


# ── Upload (URL) ──────────────────────────────────────────────

class UrlUploadRequest(BaseModel):
    url:         str
    category:    str           = "general"
    description: Optional[str] = None
    tags:        list[str]     = []


@router.post(
    "/upload/url",
    status_code=201,
    summary="Ingest a website URL into the knowledge base (admin only)",
)
async def upload_url(
    payload:      UrlUploadRequest,
    current_user: dict = Depends(require_admin),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
    chunks_col:   AsyncIOMotorCollection = Depends(KnowledgeChunksCollection),
):
    """Fetch and process a web page URL into the knowledge base."""
    try:
        doc = await upload_service.handle_url_upload(
            url=payload.url,
            category=payload.category.strip(),
            description=payload.description,
            tags=payload.tags,
            uploaded_by=current_user.get("_id", ""),
            docs_col=docs_col,
            chunks_col=chunks_col,
        )
    except ValueError as exc:
        raise BadRequestError(message=str(exc), error_code="URL_UPLOAD_INVALID")

    return success_response(
        data=DocumentUploadResponse(
            document_id=doc["document_id"],
            filename=doc["filename"],
            doc_type=doc["doc_type"],
            category=doc["category"],
            status=DocumentStatus(doc["status"]),
            message="URL ingestion started in the background.",
        ).model_dump(),
        message="URL accepted.",
    )


# ── List documents ────────────────────────────────────────────

@router.get(
    "",
    summary="List knowledge documents",
)
async def list_documents(
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(20,   ge=1, le=100),
    category:     Optional[str] = Query(None),
    status:       Optional[str] = Query(None),
    doc_type:     Optional[str] = Query(None),
    search:       Optional[str] = Query(None, description="Search filename or description"),
    current_user: dict          = Depends(get_current_user),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
):
    skip         = (page - 1) * page_size
    docs, total  = await mongo_service.list_documents(
        docs_col,
        skip=skip, limit=page_size,
        category=category, status=status,
        doc_type=doc_type, search=search,
    )
    items = [_to_list_out(d) for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Documents retrieved.",
    )


# ── Categories ────────────────────────────────────────────────

@router.get(
    "/categories",
    summary="Get all distinct knowledge base categories",
)
async def get_categories(
    current_user: dict = Depends(get_current_user),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
):
    cats = await mongo_service.get_categories(docs_col)
    return success_response(data=cats, message="Categories retrieved.")


# ── Search (keyword) ──────────────────────────────────────────

@router.get(
    "/search",
    summary="Keyword search across knowledge documents",
)
async def search_documents(
    q:            str           = Query(..., min_length=2, description="Search query"),
    category:     Optional[str] = Query(None),
    page:         int           = Query(1,   ge=1),
    page_size:    int           = Query(20,  ge=1, le=100),
    current_user: dict          = Depends(get_current_user),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
):
    skip        = (page - 1) * page_size
    docs, total = await mongo_service.list_documents(
        docs_col,
        skip=skip, limit=page_size,
        category=category, search=q,
    )
    items = [_to_list_out(d) for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message=f"Search results for '{q}'.",
    )


# ── Get single document ───────────────────────────────────────

@router.get(
    "/{document_id}",
    summary="Get knowledge document by document_id",
)
async def get_document(
    document_id:  str,
    current_user: dict = Depends(get_current_user),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
):
    doc = await mongo_service.get_document_by_doc_id(docs_col, document_id)
    if not doc:
        raise NotFoundError(
            f"Document '{document_id}' not found.",
            error_code="KB_NOT_FOUND",
        )
    return success_response(data=_to_document_out(doc), message="Document retrieved.")


# ── Update document metadata ──────────────────────────────────

@router.put(
    "/{document_id}",
    summary="Update knowledge document metadata (admin only)",
)
async def update_document(
    document_id:  str,
    payload:      DocumentUpdate,
    current_user: dict = Depends(require_admin),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
):
    doc = await mongo_service.get_document_by_doc_id(docs_col, document_id)
    if not doc:
        raise NotFoundError(
            f"Document '{document_id}' not found.",
            error_code="KB_NOT_FOUND",
        )

    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise BadRequestError(
            "No update fields provided.", error_code="NO_FIELDS"
        )

    await mongo_service.update_document_record(docs_col, document_id, patch)
    updated = await mongo_service.get_document_by_doc_id(docs_col, document_id)
    return success_response(data=_to_document_out(updated), message="Document updated.")


# ── Delete document ───────────────────────────────────────────

@router.delete(
    "/{document_id}",
    summary="Delete knowledge document + its chunks + vectors (admin only)",
)
async def delete_document(
    document_id:  str,
    current_user: dict = Depends(require_admin),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
    chunks_col:   AsyncIOMotorCollection = Depends(KnowledgeChunksCollection),
):
    doc = await mongo_service.get_document_by_doc_id(docs_col, document_id)
    if not doc:
        raise NotFoundError(
            f"Document '{document_id}' not found.",
            error_code="KB_NOT_FOUND",
        )

    # 1. Delete MongoDB chunks
    deleted_chunks = await mongo_service.delete_chunks_by_document_id(
        chunks_col, document_id
    )

    # 2. Delete ChromaDB vectors
    deleted_vectors = await delete_by_document_id(document_id)

    # 3. Delete MongoDB document record
    await mongo_service.delete_document_record(docs_col, document_id)

    logger.info(
        "Document deleted | id=%s chunks=%d vectors=%d",
        document_id, deleted_chunks, deleted_vectors,
    )

    return success_response(
        data={
            "document_id":     document_id,
            "deleted_chunks":  deleted_chunks,
            "deleted_vectors": deleted_vectors,
        },
        message="Document and all associated data deleted.",
    )


# ── List chunks of a document ─────────────────────────────────

@router.get(
    "/{document_id}/chunks",
    summary="List chunks of a knowledge document",
)
async def list_chunks(
    document_id:  str,
    page:         int = Query(1,   ge=1),
    page_size:    int = Query(50,  ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    docs_col:     AsyncIOMotorCollection = Depends(KnowledgeDocumentsCollection),
    chunks_col:   AsyncIOMotorCollection = Depends(KnowledgeChunksCollection),
):
    doc = await mongo_service.get_document_by_doc_id(docs_col, document_id)
    if not doc:
        raise NotFoundError(
            f"Document '{document_id}' not found.",
            error_code="KB_NOT_FOUND",
        )

    skip           = (page - 1) * page_size
    chunks, total  = await mongo_service.get_chunks_by_document_id(
        chunks_col, document_id, skip=skip, limit=page_size,
    )
    items = [
        ChunkOut(**{**c, "id": c.get("_id", "")}).model_dump()
        for c in chunks
    ]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Chunks retrieved.",
    )
