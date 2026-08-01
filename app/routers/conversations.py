"""
app/routers/conversations.py
─────────────────────────────
Starter CRUD endpoints for the conversations collection.
"""

import logging

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import DESCENDING

from app.core.auth_deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    ConversationsCollection,
    create_document,
    get_document_by_id,
    get_documents,
    count_documents,
    update_document_by_id,
    delete_document_by_id,
)
from app.models.user      import UserRole
from app.schemas.conversation import ConversationCreate, ConversationUpdate, ConversationOut
from app.utils.helpers        import utc_now, generate_conversation_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", status_code=201, summary="Create conversation")
async def create_conversation(
    payload: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    now = utc_now()
    user_id = current_user.get("_id")
    if current_user.get("role") == UserRole.ADMIN.value and payload.user_id:
        user_id = payload.user_id

    doc = payload.model_dump()
    doc.update({
        "conversation_id": generate_conversation_id(),
        "user_id":         user_id,
        "status":          "open",
        "message_count":   0,
        "created_at":      now,
        "updated_at":      now,
    })
    inserted_id = await create_document(col, doc)
    created     = await get_document_by_id(col, inserted_id)
    return success_response(
        data=ConversationOut(**{**created, "id": created["_id"]}).model_dump(),
        message="Conversation created.",
    )


@router.get("", summary="List conversations")
async def list_conversations(
    page:      int = Query(1,  ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    skip  = (page - 1) * page_size
    if current_user.get("role") == UserRole.ADMIN.value:
        total = await count_documents(col)
        docs  = await get_documents(
            col, skip=skip, limit=page_size,
            sort=[("created_at", DESCENDING)],
        )
    else:
        total = await count_documents(col, {"user_id": current_user.get("_id")})
        docs  = await get_documents(
            col,
            filter_query={"user_id": current_user.get("_id")},
            skip=skip, limit=page_size,
            sort=[("created_at", DESCENDING)],
        )

    items = [ConversationOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Conversations retrieved.",
    )


@router.get("/{conversation_id}", summary="Get conversation by ID")
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    doc = await get_document_by_id(col, conversation_id)
    if not doc or (
        current_user.get("role") != UserRole.ADMIN.value
        and doc.get("user_id") != current_user.get("_id")
    ):
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")
    return success_response(
        data=ConversationOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Conversation retrieved.",
    )


@router.patch("/{conversation_id}", summary="Update conversation")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise NotFoundError("No update fields provided.")

    doc = await get_document_by_id(col, conversation_id)
    if not doc or (
        current_user.get("role") != UserRole.ADMIN.value
        and doc.get("user_id") != current_user.get("_id")
    ):
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")

    updates["updated_at"] = utc_now()
    updated = await update_document_by_id(col, conversation_id, {"$set": updates})
    if not updated:
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")
    doc = await get_document_by_id(col, conversation_id)
    return success_response(
        data=ConversationOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Conversation updated.",
    )


@router.delete("/{conversation_id}", summary="Delete conversation")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    col: AsyncIOMotorCollection = Depends(ConversationsCollection),
):
    doc = await get_document_by_id(col, conversation_id)
    if not doc or (
        current_user.get("role") != UserRole.ADMIN.value
        and doc.get("user_id") != current_user.get("_id")
    ):
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")

    deleted = await delete_document_by_id(col, conversation_id)
    if not deleted:
        raise NotFoundError("Conversation not found.", error_code="CONV_NOT_FOUND")
    return success_response(message="Conversation deleted.")
