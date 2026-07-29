"""
app/services/user_service.py
──────────────────────────────
Business logic for user management.

All functions accept a Motor collection so they are easy to test
with a mock collection (no patching of globals needed).
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.exceptions  import ConflictError, NotFoundError
from app.core.security    import hash_password
from app.database.crud    import (
    create_document,
    get_document,
    get_document_by_id,
    get_documents,
    count_documents,
    update_document,
    update_document_by_id,
    delete_document_by_id,
    document_exists,
)
from app.models.user      import UserRole
from app.utils.helpers    import utc_now

logger = logging.getLogger(__name__)


async def create_user(
    col:       AsyncIOMotorCollection,
    full_name: str,
    email:     str,
    password:  str,
    role:      str = UserRole.CUSTOMER.value,
) -> dict:
    """
    Create a new user — hashes the password, checks email uniqueness.

    If no users exist yet, the first registered account is promoted to admin.
    Otherwise new registrations may be created as a customer or demo agent.

    Returns the created user document (without password_hash).
    Raises ConflictError if the email is already registered.
    """
    # Guard: email uniqueness (also enforced by MongoDB unique index)
    if await document_exists(col, {"email": email.lower().strip()}):
        raise ConflictError(
            message="An account with this email already exists.",
            error_code="EMAIL_TAKEN",
        )

    existing_users = await count_documents(col)
    if isinstance(role, UserRole):
        role = role.value
    else:
        role = str(role).lower()

    if existing_users == 0:
        role = UserRole.ADMIN.value
    elif role not in {UserRole.CUSTOMER.value, UserRole.AGENT.value}:
        role = UserRole.CUSTOMER.value

    now  = utc_now()
    doc  = {
        "full_name":     full_name.strip(),
        "email":         email.lower().strip(),
        "password_hash": hash_password(password),
        "role":          role,
        "is_active":     True,
        "last_login_at": None,
        "created_at":    now,
        "updated_at":    now,
    }

    inserted_id = await create_document(col, doc)
    logger.info("User created | id=%s email=%s role=%s", inserted_id, email, role)

    # Return without the password_hash
    created = await get_document_by_id(col, inserted_id)
    return _strip_password(created)


async def get_user_by_email(
    col:   AsyncIOMotorCollection,
    email: str,
) -> Optional[dict]:
    """
    Fetch a user by email (case-insensitive via stored lowercase).
    Returns the full document INCLUDING password_hash (needed for login).
    Returns None if not found.
    """
    return await get_document(col, {"email": email.lower().strip()})


async def get_user_by_id(
    col:     AsyncIOMotorCollection,
    user_id: str,
) -> Optional[dict]:
    """Fetch a user by their MongoDB _id string (no password_hash)."""
    doc = await get_document_by_id(col, user_id)
    if doc is None:
        return None
    return _strip_password(doc)


async def update_last_login(
    col:     AsyncIOMotorCollection,
    user_id: str,
) -> None:
    """Stamp last_login_at on every successful login."""
    now = utc_now()
    await update_document_by_id(
        col, user_id,
        {"$set": {"last_login_at": now.isoformat(), "updated_at": now}},
    )


async def deactivate_user(
    col:     AsyncIOMotorCollection,
    user_id: str,
) -> bool:
    """Set is_active=False (soft delete)."""
    return await update_document_by_id(
        col, user_id,
        {"$set": {"is_active": False, "updated_at": utc_now()}},
    )


# ── Internal ──────────────────────────────────────────────────

def _strip_password(doc: Optional[dict]) -> Optional[dict]:
    """Remove password_hash from a document dict before returning it."""
    if doc:
        doc.pop("password_hash", None)
    return doc
