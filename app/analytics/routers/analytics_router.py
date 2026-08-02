"""
app/analytics/routers/analytics_router.py
───────────────────────────────────────────
Analytics API — all endpoints require admin role.

GET  /analytics/dashboard        — Full dashboard (all metrics in one call)
GET  /analytics/overview         — KPI summary cards
GET  /analytics/charts/daily     — Daily time-series chart data
GET  /analytics/charts/monthly   — Monthly time-series chart data
GET  /analytics/charts/sentiment — Sentiment distribution (pie/bar chart)
GET  /analytics/charts/intents   — Intent distribution (bar chart)
GET  /analytics/charts/response-time — Avg response time trend
GET  /analytics/tickets          — Ticket breakdown metrics
GET  /analytics/escalations      — Escalation metrics
GET  /analytics/export/conversations — Export conversations as JSON/CSV
GET  /analytics/export/tickets       — Export tickets as JSON/CSV
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps  import require_agent_or_admin, get_current_user
from app.core.responses  import success_response
from app.database        import (
    ConversationsCollection,
    MessagesCollection,
    UsersCollection,
    TicketsCollection,
    SentimentLogsCollection,
    IntentLogsCollection,
    EscalationEventsCollection,
)
from app.analytics.schemas   import DashboardData
from app.analytics.services  import (
    get_overview_metrics,
    get_daily_chart,
    get_monthly_chart,
    get_sentiment_distribution,
    get_intent_distribution,
    get_ticket_metrics,
    get_escalation_metrics,
    get_response_time_chart,
    get_dashboard,
    export_conversations,
    export_tickets,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["Analytics"])

_VALID_PERIODS = ["last_7_days", "last_30_days", "last_90_days", "last_12_months", "all_time"]


def _validate_period(period: str) -> str:
    return period if period in _VALID_PERIODS else "last_30_days"


# ── GET /analytics/dashboard ──────────────────────────────────

@router.get(
    "/dashboard",
    summary="Full analytics dashboard — all metrics in one call [admin/agent]",
)
async def dashboard(
    period: str = Query("last_30_days", description="last_7_days | last_30_days | last_90_days | last_12_months | all_time"),
    _:      dict = Depends(require_agent_or_admin),
    conv_col:  AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:   AsyncIOMotorCollection = Depends(MessagesCollection),
    user_col:  AsyncIOMotorCollection = Depends(UsersCollection),
    tix_col:   AsyncIOMotorCollection = Depends(TicketsCollection),
    esc_col:   AsyncIOMotorCollection = Depends(EscalationEventsCollection),
    sent_col:  AsyncIOMotorCollection = Depends(SentimentLogsCollection),
    int_col:   AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Returns the complete analytics dashboard in a single request.
    All metrics are computed concurrently for low latency.
    """
    data = await get_dashboard(
        conversations_col=conv_col, messages_col=msg_col,
        users_col=user_col, tickets_col=tix_col,
        escalations_col=esc_col, sentiment_logs_col=sent_col,
        intent_logs_col=int_col, period=_validate_period(period),
    )
    return success_response(data=data.model_dump(), message="Dashboard data retrieved.")


# ── GET /analytics/overview ───────────────────────────────────

@router.get("/overview", summary="KPI summary cards")
async def overview(
    period: str = Query("last_30_days"),
    current_user: dict = Depends(get_current_user),
    conv_col:  AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:   AsyncIOMotorCollection = Depends(MessagesCollection),
    user_col:  AsyncIOMotorCollection = Depends(UsersCollection),
    tix_col:   AsyncIOMotorCollection = Depends(TicketsCollection),
    esc_col:   AsyncIOMotorCollection = Depends(EscalationEventsCollection),
    int_col:   AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Return overview metrics. Admins and agents receive global metrics;
    customers receive a limited user-scoped overview.
    """
    if current_user.get("role") in {"admin", "agent"}:
        data = await get_overview_metrics(
            conv_col, msg_col, user_col, tix_col, esc_col, int_col,
            period=_validate_period(period),
        )
        return success_response(data=data.model_dump(), message="Overview metrics retrieved.")

    # Customers: compute a minimal, user-scoped overview to keep the dashboard working
    start = _validate_period(period)
    # Use same period start logic as services; replicate minimal behavior
    from app.analytics.services.analytics_service import _period_start, _prev_period_start
    start_dt = _period_start(period)
    prev_s, prev_e = _prev_period_start(period)

    user_q = {"created_at": {"$gte": start_dt}, "user_id": current_user.get("_id")}
    prev_q = {"created_at": {"$gte": prev_s, "$lt": prev_e}, "user_id": current_user.get("_id")}

    total_convs = await conv_col.count_documents(user_q)
    prev_convs = await conv_col.count_documents(prev_q)
    total_msgs = await msg_col.count_documents(user_q)
    resolved_tix = await tix_col.count_documents({**user_q, "status": "resolved"})

    def _make_kpi(label, value, prev):
        change = None
        trend = None
        if prev and prev > 0:
            change = round((value - prev) / prev * 100, 1)
            trend = "up" if change > 0 else ("down" if change < 0 else "stable")
        return {"label": label, "value": value, "change_pct": change, "trend": trend}

    overview = {
        "total_conversations": _make_kpi("Total Conversations", total_convs, prev_convs),
        "total_users": _make_kpi("Total Users", 1, 1),
        "total_messages": _make_kpi("Total Messages", total_msgs, None),
        "resolved_tickets": _make_kpi("Resolved Tickets", resolved_tix, None),
        "escalated_tickets": _make_kpi("Escalated", 0, None),
        "open_tickets": _make_kpi("Open Tickets", 0, None),
        "avg_response_time_ms": _make_kpi("Avg Response Time", 0, None),
        "ai_resolution_rate": _make_kpi("AI Resolution Rate", 0, None),
        "period": period,
    }

    return success_response(data=overview, message="Overview metrics retrieved.")


# ── GET /analytics/charts/daily ───────────────────────────────

@router.get("/charts/daily", summary="Daily conversations/messages/tickets chart [admin/agent]")
async def daily_chart(
    days: int = Query(30, ge=7, le=365, description="Number of days to include"),
    _:    dict = Depends(require_agent_or_admin),
    conv_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:  AsyncIOMotorCollection = Depends(MessagesCollection),
    tix_col:  AsyncIOMotorCollection = Depends(TicketsCollection),
):
    data = await get_daily_chart(conv_col, msg_col, tix_col, days=days)
    return success_response(data=data.model_dump(), message="Daily chart data retrieved.")


# ── GET /analytics/charts/monthly ────────────────────────────

@router.get("/charts/monthly", summary="Monthly conversations/messages/tickets chart [admin/agent]")
async def monthly_chart(
    months: int = Query(12, ge=1, le=24, description="Number of months to include"),
    _:      dict = Depends(require_agent_or_admin),
    conv_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:  AsyncIOMotorCollection = Depends(MessagesCollection),
    tix_col:  AsyncIOMotorCollection = Depends(TicketsCollection),
):
    data = await get_monthly_chart(conv_col, msg_col, tix_col, months=months)
    return success_response(data=data.model_dump(), message="Monthly chart data retrieved.")


# ── GET /analytics/charts/sentiment ──────────────────────────

@router.get("/charts/sentiment", summary="Sentiment distribution chart [admin/agent]")
async def sentiment_chart(
    period: str = Query("last_30_days"),
    _:      dict = Depends(require_agent_or_admin),
    sent_col: AsyncIOMotorCollection = Depends(SentimentLogsCollection),
):
    data = await get_sentiment_distribution(sent_col, period=_validate_period(period))
    return success_response(data=data.model_dump(), message="Sentiment distribution retrieved.")


# ── GET /analytics/charts/intents ────────────────────────────

@router.get("/charts/intents", summary="Intent distribution chart [admin/agent]")
async def intent_chart(
    period: str = Query("last_30_days"),
    _:      dict = Depends(require_agent_or_admin),
    int_col: AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    data = await get_intent_distribution(int_col, period=_validate_period(period))
    return success_response(data=data.model_dump(), message="Intent distribution retrieved.")


# ── GET /analytics/charts/response-time ──────────────────────

@router.get("/charts/response-time", summary="Average response time trend [admin/agent]")
async def response_time_chart(
    days: int = Query(30, ge=7, le=365),
    _:    dict = Depends(require_agent_or_admin),
    int_col: AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    data = await get_response_time_chart(int_col, days=days)
    return success_response(data=data.model_dump(), message="Response time chart retrieved.")


# ── GET /analytics/tickets ────────────────────────────────────

@router.get("/tickets", summary="Ticket breakdown metrics [admin/agent]")
async def ticket_metrics(
    period: str = Query("last_30_days"),
    _:      dict = Depends(require_agent_or_admin),
    tix_col: AsyncIOMotorCollection = Depends(TicketsCollection),
):
    data = await get_ticket_metrics(tix_col, period=_validate_period(period))
    return success_response(data=data.model_dump(), message="Ticket metrics retrieved.")


# ── GET /analytics/escalations ────────────────────────────────

@router.get("/escalations", summary="Escalation metrics [admin/agent]")
async def escalation_metrics(
    period: str = Query("last_30_days"),
    _:      dict = Depends(require_agent_or_admin),
    esc_col:  AsyncIOMotorCollection = Depends(EscalationEventsCollection),
    conv_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    data = await get_escalation_metrics(esc_col, conv_col, period=_validate_period(period))
    return success_response(data=data.model_dump(), message="Escalation metrics retrieved.")


# ── GET /analytics/export/conversations ──────────────────────

@router.get("/export/conversations", summary="Export conversations as JSON or CSV [admin/agent]")
async def export_convs(
    period: str = Query("last_30_days"),
    format: str = Query("json",  description="json | csv"),
    limit:  int = Query(5000, ge=1, le=10000),
    _:      dict = Depends(require_agent_or_admin),
    conv_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    rows = await export_conversations(conv_col, period=_validate_period(period), limit=limit)
    filename = f"conversations_{period}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}"
    return _stream_export(rows, filename, format)


# ── GET /analytics/export/tickets ────────────────────────────

@router.get("/export/tickets", summary="Export tickets as JSON or CSV [admin/agent]")
async def export_tix(
    period: str = Query("last_30_days"),
    format: str = Query("json", description="json | csv"),
    limit:  int = Query(5000, ge=1, le=10000),
    _:      dict = Depends(require_agent_or_admin),
    tix_col: AsyncIOMotorCollection = Depends(TicketsCollection),
):
    rows = await export_tickets(tix_col, period=_validate_period(period), limit=limit)
    filename = f"tickets_{period}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}"
    return _stream_export(rows, filename, format)


# ── Export helper ─────────────────────────────────────────────

def _stream_export(rows: list[dict], filename: str, fmt: str) -> StreamingResponse:
    """Stream rows as JSON or CSV download."""
    if fmt == "csv" and rows:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            # Convert datetime objects to strings
            clean = {
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in row.items()
            }
            writer.writerow(clean)
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    # Default: JSON
    def _serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serialisable")

    content = json.dumps({"data": rows, "total": len(rows)}, default=_serial, indent=2)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
    )
