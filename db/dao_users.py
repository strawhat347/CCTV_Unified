"""
dao_users.py — DAO layer for the `users` and `audit_logs` tables.

Provides authentication-related persistence: user CRUD, login tracking,
and an immutable audit trail of security-relevant events.

All queries use %s parameterized placeholders — never string formatting.
"""

import logging
from db.connection_pool import get_connection

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Bootstrap — safe to call on every startup (IF NOT EXISTS)
# ------------------------------------------------------------------

def ensure_users_table() -> None:
    """
    Create the `users` and `audit_logs` tables if they don't already exist.
    Idempotent — safe to call on every application startup.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                username    VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role        ENUM('admin', 'operator', 'auditor') NOT NULL DEFAULT 'operator',
                is_active   BOOLEAN NOT NULL DEFAULT TRUE,
                last_login  TIMESTAMP NULL,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_username (username)
            ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT NULL,
                event_type  VARCHAR(50) NOT NULL,
                ip_address  VARCHAR(45),
                resource    VARCHAR(255),
                details     TEXT,
                timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                INDEX idx_event_type (event_type),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)
        conn.commit()
        logger.info("users / audit_logs tables ensured.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------
# User CRUD
# ------------------------------------------------------------------

def create_user(username: str, password_hash: str, role: str = "operator") -> dict:
    """
    Insert a new user row. Returns the new user record as a dict.

    Raises mysql.connector.IntegrityError if the username already exists
    (UNIQUE constraint on username column).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
            """,
            (username, password_hash, role),
        )
        conn.commit()
        new_id = cursor.lastrowid
        # Fetch the full record to return (includes created_at set by DB)
        cursor.execute(
            """
            SELECT id, username, password_hash, role, is_active,
                   last_login, created_at
            FROM users
            WHERE id = %s
            """,
            (new_id,),
        )
        return cursor.fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    """
    Fetch a single user row as a dict, or None if the username
    doesn't exist.  Includes password_hash for auth verification.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, username, password_hash, role, is_active,
                   last_login, created_at
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def update_last_login(user_id: int) -> None:
    """Update the last_login timestamp to NOW() for the given user."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login = NOW() WHERE id = %s",
            (user_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def list_users() -> list[dict]:
    """
    Return all users (newest first) without exposing password_hash.
    Suitable for admin dashboards.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, username, role, is_active, last_login, created_at
            FROM users
            ORDER BY created_at DESC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------
# Audit trail
# ------------------------------------------------------------------

def record_audit_event(
    user_id: int | None,
    event_type: str,
    ip_address: str | None = None,
    resource: str | None = None,
    details: str | None = None,
) -> int:
    """
    Insert an immutable audit log entry. Returns the new row id.

    user_id may be None for unauthenticated events (e.g. failed login
    attempts where the username didn't resolve).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (user_id, event_type, ip_address, resource, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, event_type, ip_address, resource, details),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_recent_audit_logs(limit: int = 100) -> list[dict]:
    """
    Fetch the most recent audit log entries, newest first.

    Joins on users to include the username (which may be NULL if the
    user was deleted after the event was recorded).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT a.id, a.user_id, u.username, a.event_type,
                   a.ip_address, a.resource, a.details, a.timestamp
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
