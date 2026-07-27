"""
app/routers/messages.py
─────────────────────────
Starter CRUD endpoints for the messages collection.
"""

import logging

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING

from app.core.exceptions import NotFoundError
from app.core.responses  import success_response, paginated_response
from app.database        import (
    MessagesCollection,
    create_document,
    get_document_by_id,
    get_documents,
    count_documents,
    delete_document_by_id,
)
from app.schemas.message import MessageCreate, MessageOut
from app.utils.helpers   import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", status_code=201, summary="Create message")
async def create_message(
    payload: MessageCreate,
    col: AsyncIOMotorCollection = Depends(MessagesCollection),
):
    now = utc_now()
    doc = payload.model_dump()
    doc.update({"status": "sent", "created_at": now, "updated_at": now})
    inserted_id = await create_document(col, doc)
    created     = await get_document_by_id(col, inserted_id)
    return success_response(
        data=MessageOut(**{**created, "id": created["_id"]}).model_dump(),
        message="Message created.",
    )


@router.get("", summary="List messages by conversation")
async def list_messages(
    conversation_id: str = Query(..., description="Filter by conversation ID"),
    page:      int = Query(1,  ge=1),
    page_size: int = Query(50, ge=1, le=200),
    col: AsyncIOMotorCollection = Depends(MessagesCollection),
):
    q     = {"conversation_id": conversation_id}
    skip  = (page - 1) * page_size
    total = await count_documents(col, q)
    docs  = await get_documents(
        col, filter_query=q, skip=skip, limit=page_size,
        sort=[("created_at", ASCENDING)],
    )
    items = [MessageOut(**{**d, "id": d["_id"]}).model_dump() for d in docs]
    return paginated_response(
        data=items, total_items=total,
        page=page, page_size=page_size,
        message="Messages retrieved.",
    )


@router.get("/{message_id}", summary="Get message by ID")
async def get_message(
    message_id: str,
    col: AsyncIOMotorCollection = Depends(MessagesCollection),
):
    doc = await get_document_by_id(col, message_id)
    if not doc:
        raise NotFoundError("Message not found.", error_code="MSG_NOT_FOUND")
    return success_response(
        data=MessageOut(**{**doc, "id": doc["_id"]}).model_dump(),
        message="Message retrieved.",
    )


@router.delete("/{message_id}", summary="Delete message")
async def delete_message(
    message_id: str,
    col: AsyncIOMotorCollection = Depends(MessagesCollection),
):
    deleted = await delete_document_by_id(col, message_id)
    if not deleted:
        raise NotFoundError("Message not found.", error_code="MSG_NOT_FOUND")
    return success_response(message="Message deleted.")
