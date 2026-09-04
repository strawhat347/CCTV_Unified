"""
rbac.py — Role-Based Access Control dependencies for FastAPI.

Provides two composable FastAPI dependencies:

  get_current_user
      Extracts the JWT from the Authorization header (or a ``token``
      query parameter for WebSocket / SSE contexts), validates it,
      and returns the full user dict from the database.

  require_role(allowed_roles)
      Returns a dependency that checks whether the authenticated user's
      role is in *allowed_roles*, raising 403 Forbidden otherwise.

Usage in a route::

    @router.get("/admin/users")
    async def admin_list_users(
        user: dict = Depends(require_role(["admin"])),
    ):
        ...
"""

import logging

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from api.auth import decode_token
from db.dao_users import get_user_by_username

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# OAuth2 scheme — gives Swagger UI a native "Authorize" button that
# sends credentials to POST /auth/login and stores the token.
# ------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ------------------------------------------------------------------
# Core dependency: resolve JWT → user dict
# ------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    token_query: str | None = Query(None, alias="token"),
) -> dict:
    """
    Resolve the current authenticated user from a JWT.

    Token resolution order:
      1. ``Authorization: Bearer <token>`` header  (standard REST)
      2. ``?token=<token>`` query parameter         (WebSocket / SSE)

    Raises:
        HTTPException 401  if the token is missing, expired, or the
                           user no longer exists / is deactivated.
    """
    # Prefer header token; fall back to query param
    effective_token = token or token_query
    if not effective_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode & validate signature / expiry
    payload = decode_token(effective_token)

    # Must be an access token (not a refresh token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch fresh user record (roles / active status may have changed)
    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ------------------------------------------------------------------
# Role gate: returns a Depends-compatible callable
# ------------------------------------------------------------------

def require_role(allowed_roles: list[str]):
    """
    Factory that returns a FastAPI dependency enforcing role membership.

    Example::

        @router.delete("/cameras/{id}")
        async def delete_camera(
            id: int,
            user: dict = Depends(require_role(["admin"])),
        ):
            ...

    Raises:
        HTTPException 403  if the user's role is not in *allowed_roles*.
    """

    async def _role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user.get("role") not in allowed_roles:
            logger.warning(
                "RBAC denied: user=%s role=%s required=%s",
                current_user.get("username"),
                current_user.get("role"),
                allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.get('role')}' is not authorized. "
                       f"Required: {', '.join(allowed_roles)}",
            )
        return current_user

    return _role_checker
