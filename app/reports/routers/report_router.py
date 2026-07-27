"""
app/reports/routers/report_router.py
──────────────────────────────────────
Report Export API — all endpoints trigger a file download.

GET /reports/analytics           → Analytics report (PDF or CSV)
GET /reports/conversations       → Conversation report (PDF or CSV)
GET /reports/tickets             → Ticket report (PDF or CSV)
GET /reports/available           → List all available report types
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps  import require_admin
from app.core.exceptions import BadRequestError
from app.core.responses  import success_response
from app.database        import (
    ConversationsCollection,
    MessagesCollection,
    UsersCollection,
    TicketsCollection,
    EscalationEventsCollection,
    SentimentLogsCollection,
    IntentLogsCollection,
)
from app.reports.services import (
    build_analytics_pdf,     build_analytics_csv,
    build_conversations_pdf, build_conversations_csv,
    build_tickets_pdf,       build_tickets_csv,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Report Export"])

_VALID_PERIODS = [
    "last_7_days", "last_30_days", "last_90_days",
    "last_12_months", "all_time",
]
_VALID_FORMATS = {"pdf", "csv"}


def _validate(period: str, fmt: str) -> None:
    if period not in _VALID_PERIODS:
        raise BadRequestError(
            f"Invalid period '{period}'. Choose: {', '.join(_VALID_PERIODS)}",
            error_code="INVALID_PERIOD",
        )
    if fmt not in _VALID_FORMATS:
        raise BadRequestError(
            f"Invalid format '{fmt}'. Choose: pdf, csv",
            error_code="INVALID_FORMAT",
        )


def _filename(report_type: str, period: str, fmt: str) -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
    return f"{report_type}_{period}_{date}.{fmt}"


def _response(content: bytes, filename: str, fmt: str) -> StreamingResponse:
    media_types = {
        "pdf": "application/pdf",
        "csv": "text/csv; charset=utf-8",
    }
    return StreamingResponse(
        iter([content]),
        media_type=media_types.get(fmt, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(content)),
            "X-Report-Format":     fmt,
            "X-Report-Rows":       str(len(content)),
        },
    )


# ── GET /reports/available ────────────────────────────────────

@router.get(
    "/available",
    summary="List all available report types and formats",
)
async def list_reports(
    _: dict = Depends(require_admin),
):
    """Returns all supported report types, formats, and valid period options."""
    return success_response(
        data={
            "report_types": [
                {
                    "type":        "analytics",
                    "label":       "Analytics Report",
                    "description": "KPI summary, sentiment, intents, tickets, and escalations.",
                    "formats":     ["pdf", "csv"],
                },
                {
                    "type":        "conversations",
                    "label":       "Conversation Report",
                    "description": "All conversations with status, sentiment, and message count.",
                    "formats":     ["pdf", "csv"],
                },
                {
                    "type":        "tickets",
                    "label":       "Ticket Report",
                    "description": "Support tickets with category, priority, and resolution status.",
                    "formats":     ["pdf", "csv"],
                },
            ],
            "formats":  list(_VALID_FORMATS),
            "periods":  _VALID_PERIODS,
        },
        message="3 report types available.",
    )


# ── GET /reports/analytics ────────────────────────────────────

@router.get(
    "/analytics",
    summary="Download Analytics Report as PDF or CSV [admin]",
)
async def download_analytics_report(
    period: str = Query("last_30_days", description="Time period for the report"),
    format: str = Query("pdf",          description="pdf | csv"),
    _:      dict = Depends(require_admin),
    conv_col:  AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:   AsyncIOMotorCollection = Depends(MessagesCollection),
    user_col:  AsyncIOMotorCollection = Depends(UsersCollection),
    tix_col:   AsyncIOMotorCollection = Depends(TicketsCollection),
    esc_col:   AsyncIOMotorCollection = Depends(EscalationEventsCollection),
    sent_col:  AsyncIOMotorCollection = Depends(SentimentLogsCollection),
    int_col:   AsyncIOMotorCollection = Depends(IntentLogsCollection),
):
    """
    Download a full analytics report.

    PDF includes: KPI summary cards, daily activity table, sentiment
    distribution, intent distribution, ticket breakdown, escalation summary.

    CSV includes: flat key-value metrics table.
    """
    _validate(period, format)
    logger.info("Analytics report requested | format=%s period=%s", format, period)

    if format == "pdf":
        content = await build_analytics_pdf(
            conv_col, msg_col, user_col, tix_col, esc_col, sent_col, int_col, period,
        )
    else:
        content = await build_analytics_csv(
            conv_col, msg_col, user_col, tix_col, esc_col, sent_col, int_col, period,
        )

    return _response(content, _filename("analytics_report", period, format), format)


# ── GET /reports/conversations ────────────────────────────────

@router.get(
    "/conversations",
    summary="Download Conversation Report as PDF or CSV [admin]",
)
async def download_conversations_report(
    period: str = Query("last_30_days"),
    format: str = Query("pdf", description="pdf | csv"),
    _:      dict = Depends(require_admin),
    conv_col: AsyncIOMotorCollection = Depends(ConversationsCollection),
    msg_col:  AsyncIOMotorCollection = Depends(MessagesCollection),
):
    """
    Download a conversation report.

    PDF includes: conversation list with status, sentiment, message counts.
    CSV includes: full flat export (up to 5,000 conversations).
    """
    _validate(period, format)
    logger.info("Conversation report requested | format=%s period=%s", format, period)

    if format == "pdf":
        content = await build_conversations_pdf(conv_col, msg_col, period)
    else:
        content = await build_conversations_csv(conv_col, period)

    return _response(content, _filename("conversation_report", period, format), format)


# ── GET /reports/tickets ──────────────────────────────────────

@router.get(
    "/tickets",
    summary="Download Ticket Report as PDF or CSV [admin]",
)
async def download_tickets_report(
    period: str = Query("last_30_days"),
    format: str = Query("pdf", description="pdf | csv"),
    _:      dict = Depends(require_admin),
    tix_col: AsyncIOMotorCollection = Depends(TicketsCollection),
):
    """
    Download a ticket report.

    PDF includes: KPI summary cards + full ticket list table.
    CSV includes: full flat export (up to 5,000 tickets).
    """
    _validate(period, format)
    logger.info("Ticket report requested | format=%s period=%s", format, period)

    if format == "pdf":
        content = await build_tickets_pdf(tix_col, period)
    else:
        content = await build_tickets_csv(tix_col, period)

    return _response(content, _filename("ticket_report", period, format), format)
