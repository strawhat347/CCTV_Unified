"""
auth.py — Password hashing and JWT token management for CCTV Unified.

Password hashing uses Argon2 (via passlib) — the current OWASP recommendation
for password storage.  JWTs are signed with HS256 using a server-side secret.

Token types:
  - access  : short-lived (default 15 min), carried in Authorization header.
  - refresh : long-lived (default 7 days), used only to obtain new access tokens.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

import config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Password hashing (Argon2)
# ------------------------------------------------------------------

_pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return an Argon2id hash of *password*."""
    return _pwd_ctx.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify *plain_password* against a stored Argon2 hash.
    Returns True on match, False otherwise (never raises on mismatch).
    """
    return _pwd_ctx.verify(plain_password, hashed_password)

def dummy_verify():
    """
    Simulates a password verification to mitigate timing attacks
    for user enumeration (when a username is not found).
    """
    _pwd_ctx.dummy_verify()

# ------------------------------------------------------------------
# JWT helpers
# ------------------------------------------------------------------

_ALGORITHM = "HS256"


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Mint a short-lived access JWT.

    *data* must contain at least ``sub`` (username) and ``role``.
    The resulting token carries::

        { "sub": <username>, "role": <role>,
          "type": "access", "exp": ..., "iat": ... }
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=config.JWT_ACCESS_EXPIRE_MINUTES)
    )

    payload = {
        **data,
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGORITHM)


def create_refresh_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Mint a long-lived refresh JWT.

    *data* must contain at least ``sub`` (username).
    The resulting token carries::

        { "sub": <username>, "type": "refresh", "exp": ..., "iat": ... }
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=config.JWT_REFRESH_EXPIRE_DAYS)
    )

    payload = {
        **data,
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.  Returns the payload dict on success.

    Raises ``HTTPException(401)`` if the token is expired, malformed,
    or has an invalid signature.
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT invalid: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
