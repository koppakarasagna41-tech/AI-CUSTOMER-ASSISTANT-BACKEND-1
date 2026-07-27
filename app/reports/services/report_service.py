"""
app/reports/services/report_service.py
──────────────────────────────────────────
Report data collection + generation orchestration.

Each report type has two functions:
  build_<type>_pdf()  → bytes   (ReportLab PDF)
  build_<type>_csv()  → bytes   (UTF-8 CSV)

Data is fetched from MongoDB and handed to the generators.
No business logic here — pure data assembly + format dispatch.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.reports.generators.csv_generator import generate_csv
from app.reports.generators.pdf_generator import generate_pdf
from app.analytics.services               import (
    get_overview_metrics, get_daily_chart, get_monthly_chart,
    get_sentiment_distribution, get_intent_distribution,
    get_ticket_metrics, get_escalation_metrics,
    export_conversations, export_tickets,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────

def _dt(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    return str(v) if v is not None else ""


def _period_label(period: str) -> str:
    return period.replace("_", " ").title()


# ── Analytics Report ──────────────────────────────────────────

async def build_analytics_pdf(
    conversations_col:  AsyncIOMotorCollection,
    messages_col:       AsyncIOMotorCollection,
    users_col:          AsyncIOMotorCollection,
    tickets_col:        AsyncIOMotorCollection,
    escalations_col:    AsyncIOMotorCollection,
    sentiment_logs_col: AsyncIOMotorCollection,
    intent_logs_col:    AsyncIOMotorCollection,
    period:             str = "last_30_days",
) -> bytes:
    """Generate a full analytics summary PDF."""
    overview, daily, monthly, sentiment, intents, tix_metrics, esc_metrics = await asyncio.gather(
        get_overview_metrics(conversations_col, messages_col, users_col,
                             tickets_col, escalations_col, intent_logs_col, period),
        get_daily_chart(conversations_col, messages_col, tickets_col),
        get_monthly_chart(conversations_col, messages_col, tickets_col),
        get_sentiment_distribution(sentiment_logs_col, period),
        get_intent_distribution(intent_logs_col, period),
        get_ticket_metrics(tickets_col, period),
        get_escalation_metrics(escalations_col, conversations_col, period),
    )

    # Build KPI list from overview
    kpis = [
        {"label": "Total Conversations",  "value": overview.total_conversations.value},
        {"label": "Total Users",          "value": overview.total_users.value},
        {"label": "Total Messages",       "value": overview.total_messages.value},
        {"label": "Resolved Tickets",     "value": overview.resolved_tickets.value},
        {"label": "Escalated",            "value": overview.escalated_tickets.value},
        {"label": "Open Tickets",         "value": overview.open_tickets.value},
        {"label": "Avg Response Time",    "value": overview.avg_response_time_ms.value, "unit": " ms"},
        {"label": "AI Resolution Rate",   "value": overview.ai_resolution_rate.value,   "unit": "%"},
    ]

    # Daily chart table (last 10 days)
    daily_rows = [[p.date, p.conversations, p.messages, p.tickets] for p in daily.data[-10:]]

    # Sentiment table
    sent_rows = [[p.label, p.emoji, p.count, f"{p.percentage}%"] for p in sentiment.data]

    # Intent table
    int_rows = [[p.label, p.count, f"{p.percentage}%"] for p in intents.data[:10]]

    # Ticket table
    tix_rows = [[cat, cnt] for cat, cnt in tix_metrics.by_category.items()]

    sections = [
        {
            "heading":    f"Overview — {_period_label(period)}",
            "kpis":       kpis,
        },
        {
            "heading":    "Daily Activity (Last 10 Days)",
            "table":      {
                "headers": ["Date", "Conversations", "Messages", "Tickets"],
                "rows":    daily_rows,
            },
        },
        {
            "heading":    "Sentiment Distribution",
            "paragraphs": [f"Total analysed: {sentiment.total_analysed}  |  Dominant: {sentiment.dominant or 'N/A'}"],
            "table":      {"headers": ["Sentiment", "Emoji", "Count", "Share"], "rows": sent_rows},
        },
        {
            "heading":    "Top Intents",
            "paragraphs": [f"Total classified: {intents.total_analysed}"],
            "table":      {"headers": ["Intent", "Count", "Share"], "rows": int_rows},
        },
        {
            "heading":    "Tickets by Category",
            "paragraphs": [f"Total tickets: {tix_metrics.total}  |  Resolution rate: {tix_metrics.resolution_rate}%"],
            "table":      {"headers": ["Category", "Count"], "rows": tix_rows},
        },
        {
            "heading":    "Escalations",
            "paragraphs": [
                f"Total escalations: {esc_metrics.total_escalations}",
                f"Escalation rate: {esc_metrics.escalation_rate}%",
            ],
            "table":      {
                "headers": ["Trigger", "Count"],
                "rows":    [[k, v] for k, v in esc_metrics.by_trigger.items()],
            },
        },
    ]

    return generate_pdf(
        title=f"Analytics Report — {_period_label(period)}",
        subtitle="AI Customer Support Platform",
        sections=sections,
        period=period,
    )


async def build_analytics_csv(
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    users_col:         AsyncIOMotorCollection,
    tickets_col:       AsyncIOMotorCollection,
    escalations_col:   AsyncIOMotorCollection,
    sentiment_logs_col: AsyncIOMotorCollection,
    intent_logs_col:   AsyncIOMotorCollection,
    period:            str = "last_30_days",
) -> bytes:
    overview = await get_overview_metrics(
        conversations_col, messages_col, users_col,
        tickets_col, escalations_col, intent_logs_col, period,
    )
    rows = [
        {"metric": "Total Conversations",  "value": overview.total_conversations.value},
        {"metric": "Total Users",          "value": overview.total_users.value},
        {"metric": "Total Messages",       "value": overview.total_messages.value},
        {"metric": "Resolved Tickets",     "value": overview.resolved_tickets.value},
        {"metric": "Escalated Tickets",    "value": overview.escalated_tickets.value},
        {"metric": "Open Tickets",         "value": overview.open_tickets.value},
        {"metric": "Avg Response Time (ms)", "value": overview.avg_response_time_ms.value},
        {"metric": "AI Resolution Rate (%)", "value": overview.ai_resolution_rate.value},
        {"metric": "Period",               "value": period},
        {"metric": "Generated At",         "value": datetime.now(tz=timezone.utc).isoformat()},
    ]
    return generate_csv(rows, ["metric", "value"])


# ── Conversation Report ───────────────────────────────────────

async def build_conversations_pdf(
    conversations_col: AsyncIOMotorCollection,
    messages_col:      AsyncIOMotorCollection,
    period:            str = "last_30_days",
) -> bytes:
    rows = await export_conversations(conversations_col, period=period, limit=500)

    table_rows = [
        [
            r.get("conversation_id", ""),
            r.get("user_id", "")[:12] + "…" if r.get("user_id") and len(str(r.get("user_id", ""))) > 12 else r.get("user_id", ""),
            r.get("status", ""),
            r.get("message_count", 0),
            r.get("sentiment", ""),
            _dt(r.get("created_at")),
        ]
        for r in rows[:200]
    ]

    sections = [
        {
            "heading":    f"Conversation Report — {_period_label(period)}",
            "paragraphs": [f"Total conversations: {len(rows)}"],
            "table":      {
                "headers": ["Conversation ID", "User ID", "Status", "Messages", "Sentiment", "Created At"],
                "rows":    table_rows,
            },
        }
    ]
    return generate_pdf(
        title=f"Conversation Report — {_period_label(period)}",
        subtitle="AI Customer Support Platform",
        sections=sections,
        period=period,
    )


async def build_conversations_csv(
    conversations_col: AsyncIOMotorCollection,
    period:            str = "last_30_days",
) -> bytes:
    rows = await export_conversations(conversations_col, period=period, limit=5000)
    return generate_csv(rows)


# ── Ticket Report ─────────────────────────────────────────────

async def build_tickets_pdf(
    tickets_col: AsyncIOMotorCollection,
    period:      str = "last_30_days",
) -> bytes:
    rows     = await export_tickets(tickets_col, period=period, limit=500)
    tix_meta = await get_ticket_metrics(tickets_col, period=period)

    kpis = [
        {"label": "Total",      "value": tix_meta.total},
        {"label": "Open",       "value": tix_meta.open},
        {"label": "Resolved",   "value": tix_meta.resolved},
        {"label": "Resolution Rate", "value": tix_meta.resolution_rate, "unit": "%"},
    ]

    table_rows = [
        [
            r.get("ticket_id", ""),
            r.get("subject", "")[:50],
            r.get("category", ""),
            r.get("priority", ""),
            r.get("status", ""),
            _dt(r.get("created_at")),
        ]
        for r in rows[:200]
    ]

    sections = [
        {
            "heading": f"Ticket Summary — {_period_label(period)}",
            "kpis":    kpis,
        },
        {
            "heading": "Ticket List",
            "table":   {
                "headers": ["Ticket ID", "Subject", "Category", "Priority", "Status", "Created At"],
                "rows":    table_rows,
            },
        },
    ]
    return generate_pdf(
        title=f"Ticket Report — {_period_label(period)}",
        subtitle="AI Customer Support Platform",
        sections=sections,
        period=period,
    )


async def build_tickets_csv(
    tickets_col: AsyncIOMotorCollection,
    period:      str = "last_30_days",
) -> bytes:
    rows = await export_tickets(tickets_col, period=period, limit=5000)
    return generate_csv(rows)
