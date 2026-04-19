"""Pydantic schemas for authentication endpoints."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    org_name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    org_id: str
    org_name: str | None = None
    is_active: bool = True
