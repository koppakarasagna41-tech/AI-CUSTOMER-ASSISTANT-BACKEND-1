"""
app/routers/auth.py
────────────────────
JWT Authentication endpoints.

POST /api/v1/auth/register   — create account + return tokens
POST /api/v1/auth/login      — verify credentials + return tokens
POST /api/v1/auth/refresh    — swap refresh token for new access token
POST /api/v1/auth/logout     — client-side token invalidation notice
GET  /api/v1/auth/me         — return current authenticated user profile
"""

import logging

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorCollection

from app.config            import settings
from app.core.auth_deps    import get_current_user
from app.core.exceptions   import UnauthorizedError, BadRequestError
from app.core.responses    import success_response
from app.core.security     import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.database          import UsersCollection, get_document, get_document_by_id, update_document_by_id
from app.models.user       import UserRole
from app.schemas.auth      import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPair,
    UpdateProfileRequest,
    UserOut,
)
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_last_login,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Helpers ───────────────────────────────────────────────────

def _build_token_pair(user_id: str, role: str) -> TokenPair:
    """Create access + refresh token pair for a user."""
    access  = create_access_token(subject=user_id, role=role)
    refresh = create_refresh_token(subject=user_id, role=role)
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _user_out(doc: dict) -> UserOut:
    """Map a raw DB dict → UserOut schema."""
    return UserOut(
        id=doc["_id"],
        full_name=doc["full_name"],
        email=doc["email"],
        role=doc["role"],
        is_active=doc["is_active"],
        last_login_at=doc.get("last_login_at"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


# ── Endpoints ─────────────────────────────────────────────────

@router.post(
    "/register",
    status_code=201,
    summary="Register a new account",
    response_description="User profile + JWT token pair",
)
async def register(
    payload: RegisterRequest,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
):
    """
    Create a new user account.

    - Validates email uniqueness.
    - Hashes the password with bcrypt.
    - Returns an access token + refresh token immediately (no separate login needed).
    """
    requested_role = payload.role or UserRole.CUSTOMER
    if requested_role in {UserRole.ADMIN, UserRole.AGENT}:
        raise BadRequestError(
            message="Agent accounts must be created by an administrator." if requested_role == UserRole.AGENT else "Admin role may not be assigned during registration.",
            error_code="INVALID_ROLE",
        )

    user = await create_user(
        col=col,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role=requested_role.value,
    )

    tokens = _build_token_pair(user_id=user["_id"], role=user["role"])

    logger.info("New user registered | id=%s email=%s", user["_id"], user["email"])

    return success_response(
        data=AuthResponse(user=_user_out(user), tokens=tokens).model_dump(),
        message="Account created successfully.",
    )


@router.post(
    "/login",
    summary="Login with email and password",
    response_description="User profile + JWT token pair",
)
async def login(
    payload: LoginRequest,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
):
    """
    Authenticate with email + password.

    - Returns 401 for unknown email or wrong password (generic message to
      prevent user enumeration).
    - Returns 401 if the account is deactivated.
    """
    _INVALID = UnauthorizedError(
        message="Invalid email or password.",
        error_code="INVALID_CREDENTIALS",
    )

    # Fetch full doc (includes password_hash)
    user = await get_user_by_email(col, payload.email)
    if user is None:
        raise _INVALID

    if not verify_password(payload.password, user.get("password_hash", "") or ""):
        raise _INVALID

    if not user.get("is_active", True):
        raise UnauthorizedError(
            message="Your account has been deactivated. Contact support.",
            error_code="ACCOUNT_INACTIVE",
        )

    user_id = user["_id"]
    tokens  = _build_token_pair(user_id=user_id, role=user["role"])

    # Fire-and-forget timestamp update (don't block the response)
    await update_last_login(col, user_id)

    # Strip password before responding
    user.pop("password_hash", None)

    logger.info("User logged in | id=%s email=%s", user_id, user["email"])

    return success_response(
        data=AuthResponse(user=_user_out(user), tokens=tokens).model_dump(),
        message="Login successful.",
    )


@router.post(
    "/refresh",
    summary="Refresh access token",
    response_description="New access token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
):
    """
    Exchange a valid refresh token for a new access token.

    - Validates the token signature and expiry.
    - Verifies the user still exists and is active.
    - Returns a fresh access token (refresh token is NOT rotated here —
      add rotation in a later sprint if needed).
    """
    try:
        decoded = decode_token(payload.refresh_token)
    except ValueError as exc:
        code = str(exc)
        raise UnauthorizedError(
            message="Refresh token expired. Please log in again."
                    if code == "TOKEN_EXPIRED"
                    else "Invalid refresh token.",
            error_code=code,
        )

    if decoded.get("type") != "refresh":
        raise UnauthorizedError(
            message="Invalid token type.",
            error_code="WRONG_TOKEN_TYPE",
        )

    user_id = decoded.get("sub")
    user    = await get_user_by_id(col, user_id)

    if user is None or not user.get("is_active", True):
        raise UnauthorizedError(
            message="User account not found or inactive.",
            error_code="USER_NOT_FOUND",
        )

    new_access = create_access_token(subject=user_id, role=user["role"])

    return success_response(
        data={
            "access_token": new_access,
            "token_type":   "bearer",
            "expires_in":   settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
        message="Access token refreshed.",
    )


@router.post(
    "/logout",
    summary="Logout (invalidate client-side tokens)",
)
async def logout(
    current_user: dict = Depends(get_current_user),
):
    """
    Logout the current user.

    JWT tokens are stateless — this endpoint signals the client to
    discard both tokens.  Server-side token blacklisting can be added
    in a future sprint using Redis.
    """
    logger.info("User logged out | id=%s", current_user.get("_id"))
    return success_response(
        message="Logged out successfully. Please discard your tokens.",
    )


@router.get(
    "/me",
    summary="Get current user profile",
    response_description="Authenticated user profile",
)
async def get_me(
    current_user: dict = Depends(get_current_user),
):
    """
    Return the profile of the currently authenticated user.
    Requires a valid Bearer access token.
    """
    return success_response(
        data=_user_out(current_user).model_dump(),
        message="User profile retrieved.",
    )


@router.patch(
    "/me",
    summary="Update current user profile",
    response_description="Updated authenticated user profile",
)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(UsersCollection),
):
    updates: dict = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name.strip()
    if payload.email is not None:
        normalized_email = payload.email.lower().strip()
        existing = await get_document(col, {"email": normalized_email})
        if existing and existing.get("_id") != current_user.get("_id"):
            raise BadRequestError(
                message="An account with this email already exists.",
                error_code="EMAIL_TAKEN",
            )
        updates["email"] = normalized_email

    if not updates:
        raise BadRequestError(message="No profile fields were provided.", error_code="NO_UPDATES")

    updates["updated_at"] = utc_now()
    await update_document_by_id(col, current_user.get("_id"), {"$set": updates})

    refreshed = await get_document_by_id(col, current_user.get("_id"))
    return success_response(
        data=_user_out(refreshed).model_dump(),
        message="Profile updated successfully.",
    )


@router.post(
    "/change-password",
    summary="Change the current user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(UsersCollection),
):
    user_doc = await get_document_by_id(col, current_user.get("_id"))
    if not user_doc:
        raise BadRequestError(message="User not found.", error_code="USER_NOT_FOUND")

    if not verify_password(payload.current_password, user_doc.get("password_hash", "") or ""):
        raise BadRequestError(message="Current password is incorrect.", error_code="INVALID_PASSWORD")

    await update_document_by_id(
        col,
        current_user.get("_id"),
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": utc_now()}},
    )

    return success_response(message="Password changed successfully.")
