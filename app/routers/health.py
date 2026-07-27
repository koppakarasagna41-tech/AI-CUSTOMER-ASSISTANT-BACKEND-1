"""
app/routers/health.py
──────────────────────
Health-check endpoint.

GET /health
  Returns app status + MongoDB connectivity in one call.
  Used by Render's health-check probe and uptime monitors.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config   import settings
from app.core.responses import success_response
from app.database import ping_database

logger = APIRouter()
router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
async def health_check():
    """
    Returns the current status of the API and its database connection.

    Response codes:
      200 — API is up (MongoDB status is in the body)
      500 — caught by the global exception handler
    """
    db_ok = await ping_database()

    return success_response(
        message="OK" if db_ok else "API is up but database is unreachable.",
        data={
            "app":      settings.APP_NAME,
            "version":  settings.APP_VERSION,
            "env":      settings.APP_ENV,
            "database": "connected" if db_ok else "unreachable",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
