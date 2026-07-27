"""
app/analytics/services/analytics_service.py
──────────────────────────────────────────────
Analytics aggregation service.

All functions run MongoDB aggregation pipelines directly for efficiency.
Collections queried: conversations, messages, users, tickets,
                     escalation_events, sentiment_logs, intent_logs
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.analytics.schemas.analytics import (
    KPICard, OverviewMetrics,
    TimeSeriesPoint, TimeSeriesChart,
    SentimentDistributionPoint, SentimentDistributionChart,
    IntentDistributionPoint, IntentDistributionChart,
    TicketMetrics, EscalationMetrics,
    ResponseTimePoint, ResponseTimeChart,
    DashboardData,
)
from app.sentiment.constants import SENTIMENT_META
from app.intent.constants    import INTENT_META

logger = logging.getLogger(__name__)


# ── Period helpers ────────────────────────────────────────────

def _period_start(period: str) -> datetime:
    now = datetime.now(tz=timezone.utc)
    mapping = {
        "last_7_days":   now - timedelta(days=7),
        "last_30_days":  now - timedelta(days=30),
        "last_90_days":  now - timedelta(days=90),
        "last_12_months":now - timedelta(days=365),
        "all_time":      datetime(2000, 1, 1, tzinfo=timezone.utc),
    }
    return mapping.get(period, now - timedelta(days=30))


def _prev_period_start(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) of the period before the current one."""
    now   = datetime.now(tz=timezone.utc)
    delta_map = {
        "last_7_days":    timedelta(days=7),
        "last_30_days":   timedelta(days=30),
        "last_90_days":   timedelta(days=90),
        "last_12_months": timedelta(days=365),
    }
    delta = delta_map.get(period, timedelta(days=30))
    end   = now - delta
    start = end - delta
    return start, end


def _kpi(label: str, value, prev_value=None, unit: str = "count") -> KPICard:
    change = None
    trend  = None
    if prev_value is not None and prev_value > 0:
        change = round((value - prev_value) / prev_value * 100, 1)
        trend  = "up" if change > 0 else ("down" if change < 0 else "stable")
    return KPICard(label=label, value=value, change_pct=change, trend=trend, unit=unit)


# ── Overview metrics ──────────────────────────────────────────

async def get_overview_metrics(
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    users_col:         AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    escalations_col:   AsyncIOMotorCollection,
    intent_logs_col:   AsyncIOMotorCollection,
    period:            str = "last_30_days",
) -> OverviewMetrics:
    start     = _period_start(period)
    prev_s, prev_e = _prev_period_start(period)
    date_q    = {"created_at": {"$gte": start}}
    prev_q    = {"created_at": {"$gte": prev_s, "$lt": prev_e}}

    async def _count(col, q):         return await col.count_documents(q)
    async def _count_prev(col):       return await col.count_documents(prev_q)

    # Parallel counts
    (total_convs, total_msgs, total_users,
     resolved_tix, escalated_tix, open_tix,
     prev_convs, prev_users) = await asyncio.gather(
        _count(conversations_col, date_q),
        _count(messages_col, date_q),
        _count(users_col, {}),
        _count(tickets_col, {**date_q, "status": "resolved"}),
        _count(escalations_col, date_q),
        _count(tickets_col, {**date_q, "status": "open"}),
        _count_prev(conversations_col),
        _count_prev(users_col),
    )

    # AI resolution rate = resolved / total tickets (if any)
    total_tix_period = await tickets_col.count_documents(date_q)
    ai_res_rate = round(resolved_tix / max(total_tix_period, 1) * 100, 1)

    # Avg response time from intent_logs latency_ms
    pipeline = [
        {"$match": {**date_q, "latency_ms": {"$exists": True, "$gt": 0}}},
        {"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}}},
    ]
    rows = await intent_logs_col.aggregate(pipeline).to_list(1)
    avg_ms = round(rows[0]["avg"], 1) if rows else 0.0

    now = datetime.now(tz=timezone.utc)
    return OverviewMetrics(
        total_conversations  = _kpi("Total Conversations",  total_convs,  prev_convs),
        total_users          = _kpi("Total Users",           total_users,  prev_users),
        total_messages       = _kpi("Total Messages",        total_msgs),
        resolved_tickets     = _kpi("Resolved Tickets",      resolved_tix),
        escalated_tickets    = _kpi("Escalated",             escalated_tix),
        open_tickets         = _kpi("Open Tickets",          open_tix),
        avg_response_time_ms = _kpi("Avg Response Time",     avg_ms, unit="ms"),
        ai_resolution_rate   = _kpi("AI Resolution Rate",    ai_res_rate, unit="%"),
        period=period,
        generated_at=now,
    )


# ── Daily chart ───────────────────────────────────────────────

async def get_daily_chart(
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    days:              int = 30,
) -> TimeSeriesChart:
    start = datetime.now(tz=timezone.utc) - timedelta(days=days)

    async def _daily_agg(col, label):
        pipeline = [
            {"$match": {"created_at": {"$gte": start}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        rows = await col.aggregate(pipeline).to_list(length=days + 5)
        return {r["_id"]: r["count"] for r in rows}

    conv_map, msg_map, tix_map = await asyncio.gather(
        _daily_agg(conversations_col, "conversations"),
        _daily_agg(messages_col,      "messages"),
        _daily_agg(tickets_col,       "tickets"),
    )

    # Build contiguous date range
    points: list[TimeSeriesPoint] = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        points.append(TimeSeriesPoint(
            date=d,
            conversations=conv_map.get(d, 0),
            messages=msg_map.get(d, 0),
            tickets=tix_map.get(d, 0),
        ))

    return TimeSeriesChart(
        period="daily",
        data=points,
        totals={
            "conversations": sum(p.conversations for p in points),
            "messages":      sum(p.messages      for p in points),
            "tickets":       sum(p.tickets       for p in points),
        },
    )


# ── Monthly chart ─────────────────────────────────────────────

async def get_monthly_chart(
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    months:            int = 12,
) -> TimeSeriesChart:
    start = datetime.now(tz=timezone.utc) - timedelta(days=months * 31)

    async def _monthly_agg(col):
        pipeline = [
            {"$match": {"created_at": {"$gte": start}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        rows = await col.aggregate(pipeline).to_list(length=months + 2)
        return {r["_id"]: r["count"] for r in rows}

    conv_map, msg_map, tix_map = await asyncio.gather(
        _monthly_agg(conversations_col),
        _monthly_agg(messages_col),
        _monthly_agg(tickets_col),
    )

    all_months = sorted(set(list(conv_map) + list(msg_map) + list(tix_map)))
    points = [
        TimeSeriesPoint(
            date=m,
            conversations=conv_map.get(m, 0),
            messages=msg_map.get(m, 0),
            tickets=tix_map.get(m, 0),
        )
        for m in all_months
    ]

    return TimeSeriesChart(
        period="monthly",
        data=points,
        totals={
            "conversations": sum(p.conversations for p in points),
            "messages":      sum(p.messages      for p in points),
            "tickets":       sum(p.tickets       for p in points),
        },
    )


# ── Sentiment distribution ────────────────────────────────────

async def get_sentiment_distribution(
    sentiment_logs_col: AsyncIOMotorCollection,
    period:             str = "last_30_days",
) -> SentimentDistributionChart:
    start = _period_start(period)
    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": "$sentiment", "count": {"$sum": 1}}},
    ]
    rows  = await sentiment_logs_col.aggregate(pipeline).to_list(length=10)
    total = sum(r["count"] for r in rows) or 1
    dominant = max(rows, key=lambda r: r["count"])["_id"] if rows else None

    data = []
    for r in sorted(rows, key=lambda x: x["count"], reverse=True):
        s    = r["_id"] or "neutral"
        meta = SENTIMENT_META.get(s, {"label": s.title(), "emoji": ""})
        data.append(SentimentDistributionPoint(
            sentiment=s,
            label=meta["label"],
            emoji=meta["emoji"],
            count=r["count"],
            percentage=round(r["count"] / total * 100, 1),
        ))

    return SentimentDistributionChart(data=data, total_analysed=total, dominant=dominant)


# ── Intent distribution ───────────────────────────────────────

async def get_intent_distribution(
    intent_logs_col: AsyncIOMotorCollection,
    period:          str = "last_30_days",
) -> IntentDistributionChart:
    start = _period_start(period)
    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": "$intent", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows  = await intent_logs_col.aggregate(pipeline).to_list(length=20)
    total = sum(r["count"] for r in rows) or 1

    data = [
        IntentDistributionPoint(
            intent=r["_id"] or "unknown",
            label=INTENT_META.get(r["_id"] or "unknown", {}).get("label", r["_id"] or "Unknown"),
            count=r["count"],
            percentage=round(r["count"] / total * 100, 1),
        )
        for r in rows
    ]
    return IntentDistributionChart(data=data, total_analysed=total)


# ── Ticket metrics ────────────────────────────────────────────

async def get_ticket_metrics(
    tickets_col: AsyncIOMotorCollection,
    period:      str = "last_30_days",
) -> TicketMetrics:
    start = _period_start(period)
    q     = {"created_at": {"$gte": start}}

    async def _by(field):
        pipeline = [
            {"$match": q},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        rows = await tickets_col.aggregate(pipeline).to_list(length=20)
        return {r["_id"]: r["count"] for r in rows if r["_id"]}

    total, by_status, by_cat, by_pri = await asyncio.gather(
        tickets_col.count_documents(q),
        _by("status"), _by("category"), _by("priority"),
    )

    resolved   = by_status.get("resolved", 0)
    res_rate   = round(resolved / max(total, 1) * 100, 1)

    return TicketMetrics(
        total=total,
        open=by_status.get("open", 0),
        in_progress=by_status.get("in_progress", 0),
        resolved=resolved,
        closed=by_status.get("closed", 0),
        by_category=by_cat,
        by_priority=by_pri,
        resolution_rate=res_rate,
    )


# ── Escalation metrics ────────────────────────────────────────

async def get_escalation_metrics(
    escalations_col:   AsyncIOMotorCollection,
    conversations_col: AsyncIOMotorCollection,
    period:            str = "last_30_days",
) -> EscalationMetrics:
    start = _period_start(period)
    q     = {"created_at": {"$gte": start}}

    async def _by(field):
        pipeline = [
            {"$match": q},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        rows = await escalations_col.aggregate(pipeline).to_list(length=20)
        return {r["_id"]: r["count"] for r in rows if r["_id"]}

    total_esc, total_convs, by_trigger, by_pri, by_state = await asyncio.gather(
        escalations_col.count_documents(q),
        conversations_col.count_documents(q),
        _by("trigger"), _by("priority"), _by("state"),
    )

    esc_rate = round(total_esc / max(total_convs, 1) * 100, 1)

    return EscalationMetrics(
        total_escalations=total_esc,
        by_trigger=by_trigger,
        by_priority=by_pri,
        by_state=by_state,
        escalation_rate=esc_rate,
    )


# ── Response time chart ───────────────────────────────────────

async def get_response_time_chart(
    intent_logs_col: AsyncIOMotorCollection,
    days:            int = 30,
) -> ResponseTimeChart:
    start = datetime.now(tz=timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"created_at": {"$gte": start}, "latency_ms": {"$gt": 0}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "avg": {"$avg": "$latency_ms"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await intent_logs_col.aggregate(pipeline).to_list(length=days + 5)

    points = [
        ResponseTimePoint(date=r["_id"], avg_latency_ms=round(r["avg"], 1))
        for r in rows
    ]

    overall  = round(sum(p.avg_latency_ms for p in points) / max(len(points), 1), 1)
    sorted_  = sorted(p.avg_latency_ms for p in points)
    p95_idx  = int(len(sorted_) * 0.95)
    p95      = sorted_[p95_idx] if sorted_ else None

    return ResponseTimeChart(data=points, overall_avg_ms=overall, p95_ms=p95)


# ── Full dashboard ────────────────────────────────────────────

async def get_dashboard(
    conversations_col:  AsyncIOMotorCollection,
    messages_col:       AsyncIOMotorCollection,
    users_col:          AsyncIOMotorCollection,
    tickets_col:        AsyncIOMotorCollection,
    escalations_col:    AsyncIOMotorCollection,
    sentiment_logs_col: AsyncIOMotorCollection,
    intent_logs_col:    AsyncIOMotorCollection,
    period:             str = "last_30_days",
) -> DashboardData:
    """Fetch all analytics data concurrently and return the full dashboard payload."""
    (overview, daily, monthly, sentiment, intents,
     tickets, escalations, resp_time) = await asyncio.gather(
        get_overview_metrics(conversations_col, messages_col, users_col, tickets_col, escalations_col, intent_logs_col, period),
        get_daily_chart(conversations_col, messages_col, tickets_col),
        get_monthly_chart(conversations_col, messages_col, tickets_col),
        get_sentiment_distribution(sentiment_logs_col, period),
        get_intent_distribution(intent_logs_col, period),
        get_ticket_metrics(tickets_col, period),
        get_escalation_metrics(escalations_col, conversations_col, period),
        get_response_time_chart(intent_logs_col),
    )

    return DashboardData(
        overview=overview,
        daily_chart=daily,
        monthly_chart=monthly,
        sentiment=sentiment,
        intents=intents,
        tickets=tickets,
        escalations=escalations,
        response_time=resp_time,
        period=period,
        generated_at=datetime.now(tz=timezone.utc),
    )


# ── Export data ───────────────────────────────────────────────

async def export_conversations(
    conversations_col: AsyncIOMotorCollection,
    period:            str = "last_30_days",
    limit:             int = 5000,
) -> list[dict]:
    start  = _period_start(period)
    cursor = (
        conversations_col
        .find({"created_at": {"$gte": start}},
              {"_id": 0, "conversation_id": 1, "user_id": 1, "status": 1,
               "message_count": 1, "sentiment": 1, "created_at": 1, "updated_at": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def export_tickets(
    tickets_col: AsyncIOMotorCollection,
    period:      str = "last_30_days",
    limit:       int = 5000,
) -> list[dict]:
    start  = _period_start(period)
    cursor = (
        tickets_col
        .find({"created_at": {"$gte": start}},
              {"_id": 0, "ticket_id": 1, "subject": 1, "category": 1,
               "priority": 1, "status": 1, "user_id": 1, "created_at": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
