"""
api/routes_auth.py — Authentication endpoints (Step 11: Enterprise Security).

Provides login (OAuth2-compatible), token refresh, current-user info, and
admin-only user registration.  Login is rate-limited via slowapi to mitigate
brute-force attempts.  All security-relevant actions are recorded in the
audit_logs table through db.dao_users.record_audit_event.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator

from slowapi import Limiter
from slowapi.util import get_remote_address

from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from api.rbac import get_current_user, require_role
from api.schemas import TokenResponse, UserOut
from db.dao_users import (
    create_user,
    get_user_by_username,
    record_audit_event,
    update_last_login,
)

logger = logging.getLogger("api.routes_auth")

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)

# ── Request Models ────────────────────────────────────────────────────


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="operator", pattern=r"^(admin|operator|auditor)$")

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character.")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    """
    POST /auth/login — OAuth2-compatible login (Swagger UI "Authorize" works
    out of the box).  Returns an access + refresh token pair.

    Rate-limited to 5 requests per minute per client IP.
    """
    if len(form.password) > 128 or len(form.username) > 50:
        raise HTTPException(status_code=400, detail="Invalid username or password length")

    client_ip = request.client.host if request.client else "unknown"

    user = get_user_by_username(form.username)
    if user is None:
        dummy_verify()
        valid_password = False
    else:
        valid_password = verify_password(form.password, user["password_hash"])

    if user is None or not valid_password:
        # Log failure *before* raising so the audit trail is always written.
        user_id = user["id"] if user else None
        record_audit_event(
            user_id=user_id,
            event_type="LOGIN_FAILURE",
            ip_address=client_ip,
            resource="/auth/login",
            details=f"Failed login attempt for username '{form.username}'",
        )
        logger.warning("LOGIN_FAILURE ip=%s user=%s", client_ip, form.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.get("is_active", True):
        record_audit_event(
            user_id=user["id"],
            event_type="LOGIN_FAILURE",
            ip_address=client_ip,
            resource="/auth/login",
            details=f"Login attempt on disabled account '{form.username}'",
        )
        logger.warning("LOGIN_FAILURE (inactive) ip=%s user=%s", client_ip, form.username)
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Issue tokens
    access_token = create_access_token({"sub": user["username"], "role": user["role"], "uid": user["id"]})
    refresh_token = create_refresh_token({"sub": user["username"], "uid": user["id"]})

    # Side-effects: update last_login timestamp and write audit log.
    update_last_login(user["id"])
    record_audit_event(
        user_id=user["id"],
        event_type="LOGIN_SUCCESS",
        ip_address=client_ip,
        resource="/auth/login",
        details=f"Successful login for '{form.username}'",
    )
    logger.info("LOGIN_SUCCESS ip=%s user=%s", client_ip, form.username)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """
    POST /auth/refresh — Exchange a valid refresh token for a new access token.
    """
    payload = decode_token(body.refresh_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token is not a refresh token")

    # Verify user still exists and is active before issuing new access token.
    user = get_user_by_username(payload["sub"])
    if user is None or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User account not found or disabled")

    access_token = create_access_token({"sub": user["username"], "role": user["role"], "uid": user["id"]})

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    """
    GET /auth/me — Return the authenticated user's profile (no password_hash).
    """
    return UserOut(
        id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        last_login=current_user.get("last_login"),
        created_at=current_user["created_at"],
    )


@router.post("/register", response_model=UserOut)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    current_user: dict = Depends(require_role(["admin"])),
):
    """
    POST /auth/register - Create a new user account (admin-only).

    Only authenticated administrators can onboard new operators and auditors.
    Records a USER_CREATED audit event.
    """
    client_ip = request.client.host if request.client else "unknown"

    # 1. Check if user already exists
    existing = get_user_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # 2. Hash password and insert
    hashed_password = hash_password(body.password)
    new_user = create_user(body.username, hashed_password, role=body.role)
    new_user_id = new_user['id']

    
    # 3. Record Audit Event
    record_audit_event(
        user_id=current_user["id"],
        event_type="USER_CREATED",
        ip_address=client_ip,
        resource=f"/auth/register",
        details=f"Admin '{current_user['username']}' created user '{body.username}' with role '{body.role}'",
    )
    logger.info("USER_CREATED admin=%s new_user=%s role=%s", current_user["username"], body.username, body.role)

    return UserOut(
        id=new_user["id"],
        username=new_user["username"],
        role=new_user["role"],
        is_active=new_user["is_active"],
        last_login=new_user["last_login"],
        created_at=new_user["created_at"]
    )

