"""
app/models/user.py
───────────────────
MongoDB document model for the `users` collection.
"""

from enum import Enum
from typing import Optional

from pydantic import EmailStr, Field

from .base import MongoBaseModel, TimestampMixin


class UserRole(str, Enum):
    ADMIN    = "admin"
    AGENT    = "agent"
    CUSTOMER = "customer"


class UserDocument(MongoBaseModel, TimestampMixin):
    """
    Internal storage model — never expose this directly from an API response.
    Use UserOut schema for all responses.
    """
    full_name:     str
    email:         EmailStr
    password_hash: Optional[str] = None
    role:          UserRole       = UserRole.CUSTOMER
    is_active:     bool           = True
    last_login_at: Optional[str]  = None   # ISO datetime string
