"""
app/knowledge/models/chunk.py
──────────────────────────────
MongoDB document model for knowledge_chunks collection.
Each chunk represents a text segment with full metadata
ready for embedding and ChromaDB storage.
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models.base import MongoBaseModel, TimestampMixin


class KnowledgeChunk(MongoBaseModel, TimestampMixin):
    """
    A single text chunk derived from a knowledge document.
    Stored in MongoDB `knowledge_chunks` collection.
    The embedding vector itself lives in ChromaDB.
    """

    chunk_id:       str            # CHK-YYYYMMDD-XXXXXXXX (also used as ChromaDB ID)
    document_id:    str            # parent KnowledgeDocument.document_id
    chunk_index:    int            # 0-based position within the document
    content:        str            # cleaned text content of this chunk
    char_count:     int

    # Metadata attached to every chunk for RAG retrieval later
    filename:       str
    original_name:  str
    source:         str            # file path or URL
    category:       str
    page_number:    Optional[int]  = None
    uploaded_by:    str
    uploaded_at:    Optional[datetime] = None

    # Embedding status
    is_embedded:    bool = False
    embedding_model: Optional[str] = None   # e.g. "models/text-embedding-004"
