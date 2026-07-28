"""
app/schemas/auth.py
────────────────────
Pydantic schemas for authentication endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models.user import UserRole


# ── Request bodies ────────────────────────────────────────────

class RegisterRequest(BaseModel):
    full_name: str       = Field(..., min_length=2, max_length=100,
                                 examples=["Jane Doe"])
    email:     EmailStr  = Field(..., examples=["jane@example.com"])
    password:  str       = Field(..., min_length=8, max_length=128,
                                 examples=["SecurePass123"])
    role:      UserRole  = UserRole.CUSTOMER


class LoginRequest(BaseModel):
    email:    EmailStr = Field(..., examples=["jane@example.com"])
    password: str      = Field(..., examples=["SecurePass123"])


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid JWT refresh token")


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── Response bodies ───────────────────────────────────────────

class UserOut(BaseModel):
    """Public user object — never includes password_hash."""
    id:            str
    full_name:     str
    email:         EmailStr
    role:          UserRole
    is_active:     bool
    last_login_at: Optional[str]      = None
    created_at:    Optional[datetime] = None
    updated_at:    Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TokenPair(BaseModel):
    """Returned on login and register."""
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int              # seconds until access token expires


class AuthResponse(BaseModel):
    """Full auth response: tokens + user profile."""
    user:   UserOut
    tokens: TokenPair
