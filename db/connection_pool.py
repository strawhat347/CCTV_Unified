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

# --- Database TLS (encrypt connection to MySQL) ---
# When DB_SSL=true, all connections in the pool use TLS, preventing
# network sniffing of queries containing license plates and credentials.
if config.DB_SSL:
    import ssl as _ssl
    _ssl_context = _ssl.create_default_context()
    if config.DB_SSL_CA:
        _ssl_context.load_verify_locations(config.DB_SSL_CA)
    else:
        # If no CA specified, still encrypt but don't verify server cert
        # (acceptable for dev / same-host MySQL, not for production over WAN)
        _ssl_context.check_hostname = False
        _ssl_context.verify_mode = _ssl.CERT_NONE
    if config.DB_SSL_CERT and config.DB_SSL_KEY:
        _ssl_context.load_cert_chain(config.DB_SSL_CERT, config.DB_SSL_KEY)
    _dbconfig["ssl_disabled"] = False
    _dbconfig["ssl_ca"] = config.DB_SSL_CA or None
    _dbconfig["ssl_cert"] = config.DB_SSL_CERT or None
    _dbconfig["ssl_key"] = config.DB_SSL_KEY or None

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
    Borrow a connection from the pool with automatic reconnection.

    Caller is responsible for calling .close() on it when done — this
    does NOT actually close the TCP connection, it just returns it to
    the pool for reuse (same as releasing a buffer back to a pool
    allocator instead of freeing the underlying memory).

    The ping() call detects and recovers from stale connections that
    timed out while idle in the pool.

    Usage:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cameras")
            rows = cursor.fetchall()
        finally:
            conn.close()
    """
    conn = get_pool().get_connection()
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        conn = get_pool().get_connection()
    return conn