"""
connection_pool.py — MySQL connection pooling for CCTV Unified.

Instead of opening a new TCP connection to MySQL for every query (slow —
like malloc/free on every function call instead of reusing a buffer),
we keep a small pool of already-open connections and borrow/return them.
"""

import threading
from mysql.connector import pooling

import config

_POOL_NAME = "cctv_unified_pool"
_POOL_SIZE = config.DB_POOL_SIZE

_dbconfig = {
    "host": config.DB_HOST,
    "port": config.DB_PORT,
    "database": config.DB_NAME,
    "user": config.DB_USER,
    "password": config.DB_PASS,
}

_pool = None
_pool_lock = threading.Lock()


def get_pool():
    """
    Lazily initialize and return the MySQL connection pool singleton.
    Thread-safe via double-checked locking.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pooling.MySQLConnectionPool(
                    pool_name=_POOL_NAME,
                    pool_size=_POOL_SIZE,
                    **_dbconfig,
                )
    return _pool


def get_connection():
    """
    Borrow a connection from the pool.

    Caller is responsible for calling .close() on it when done — this
    does NOT actually close the TCP connection, it just returns it to
    the pool for reuse (same as releasing a buffer back to a pool
    allocator instead of freeing the underlying memory).

    Usage:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cameras")
            rows = cursor.fetchall()
        finally:
            conn.close()
    """
    return get_pool().get_connection()