"""Authentication API routes — register, login, refresh, profile."""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import Organization, User
from app.schemas.auth import (
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfileResponse,
)

logger = logging.getLogger("fairlens")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Register a new user and auto-create their organization."""
    # Check duplicate email
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create organization
    org = Organization(
        id=str(uuid4()),
        name=request.org_name,
    )
    db.add(org)
    db.flush()

    # Create user
    user = User(
        id=str(uuid4()),
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        role="admin",  # First user in an org is admin
        org_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user.registered", extra={"user_id": user.id, "org_id": org.id})

    return _build_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(request: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate with email + password, receive access and refresh tokens."""
    user = db.query(User).filter(User.email == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    logger.info("user.login", extra={"user_id": user.id})

    return _build_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    from jose import JWTError

    try:
        payload = decode_token(request.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is expired or invalid.",
        )

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")

    return _build_tokens(user)


@router.get("/me", response_model=UserProfileResponse)
def get_profile(user=Depends(get_current_user), db: Session = Depends(get_db)) -> UserProfileResponse:
    """Return the current authenticated user's profile."""
    org_name = None
    if hasattr(user, "org_id") and user.org_id:
        org = db.get(Organization, user.org_id)
        if org:
            org_name = org.name

    return UserProfileResponse(
        id=getattr(user, "id", "dev-user"),
        email=getattr(user, "email", "dev@fairlens.local"),
        full_name=getattr(user, "full_name", "Developer"),
        role=getattr(user, "role", "admin") if isinstance(getattr(user, "role", "admin"), str) else user.role.value,
        org_id=getattr(user, "org_id", "dev-org"),
        org_name=org_name or "Development",
        is_active=getattr(user, "is_active", True),
    )


def _build_tokens(user: User) -> TokenResponse:
    """Create access + refresh tokens for a user."""
    token_data = {"sub": user.id, "email": user.email, "role": user.role, "org_id": user.org_id}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )
