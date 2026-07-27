"""
app/config/settings.py
────────────────────────
Centralised, type-safe environment configuration via Pydantic-Settings v2.
"""

from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────
    APP_NAME:      str  = "AI Customer Support API"
    APP_VERSION:   str  = "1.0.0"
    APP_ENV:       Literal["development", "staging", "production"] = "development"
    DEBUG:         bool = False
    API_V1_PREFIX: str  = "/api/v1"

    # ── Server ────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── MongoDB — accept both naming conventions ───────────────
    MONGODB_URI:    Optional[str] = Field(default=None)
    DATABASE_NAME:  Optional[str] = Field(default=None)
    MONGODB_URL:    str           = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str          = "ai_support"

    @model_validator(mode="after")
    def _resolve_mongo_vars(self) -> "Settings":
        if self.MONGODB_URI:
            self.MONGODB_URL = self.MONGODB_URI
        if self.DATABASE_NAME:
            self.MONGODB_DB_NAME = self.DATABASE_NAME
        return self

    # ── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── JWT / Security ────────────────────────────────────────
    SECRET_KEY:                   str = "change-me-to-a-long-random-secret-key-min-32"
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 30
    REFRESH_TOKEN_EXPIRE_DAYS:    int = 7

    # ── Google Gemini ─────────────────────────────────────────
    GEMINI_API_KEY:        str  = ""
    GEMINI_MODEL:          str  = "gemini-1.5-flash"
    GEMINI_MAX_TOKENS:     int  = 1024
    GEMINI_TEMPERATURE:    float = 0.7
    GEMINI_TOP_P:          float = 0.95
    GEMINI_TOP_K:          int   = 40
    # Max messages from history sent to Gemini per request
    GEMINI_HISTORY_LIMIT:  int   = 10
    # Request timeout in seconds
    GEMINI_TIMEOUT:        int   = 30

    # ── Knowledge Base / ChromaDB ─────────────────────────────
    CHROMA_PERSIST_DIR:          str   = "./chroma_data"
    CHROMA_COLLECTION_NAME:      str   = "knowledge_base_vectors"
    GEMINI_EMBEDDING_MODEL:      str   = "models/text-embedding-004"
    KB_MAX_FILE_SIZE_MB:         int   = 20
    KB_CHUNK_SIZE:               int   = 800
    KB_CHUNK_OVERLAP:            int   = 150
    KB_MIN_CHUNK_SIZE:           int   = 100
    KB_ALLOWED_EXTENSIONS:       str   = "pdf,docx,txt,csv,json,md"
    KB_UPLOAD_DIR:               str   = "./uploads/knowledge"

    # ── RAG ───────────────────────────────────────────────────
    RAG_TOP_K:                   int   = 5       # chunks to retrieve
    RAG_CONFIDENCE_THRESHOLD:    float = 0.55    # below → escalate
    RAG_MIN_CHUNKS_FOR_ANSWER:   int   = 1       # need at least N chunks
    RAG_MAX_CONTEXT_CHARS:       int   = 6000    # max context injected to Gemini
    RAG_ESCALATION_MESSAGE:      str   = (
        "I'm not confident enough to answer this question accurately. "
        "Your request has been forwarded to a human support agent who will "
        "assist you shortly."
    )

    # ── Intent Detection ──────────────────────────────────────
    INTENT_MODEL:                str   = "gemini-1.5-flash"
    INTENT_TEMPERATURE:          float = 0.0    # deterministic classification
    INTENT_TIMEOUT:              int   = 15     # fast — short prompt
    INTENT_CONFIDENCE_THRESHOLD: float = 0.6   # below → fallback to "unknown"

    # ── Sentiment Analysis ────────────────────────────────────
    SENTIMENT_MODEL:                str   = "gemini-1.5-flash"
    SENTIMENT_TEMPERATURE:          float = 0.0    # deterministic
    SENTIMENT_TIMEOUT:              int   = 12
    SENTIMENT_CONFIDENCE_THRESHOLD: float = 0.55   # below → neutral fallback

    # ── Escalation Detection ──────────────────────────────────
    ESCALATION_SENTIMENT_POLARITY:   float = -1.0   # polarity ≤ this → escalate
    ESCALATION_NEGATIVE_STREAK:      int   = 2       # consecutive negative msgs
    ESCALATION_UNANSWERED_THRESHOLD: int   = 3       # unanswered msgs before escalate
    ESCALATION_HUMAN_KEYWORDS:       str   = (
        "human,agent,real person,speak to someone,manager,supervisor,"
        "escalate,cancel account,legal,lawyer,lawsuit,refund now"
    )

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
