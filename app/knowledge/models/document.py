"""
app/knowledge/models/document.py
──────────────────────────────────
MongoDB document model for knowledge_documents collection.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.models.base import MongoBaseModel, TimestampMixin


class DocumentType(str, Enum):
    PDF      = "pdf"
    DOCX     = "docx"
    TXT      = "txt"
    CSV      = "csv"
    JSON     = "json"
    MARKDOWN = "md"
    URL      = "url"


class DocumentStatus(str, Enum):
    PENDING    = "pending"     # uploaded, not yet processed
    PROCESSING = "processing"  # pipeline in progress
    COMPLETED  = "completed"   # fully indexed in ChromaDB
    FAILED     = "failed"      # pipeline errored


class KnowledgeDocument(MongoBaseModel, TimestampMixin):
    """
    Metadata record for an uploaded knowledge base document.
    Stored in MongoDB `knowledge_documents` collection.
    """

    document_id:   str                         # KBD-YYYYMMDD-XXXXXXXX
    filename:      str
    original_name: str                         # original uploaded filename
    file_path:     Optional[str]  = None       # local/remote path of stored file
    source_url:    Optional[str]  = None       # for URL-sourced documents
    doc_type:      DocumentType
    category:      str            = "general"
    status:        DocumentStatus = DocumentStatus.PENDING
    file_size:     Optional[int]  = None       # bytes

    # Processing stats — filled after pipeline completes
    total_chunks:      int = 0
    embedded_chunks:   int = 0
    total_chars:       int = 0
    processing_error:  Optional[str] = None

    # Ownership / audit
    uploaded_by:    str                        # user _id
    uploaded_at:    Optional[datetime] = None

    # Optional user-supplied metadata
    description:    Optional[str] = None
    tags:           list[str]     = Field(default_factory=list)
