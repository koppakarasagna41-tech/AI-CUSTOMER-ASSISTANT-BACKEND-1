"""
app/routers/admin_agents.py
──────────────────────────
Admin-only agent management endpoints.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.core.auth_deps import require_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.responses import success_response, paginated_response
from app.core.security import hash_password
from app.database import (
    UsersCollection,
    count_documents,
    get_document_by_id,
    get_documents,
    update_document_by_id,
    delete_document_by_id,
)
from app.models.user import UserRole
from app.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services import user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/agents", tags=["Admin Agents"])


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
    summary="List agents [admin]",
)
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    status: Optional[bool] = Query(None),
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    skip = (page - 1) * page_size
    filter_query = {"role": UserRole.AGENT.value}

    if search:
        pattern = re.escape(search.strip())
        filter_query["$or"] = [
            {"full_name": {"$regex": pattern, "$options": "i"}},
            {"email": {"$regex": pattern, "$options": "i"}},
        ]

    if status is not None:
        filter_query["is_active"] = status

    total = await count_documents(col, filter_query)
    docs = await get_documents(
        col,
        filter_query,
        skip=skip,
        limit=page_size,
        sort=[("created_at", DESCENDING)],
    )

    items = [UserOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]

    return paginated_response(
        data=items,
        total_items=total,
        page=page,
        page_size=page_size,
        message="Agents retrieved.",
    )


@router.get(
    "/{agent_id}",
    summary="Get agent details [admin]",
)
async def get_agent(
    agent_id: str,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    doc = await get_document_by_id(col, agent_id)
    if not doc or doc.get("role") != UserRole.AGENT.value:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    return success_response(
        data=UserOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Agent retrieved.",
    )


@router.patch(
    "/{agent_id}",
    summary="Update agent [admin]",
)
async def update_agent(
    agent_id: str,
    payload: UserUpdate,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise BadRequestError("No update fields provided.")

    updated = await update_document_by_id(col, agent_id, {"$set": updates})
    if not updated:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    doc = await get_document_by_id(col, agent_id)
    if not doc or doc.get("role") != UserRole.AGENT.value:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    return success_response(
        data=UserOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Agent updated.",
    )


@router.delete(
    "/{agent_id}",
    summary="Delete agent [admin]",
)
async def delete_agent(
    agent_id: str,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    doc = await get_document_by_id(col, agent_id)
    if not doc or doc.get("role") != UserRole.AGENT.value:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    deleted = await delete_document_by_id(col, agent_id)
    if not deleted:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    return success_response(message="Agent deleted.")


@router.post(
    "/{agent_id}/reset-password",
    summary="Reset an agent password [admin]",
)
async def reset_agent_password(
    agent_id: str,
    payload: PasswordReset,
    col: AsyncIOMotorCollection = Depends(UsersCollection),
    _: dict = Depends(require_admin),
):
    doc = await get_document_by_id(col, agent_id)
    if not doc or doc.get("role") != UserRole.AGENT.value:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    updated = await update_document_by_id(
        col,
        agent_id,
        {"$set": {"password_hash": hash_password(payload.password)}},
    )
    if not updated:
        raise NotFoundError("Agent not found.", error_code="AGENT_NOT_FOUND")

    return success_response(message="Agent password reset successfully.")
