"""app/reports/schemas/report.py — Report request/response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """Common parameters for all report types."""
    period:  str  = Field("last_30_days", description="last_7_days | last_30_days | last_90_days | last_12_months | all_time")
    format:  str  = Field("pdf",          description="pdf | csv | json")
    title:   Optional[str] = None


class ReportMeta(BaseModel):
    """Metadata returned after a report is generated (for non-streaming endpoints)."""
    report_type:  str
    format:       str
    period:       str
    rows:         int
    file_size_kb: float
    generated_at: datetime
    download_url: Optional[str] = None
