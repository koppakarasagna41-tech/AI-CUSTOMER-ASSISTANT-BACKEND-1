"""
app/routers/admin_agents.py
──────────────────────────
Admin-only agent management endpoints.
"""

import logging

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth_deps import require_admin
from app.core.exceptions import BadRequestError
from app.core.responses import success_response
from app.database import UsersCollection
from app.models.user import UserRole
from app.schemas.user import UserCreate, UserOut
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
