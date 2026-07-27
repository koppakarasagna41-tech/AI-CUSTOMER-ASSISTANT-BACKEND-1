"""
app/models/base.py
───────────────────
Shared base classes for all MongoDB document models.

PyObjectId
  Bridges BSON ObjectId ↔ Pydantic v2.  Annotated type that serialises
  to a plain string in JSON responses while storing as ObjectId in Mongo.

MongoBaseModel
  Base Pydantic model for all documents.  Uses `id` as alias for `_id`
  so FastAPI serialises the field correctly without exposing the BSON
  underscore prefix.

TimestampMixin
  Adds created_at / updated_at fields automatically populated by the
  service layer (not by Pydantic defaults — that keeps tests deterministic).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import core_schema


# ── PyObjectId ────────────────────────────────────────────────

class PyObjectId(str):
    """
    Custom type that accepts a MongoDB ObjectId (or its string form)
    and serialises to a plain string.

    Pydantic v2 custom type via __get_pydantic_core_schema__.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    @classmethod
    def _validate(cls, value: Any) -> "PyObjectId":
        if isinstance(value, ObjectId):
            return cls(str(value))
        if isinstance(value, str) and ObjectId.is_valid(value):
            return cls(value)
        raise ValueError(f"Invalid ObjectId: {value!r}")

    def to_object_id(self) -> ObjectId:
        """Convert back to a BSON ObjectId for Motor queries."""
        return ObjectId(self)


# ── MongoBaseModel ────────────────────────────────────────────

class MongoBaseModel(BaseModel):
    """
    Base model for all MongoDB documents.

    - `id` is an alias for `_id` so responses use `id` (not `_id`).
    - `populate_by_name=True` lets code use either `id` or `_id`.
    - `arbitrary_types_allowed=True` is required for PyObjectId.
    """

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


# ── TimestampMixin ────────────────────────────────────────────

class TimestampMixin(BaseModel):
    """
    UTC timestamps — set by the service layer, not auto-generated here.
    Optional so that partial documents (from projections) don't fail.
    """

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def now() -> datetime:
        """Return current UTC datetime (timezone-aware)."""
        return datetime.now(tz=timezone.utc)
