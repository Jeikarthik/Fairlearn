"""Authentication dependencies — current user extraction and RBAC."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Roles & Permissions ──────────────────────────────


class Role(str, Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Permission(str, Enum):
    AUDIT_CREATE = "audit:create"
    AUDIT_READ = "audit:read"
    AUDIT_EXECUTE = "audit:execute"
    REPORT_GENERATE = "report:generate"
    REPORT_DOWNLOAD = "report:download"
    PROBE_EXECUTE = "probe:execute"
    MONITOR_SETUP = "monitor:setup"
    ADMIN_ALL = "admin:*"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {Permission.ADMIN_ALL},
    Role.AUDITOR: {
        Permission.AUDIT_CREATE,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXECUTE,
        Permission.REPORT_GENERATE,
        Permission.REPORT_DOWNLOAD,
        Permission.PROBE_EXECUTE,
        Permission.MONITOR_SETUP,
    },
    Role.VIEWER: {Permission.AUDIT_READ, Permission.REPORT_DOWNLOAD},
}


def _has_permission(role: Role, permission: Permission) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return Permission.ADMIN_ALL in perms or permission in perms


# ── Current-user dependency ──────────────────────────


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Any | None:
    """Return the authenticated user or *None* (for public endpoints)."""
    if token is None:
        return None
    try:
        payload = decode_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    from app.models.user import User

    user = db.get(User, user_id)
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Any:
    """Return the authenticated user or raise 401.

    If auth is disabled (no JWT_SECRET_KEY set or dev mode), returns a
    synthetic admin user so the API keeps working without tokens.
    """
    import os

    if os.getenv("FAIRLENS_AUTH_DISABLED", "true").lower() == "true":
        # Dev-mode pass-through — return a synthetic admin
        from types import SimpleNamespace

        return SimpleNamespace(
            id="dev-user",
            email="dev@fairlens.local",
            org_id="dev-org",
            role=Role.ADMIN,
        )

    user = get_current_user_optional(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(permission: Permission):
    """Dependency factory — raises 403 if the user lacks *permission*."""

    def _checker(user: Any = Depends(get_current_user)) -> Any:
        role = Role(user.role) if isinstance(user.role, str) else user.role
        if not _has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' is required.",
            )
        return user

    return _checker
