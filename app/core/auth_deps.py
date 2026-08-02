"""
app/core/auth_deps.py
──────────────────────
FastAPI dependency functions for JWT authentication and RBAC.

Usage in any protected router:

    from app.core.auth_deps import get_current_user, require_admin

    @router.get("/me")
    async def me(current_user: dict = Depends(get_current_user)):
        return current_user

    @router.delete("/users/{id}")
    async def del_user(
        user_id: str,
        _: dict = Depends(require_admin),
        col = Depends(UsersCollection),
    ):
        ...
"""

import logging
from typing import Optional

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions  import ForbiddenError, UnauthorizedError
from app.core.security    import decode_token
from app.database.crud          import get_document_by_id
from app.database.dependencies  import UsersCollection
from motor.motor_asyncio  import AsyncIOMotorCollection

logger   = logging.getLogger(__name__)
_bearer  = HTTPBearer(auto_error=False)   # auto_error=False so we can return custom 401


# ── Token extraction ──────────────────────────────────────────

def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> str:
    """Pull the raw token string from the Authorization header."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError(
            message="Authentication required. Provide a Bearer token.",
            error_code="MISSING_TOKEN",
        )
    return credentials.credentials


# ── Core dependency ───────────────────────────────────────────

async def get_current_user(
    token: str = Depends(_extract_token),
    col:   AsyncIOMotorCollection = Depends(UsersCollection),
) -> dict:
    """
    Validate the JWT access token and return the current user document.

    Raises:
        UnauthorizedError — missing, expired, or invalid token
        UnauthorizedError — user no longer exists or is inactive
    """
    # Decode token
    try:
        payload = decode_token(token)
    except ValueError as exc:
        code = str(exc)
        if code == "TOKEN_EXPIRED":
            raise UnauthorizedError(
                message="Your session has expired. Please log in again.",
                error_code="TOKEN_EXPIRED",
            )
        raise UnauthorizedError(
            message="Invalid authentication token.",
            error_code="TOKEN_INVALID",
        )

    # Must be an access token (not a refresh token)
    if payload.get("type") != "access":
        raise UnauthorizedError(
            message="Invalid token type.",
            error_code="WRONG_TOKEN_TYPE",
        )

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise UnauthorizedError(
            message="Invalid token payload.",
            error_code="TOKEN_INVALID",
        )

    # Load user from DB on every request (ensures deactivated users are rejected)
    user = await get_document_by_id(col, user_id)
    if user is None:
        raise UnauthorizedError(
            message="User account not found.",
            error_code="USER_NOT_FOUND",
        )
    if not user.get("is_active", True):
        raise UnauthorizedError(
            message="Your account has been deactivated.",
            error_code="ACCOUNT_INACTIVE",
        )

    # Remove password_hash before returning
    user.pop("password_hash", None)
    return user


# ── Role-based guards ─────────────────────────────────────────

async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allow only users with role='admin'. Raises 403 otherwise."""
    if current_user.get("role") != "admin":
        raise ForbiddenError(
            message="Admin access required.",
            error_code="FORBIDDEN",
        )
    return current_user


async def require_agent_or_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allow users with role='admin' or role='agent'. Raises 403 otherwise."""
    if current_user.get("role") not in {"admin", "agent"}:
        raise ForbiddenError(
            message="Agent or admin access required.",
            error_code="FORBIDDEN",
        )
    return current_user


async def require_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Alias for get_current_user — makes intent explicit in route signatures."""
    return current_user
