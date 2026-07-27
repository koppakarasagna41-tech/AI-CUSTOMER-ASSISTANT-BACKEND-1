"""app/knowledge/schemas/chunk.py"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChunkOut(BaseModel):
    id:              str
    chunk_id:        str
    document_id:     str
    chunk_index:     int
    content:         str
    char_count:      int
    filename:        str
    category:        str
    page_number:     Optional[int]     = None
    is_embedded:     bool              = False
    embedding_model: Optional[str]     = None
    created_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
