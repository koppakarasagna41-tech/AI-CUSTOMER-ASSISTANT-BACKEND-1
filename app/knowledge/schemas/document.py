"""app/knowledge/schemas/document.py — Request/response schemas for knowledge documents."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.models.document import DocumentStatus, DocumentType


class DocumentOut(BaseModel):
    """Full document record returned from API responses."""
    id:              str
    document_id:     str
    filename:        str
    original_name:   str
    doc_type:        DocumentType
    category:        str
    status:          DocumentStatus
    file_size:       Optional[int]        = None
    total_chunks:    int                  = 0
    embedded_chunks: int                  = 0
    total_chars:     int                  = 0
    description:     Optional[str]        = None
    tags:            list[str]            = []
    uploaded_by:     str
    uploaded_at:     Optional[datetime]   = None
    processing_error: Optional[str]       = None
    created_at:      Optional[datetime]   = None
    updated_at:      Optional[datetime]   = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentListOut(BaseModel):
    """Minimal document record for list views."""
    id:              str
    document_id:     str
    original_name:   str
    doc_type:        DocumentType
    category:        str
    status:          DocumentStatus
    total_chunks:    int            = 0
    embedded_chunks: int            = 0
    uploaded_by:     str
    uploaded_at:     Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentUploadResponse(BaseModel):
    """Returned immediately after file upload (pipeline runs async)."""
    document_id:   str
    filename:      str
    doc_type:      str
    category:      str
    status:        DocumentStatus
    message:       str


class DocumentUpdate(BaseModel):
    """Fields that can be patched on an existing document."""
    category:    Optional[str]      = Field(None, max_length=100)
    description: Optional[str]      = Field(None, max_length=500)
    tags:        Optional[list[str]] = None


class DocumentSearchParams(BaseModel):
    """Query parameters for GET /knowledge"""
    category:    Optional[str] = None
    status:      Optional[DocumentStatus] = None
    doc_type:    Optional[DocumentType]   = None
    search:      Optional[str] = None     # searches filename + description
