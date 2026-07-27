"""app/schemas/analytics.py — Request/response schemas for analytics events."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.analytics import AnalyticsEventType


class AnalyticsEventCreate(BaseModel):
    event_type:  AnalyticsEventType
    user_id:     Optional[str]          = None
    entity_id:   Optional[str]          = None
    entity_type: Optional[str]          = None
    value:       Optional[float]        = None
    properties:  dict[str, Any]         = Field(default_factory=dict)


class AnalyticsOut(BaseModel):
    id:          str
    event_type:  AnalyticsEventType
    user_id:     Optional[str]          = None
    entity_id:   Optional[str]          = None
    entity_type: Optional[str]          = None
    value:       Optional[float]        = None
    properties:  dict[str, Any]         = {}
    created_at:  Optional[datetime]     = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
