"""
app/routers/users.py
─────────────────────
User management CRUD — admin-only endpoints.

All endpoints under /api/v1/users require a valid JWT + admin role.
"""

import logging

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.core.auth_deps  import require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    UsersCollection,
    get_document_by_id,
    get_documents,
    count_documents,
    update_document_by_id,
    delete_document_by_id,
)
from app.models.user     import UserRole
from app.schemas.user     import UserCreate, UserOut, UserUpdate
from app.services         import user_service
from app.utils.helpers   import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users (Admin)"])


@router.post(
    "",
    status_code=201,
    summary="Create an agent account [admin]",
)
async def create_agent_account(
    payload: UserCreate,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    if payload.role != UserRole.AGENT:
        raise BadRequestError(
            message="Only agent accounts can be created from this endpoint.",
            error_code="INVALID_ROLE",
        )

    user = await user_service.create_user(
        col=col,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role=UserRole.AGENT.value,
    )

    return success_response(
        data=UserOut(**{**user, "id": user["_id"]}).model_dump(),
        message="Agent account created successfully.",
    )


@router.get(
    "",
    summary="List all users [admin]",
)
async def list_users(
    page:      int = Query(1,   ge=1),
    page_size: int = Query(20,  ge=1, le=100),
    col:  AsyncIOMotorCollection = Depends(UsersCollection),
    _:    dict                   = Depends(require_admin),
):
    skip  = (page - 1) * page_size
    total = await count_documents(col)
    docs  = await get_documents(
        col, skip=skip, limit=page_size,
        sort=[("created_at", DESCENDING)],
    )
    # Strip password_hash from every doc
    items = []
    for d in docs:
        d.pop("password_hash", None)
        items.append(UserOut(**{**d, "id": d["_id"]}).model_dump())

    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Users retrieved.",
    )


@router.get(
    "/{user_id}",
    summary="Get user by ID [admin]",
)
async def get_user(
    user_id: str,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _:   dict                   = Depends(require_admin),
):
    doc = await user_service.get_user_by_id(col, user_id)
    if not doc:
        raise NotFoundError("User not found.", error_code="USER_NOT_FOUND")
    return success_response(
        data=UserOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="User retrieved.",
    )


@router.patch(
    "/{user_id}",
    summary="Update user [admin]",
)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _:   dict                   = Depends(require_admin),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise NotFoundError("No update fields provided.")

    updates["updated_at"] = utc_now()
    updated = await update_document_by_id(col, user_id, {"$set": updates})
    if not updated:
        raise NotFoundError("User not found.", error_code="USER_NOT_FOUND")

    doc = await user_service.get_user_by_id(col, user_id)
    return success_response(
        data=UserOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="User updated.",
    )


@router.delete(
    "/{user_id}",
    summary="Delete user [admin]",
)
async def delete_user(
    user_id: str,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _:   dict                   = Depends(require_admin),
):
    deleted = await delete_document_by_id(col, user_id)
    if not deleted:
        raise NotFoundError("User not found.", error_code="USER_NOT_FOUND")
    return success_response(message="User deleted.")
