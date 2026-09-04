"""
tests/test_auth.py — Unit tests for Step 11: Enterprise Security & System Hardening.

Tests password hashing, JWT lifecycle, RBAC enforcement, and audit logging.
"""

import pytest
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock


class TestPasswordHashing:
    """Verify Argon2id password hashing and verification."""

    def test_hash_password_returns_argon2_hash(self):
        from api.auth import hash_password
        hashed = hash_password("testpassword123")
        assert hashed.startswith("$argon2"), f"Expected Argon2 hash, got: {hashed[:20]}"

    def test_verify_password_correct(self):
        from api.auth import hash_password, verify_password
        hashed = hash_password("securePassword!1")
        assert verify_password("securePassword!1", hashed) is True

    def test_verify_password_wrong(self):
        from api.auth import hash_password, verify_password
        hashed = hash_password("securePassword!1")
        assert verify_password("wrongPassword", hashed) is False

    def test_hash_is_not_plaintext(self):
        from api.auth import hash_password
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"

    def test_different_hashes_for_same_password(self):
        """Argon2 uses a random salt, so two hashes of the same password must differ."""
        from api.auth import hash_password
        h1 = hash_password("samePassword")
        h2 = hash_password("samePassword")
        assert h1 != h2, "Two hashes of the same password should differ (random salt)"


class TestJWTTokens:
    """Verify JWT issuance, validation, and rejection."""

    def test_create_access_token(self):
        from api.auth import create_access_token, decode_token
        token = create_access_token({"sub": "testuser", "role": "operator"})
        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "operator"
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        from api.auth import create_refresh_token, decode_token
        token = create_refresh_token({"sub": "testuser"})
        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_expired_token_rejected(self):
        from api.auth import create_access_token, decode_token
        from fastapi import HTTPException
        # Create a token that expired 1 second ago
        token = create_access_token(
            {"sub": "testuser", "role": "operator"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_tampered_token_rejected(self):
        from api.auth import create_access_token, decode_token
        from fastapi import HTTPException
        token = create_access_token({"sub": "testuser", "role": "operator"})
        # Tamper with the token by changing a character
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered)
        assert exc_info.value.status_code == 401

    def test_garbage_token_rejected(self):
        from api.auth import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.real.token")
        assert exc_info.value.status_code == 401


class TestRBACLogic:
    """Test role-based access control dependency logic."""

    def test_require_role_allows_matching_role(self):
        """require_role should pass through when user has an allowed role."""
        from api.rbac import require_role
        checker = require_role(["admin", "operator"])
        # The checker is an async function that takes current_user
        import asyncio
        user = {"id": 1, "username": "test", "role": "admin", "is_active": True}
        result = asyncio.get_event_loop().run_until_complete(checker(current_user=user))
        assert result["username"] == "test"

    def test_require_role_denies_wrong_role(self):
        """require_role should raise 403 when user role is not in allowed list."""
        from api.rbac import require_role
        from fastapi import HTTPException
        checker = require_role(["admin"])
        import asyncio
        user = {"id": 1, "username": "test", "role": "auditor", "is_active": True}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(checker(current_user=user))
        assert exc_info.value.status_code == 403


class TestDaoUsersBootstrap:
    """Test the DAO users module can be imported and has expected functions."""

    def test_dao_users_exports(self):
        from db.dao_users import (
            ensure_users_table,
            create_user,
            get_user_by_username,
            update_last_login,
            list_users,
            record_audit_event,
            get_recent_audit_logs,
        )
        # All functions should be callable
        assert callable(ensure_users_table)
        assert callable(create_user)
        assert callable(get_user_by_username)
        assert callable(update_last_login)
        assert callable(list_users)
        assert callable(record_audit_event)
        assert callable(get_recent_audit_logs)


class TestRoutesAuthImports:
    """Verify the auth routes module can be imported cleanly."""

    def test_routes_auth_importable(self):
        from api.routes_auth import router
        assert router.prefix == "/auth"

    def test_auth_schemas_exist(self):
        from api.schemas import TokenResponse, UserOut
        # Verify fields
        t = TokenResponse(access_token="abc", token_type="bearer")
        assert t.access_token == "abc"
