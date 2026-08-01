"""
app/core/security.py
─────────────────────
Password hashing and JWT token utilities.

  hash_password(plain)             → bcrypt hash string
  verify_password(plain, hashed)   → bool
  create_access_token(data, delta) → signed JWT string
  create_refresh_token(data)       → signed JWT string (longer expiry)
  decode_token(token)              → payload dict  (raises on invalid/expired)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

# ── password hashing context ────────────────────────────────
# Use PBKDF2 in this environment for compatibility with the installed
# passlib/bcrypt stack; it is sufficient for local auth and test flows.
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plain-text password."""
    normalized = plain.strip()
    if len(normalized.encode("utf-8")) > 72:
        normalized = normalized[:72]
    return _pwd_context.hash(normalized)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash."""
    if not hashed:
        return False

    normalized = plain.strip()
    if len(normalized.encode("utf-8")) > 72:
        normalized = normalized[:72]

    try:
        return _pwd_context.verify(normalized, hashed)
    except Exception:  # pragma: no cover - defensive for malformed hashes
        return False


# ── JWT ───────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    role:    str,
    extra:   Optional[dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject       : user ID (str form of MongoDB _id)
        role          : user role string ("admin" | "customer")
        extra         : any additional claims to embed
        expires_delta : override default expiry

    Returns:
        Signed JWT string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    now     = datetime.now(tz=timezone.utc)
    payload = {
        "sub":  subject,          # standard JWT subject claim
        "role": role,
        "type": "access",
        "iat":  now,
        "exp":  now + expires_delta,
    }
    if extra:
        payload.update(extra)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, role: str) -> str:
    """
    Create a signed JWT refresh token (longer expiry, minimal claims).
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    now           = datetime.now(tz=timezone.utc)
    payload       = {
        "sub":  subject,
        "role": role,
        "type": "refresh",
        "iat":  now,
        "exp":  now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises:
        ValueError("TOKEN_EXPIRED")   — token has expired
        ValueError("TOKEN_INVALID")   — signature invalid / malformed
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except ExpiredSignatureError:
        logger.debug("JWT decode failed: token expired")
        raise ValueError("TOKEN_EXPIRED")
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        raise ValueError("TOKEN_INVALID")
