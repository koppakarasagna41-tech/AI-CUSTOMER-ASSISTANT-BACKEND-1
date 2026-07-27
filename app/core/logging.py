"""
app/core/logging.py
────────────────────
Production-ready structured logging configuration for the FastAPI backend.

Features:
  - Rotating log files under the project logs/ directory.
  - Separate files for application, errors, API requests, Gemini, and MongoDB.
  - Structured JSON formatting for compatibility with Render/log aggregators.
  - Suppresses noisy third-party loggers (motor, pymongo, uvicorn.access).
"""

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from app.config import settings

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D102
        payload = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in {"args", "asctime", "created", "exc_info", "exc_text", "filename",
                       "funcName", "levelname", "levelno", "lineno", "message",
                       "module", "msecs", "msg", "name", "pathname", "process",
                       "processName", "relativeCreated", "stack_info", "thread",
                       "threadName"}:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, default=str, ensure_ascii=False)


class _ComponentFilter(logging.Filter):
    """Route records to the appropriate log file based on logger name or component."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D102
        return (
            getattr(record, "component", None) == self.component
            or record.name.startswith("app.middleware") and self.component == "api"
            or record.name.startswith("app.services.gemini") and self.component == "gemini"
            or record.name.startswith("app.rag.llm") and self.component == "gemini"
            or record.name.startswith("app.database") and self.component == "mongodb"
        )


def _build_rotating_handler(path: Path, *, level: int, component: Optional[str] = None) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    if component:
        handler.addFilter(_ComponentFilter(component))
    return handler


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logging with rotating file handlers and stdout output."""
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(JsonFormatter())
    root.addHandler(stream_handler)

    root.addHandler(_build_rotating_handler(LOG_DIR / "app.log", level=log_level))
    root.addHandler(_build_rotating_handler(LOG_DIR / "error.log", level=logging.ERROR))
    root.addHandler(_build_rotating_handler(LOG_DIR / "api.log", level=logging.INFO, component="api"))
    root.addHandler(_build_rotating_handler(LOG_DIR / "gemini.log", level=logging.INFO, component="gemini"))
    root.addHandler(_build_rotating_handler(LOG_DIR / "mongodb.log", level=logging.INFO, component="mongodb"))

    _quiet = {
        "motor": logging.WARNING,
        "pymongo": logging.WARNING,
        "uvicorn.access": logging.WARNING,
        "uvicorn.error": logging.INFO,
        "asyncio": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "multipart": logging.WARNING,
    }
    for name, lvl in _quiet.items():
        logging.getLogger(name).setLevel(lvl)

    logging.getLogger(__name__).info(
        "Logging configured",
        extra={"component": "app", "event": "logging_setup", "level_name": logging.getLevelName(log_level), "env": settings.APP_ENV},
    )
