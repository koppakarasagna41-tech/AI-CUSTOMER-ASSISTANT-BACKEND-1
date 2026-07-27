"""app/schemas/user.py — Request/response schemas for the /users CRUD endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models.user import UserRole


class UserCreate(BaseModel):
    full_name: str      = Field(..., min_length=2, max_length=100)
    email:     EmailStr
    password:  str      = Field(..., min_length=8, max_length=128)
    role:      UserRole = UserRole.CUSTOMER


class UserUpdate(BaseModel):
    full_name:  Optional[str]  = Field(None, min_length=2, max_length=100)
    is_active:  Optional[bool] = None


class UserOut(BaseModel):
    id:            str
    full_name:     str
    email:         EmailStr
    role:          UserRole
    is_active:     bool
    last_login_at: Optional[str]      = None
    created_at:    Optional[datetime] = None
    updated_at:    Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
