"""
app/main.py
────────────
FastAPI application factory.

Modules registered:
  /health                       — health check
  /api/v1/auth/...              — JWT authentication
  /api/v1/users/...             — user management (admin)
  /api/v1/conversations/...     — conversation CRUD
  /api/v1/messages/...          — message CRUD
  /api/v1/tickets/...           — ticket management
  /api/v1/chat/...              — AI chat (Gemini direct)
  /api/v1/knowledge/...         — knowledge base management
  /api/v1/rag/...               — RAG Q&A pipeline
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config          import settings
from app.core.logging    import setup_logging
from app.core.exceptions import register_exception_handlers
from app.database        import connect_to_mongo, close_mongo_connection
from app.middleware      import RequestLoggingMiddleware

# ── Routers ───────────────────────────────────────────────────
from app.routers.health        import router as health_router
from app.routers.auth          import router as auth_router
from app.routers.users         import router as users_router
from app.routers.admin_agents  import router as admin_agents_router
from app.routers.conversations import router as conversations_router
from app.routers.messages      import router as messages_router
from app.routers.tickets       import router as tickets_router
from app.routers.chat          import router as chat_router
from app.knowledge.routers     import knowledge_router
from app.rag.routers           import rag_router
from app.intent.routers        import intent_router
from app.sentiment.routers     import sentiment_router
from app.escalation.routers    import escalation_router
from app.history.routers       import history_router
from app.analytics.routers     import analytics_router
from app.reports.routers       import reports_router

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(
        "Starting %s v%s [%s]",
        settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV,
    )

    try:
        await connect_to_mongo()
        logger.info("Application startup complete.")
    except Exception as exc:  # pragma: no cover - defensive startup path
        logger.warning("Application started without a reachable database: %s", exc)

    yield

    logger.info("Shutting down…")
    try:
        await close_mongo_connection()
    except Exception as exc:  # pragma: no cover - defensive shutdown path
        logger.warning("MongoDB shutdown cleanup failed: %s", exc)
    logger.info("Shutdown complete.")


# ── App factory ───────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "AI-powered customer support backend — "
            "FastAPI + MongoDB Atlas + ChromaDB + Gemini.\n\n"
            "**Auth:** `POST /api/v1/auth/login` → copy the `access_token` → "
            "click **Authorize 🔒** and paste `Bearer <token>`.\n\n"
            "**RAG Q&A:** `POST /api/v1/rag/query` — asks a question against "
            "the Knowledge Base with confidence-based escalation.\n\n"
            "**Knowledge Base:** `POST /api/v1/knowledge/upload` (admin) — "
            "upload and index documents for RAG."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging
    app.add_middleware(RequestLoggingMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # ── Routes ────────────────────────────────────────────────
    v1 = settings.API_V1_PREFIX   # /api/v1

    app.include_router(health_router)                        # GET  /health
    app.include_router(auth_router,          prefix=v1)     # /api/v1/auth/...
    app.include_router(users_router,         prefix=v1)     # /api/v1/users/...
    app.include_router(admin_agents_router,  prefix=v1)     # /api/v1/admin/agents/...
    app.include_router(conversations_router, prefix=v1)     # /api/v1/conversations/...
    app.include_router(messages_router,      prefix=v1)     # /api/v1/messages/...
    app.include_router(tickets_router,       prefix=v1)     # /api/v1/tickets/...
    app.include_router(chat_router,          prefix=v1)     # /api/v1/chat/...
    app.include_router(knowledge_router,     prefix=v1)     # /api/v1/knowledge/...
    app.include_router(rag_router,           prefix=v1)     # /api/v1/rag/...
    app.include_router(intent_router,        prefix=v1)     # /api/v1/intent/...
    app.include_router(sentiment_router,     prefix=v1)     # /api/v1/sentiment/...
    app.include_router(escalation_router,    prefix=v1)     # /api/v1/escalation/...
    app.include_router(history_router,       prefix=v1)     # /api/v1/history/...
    app.include_router(analytics_router,     prefix=v1)     # /api/v1/analytics/...
    app.include_router(reports_router,       prefix=v1)     # /api/v1/reports/...

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    return app


app = create_app()
