"""
app/analytics/schemas/analytics.py
─────────────────────────────────────
All analytics response schemas.
Designed to be consumed directly by frontend charting libraries
(Recharts, Chart.js, D3, etc.).
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


# ── KPI cards ─────────────────────────────────────────────────

class KPICard(BaseModel):
    """Single metric card for the dashboard summary row."""
    label:       str
    value:       Any            # int | float | str
    change_pct:  Optional[float] = None   # % change vs. previous period
    trend:       Optional[str]  = None    # "up" | "down" | "stable"
    unit:        Optional[str]  = None    # "%" | "ms" | "count"


class OverviewMetrics(BaseModel):
    """
    All KPI cards in one response — maps directly to the dashboard header row.
    """
    total_conversations:     KPICard
    total_users:             KPICard
    total_messages:          KPICard
    resolved_tickets:        KPICard
    escalated_tickets:       KPICard
    open_tickets:            KPICard
    avg_response_time_ms:    KPICard
    ai_resolution_rate:      KPICard
    period:                  str          # e.g. "last_7_days"
    generated_at:            datetime


# ── Time-series (daily / monthly) ────────────────────────────

class TimeSeriesPoint(BaseModel):
    """One data point in a time-series chart."""
    date:         str           # YYYY-MM-DD or YYYY-MM
    conversations: int  = 0
    messages:      int  = 0
    users:         int  = 0
    tickets:       int  = 0


class TimeSeriesChart(BaseModel):
    """Ready-to-render time-series dataset."""
    period:  str                         # "daily" | "monthly"
    data:    list[TimeSeriesPoint]
    totals:  dict[str, int]              # {"conversations": N, ...}


# ── Sentiment distribution ────────────────────────────────────

class SentimentDistributionPoint(BaseModel):
    """One bar/slice in the sentiment chart."""
    sentiment:  str
    label:      str
    emoji:      str
    count:      int
    percentage: float


class SentimentDistributionChart(BaseModel):
    """Pie/bar chart data for sentiment breakdown."""
    data:          list[SentimentDistributionPoint]
    total_analysed: int
    dominant:      Optional[str] = None


# ── Intent distribution ───────────────────────────────────────

class IntentDistributionPoint(BaseModel):
    intent:     str
    label:      str
    count:      int
    percentage: float


class IntentDistributionChart(BaseModel):
    """Bar chart data for intent breakdown."""
    data:   list[IntentDistributionPoint]
    total_analysed: int


# ── Ticket analytics ──────────────────────────────────────────

class TicketMetrics(BaseModel):
    total:       int
    open:        int
    in_progress: int
    resolved:    int
    closed:      int
    by_category: dict[str, int]
    by_priority: dict[str, int]
    resolution_rate: float      # resolved / total * 100
    avg_resolution_hours: Optional[float] = None


class EscalationMetrics(BaseModel):
    total_escalations:  int
    by_trigger:         dict[str, int]
    by_priority:        dict[str, int]
    by_state:           dict[str, int]
    escalation_rate:    float           # escalations / total_conversations * 100


# ── Response time ─────────────────────────────────────────────

class ResponseTimePoint(BaseModel):
    date:           str
    avg_latency_ms: float


class ResponseTimeChart(BaseModel):
    data:           list[ResponseTimePoint]
    overall_avg_ms: float
    p95_ms:         Optional[float] = None


# ── Export ────────────────────────────────────────────────────

class ExportRow(BaseModel):
    """One row in a CSV/JSON export."""
    row: dict[str, Any]


class ExportResponse(BaseModel):
    filename:    str
    format:      str             # "json" | "csv"
    rows:        int
    data:        list[dict[str, Any]]
    generated_at: datetime


# ── Full dashboard payload ────────────────────────────────────

class DashboardData(BaseModel):
    """
    Single endpoint that returns everything the frontend needs
    to render the full analytics dashboard.
    """
    overview:     OverviewMetrics
    daily_chart:  TimeSeriesChart
    monthly_chart: TimeSeriesChart
    sentiment:    SentimentDistributionChart
    intents:      IntentDistributionChart
    tickets:      TicketMetrics
    escalations:  EscalationMetrics
    response_time: ResponseTimeChart
    period:       str
    generated_at: datetime
