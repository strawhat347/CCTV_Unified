"""
dao_alerts.py — DAO (Data Access Object) layer for the `alerts` table.

Alerts are created by alerting/rule_engine.py whenever a detection matches
a rule (e.g. plate found on blacklist). detection_id is nullable here
because a detection can later be deleted while the alert survives
(ON DELETE SET NULL in the schema) — alerts are meant to be a durable log.

All queries use %s parameterized placeholders — never string formatting.
"""

from db.connection_pool import get_connection


def insert_alert(
    camera_id: int,
    alert_type: str,
    severity: str = "medium",
    message: str = None,
    location: str = None,
    detection_id: int = None,
) -> int:
    """
    Insert a new alert row. Returns the new alert_id.

    This is what alert_dispatcher.py will call whenever rule_engine.py
    decides a detection warrants an alert.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO alerts (detection_id, camera_id, alert_type, severity, message, location)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (detection_id, camera_id, alert_type, severity, message, location),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_alert_by_id(alert_id: int) -> dict | None:
    """Fetch a single alert row as a dict, or None if it doesn't exist."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM alerts WHERE alert_id = %s",
            (alert_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_unacknowledged_alerts(limit: int = 100) -> list[dict]:
    """
    Fetch open (unacknowledged) alerts, newest first — this is the
    query a GUI dashboard would poll to show a live "needs attention" list.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM alerts
            WHERE acknowledged = FALSE
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_all_alerts(limit: int = 500) -> list[dict]:
    """Fetch all alerts, newest first, regardless of acknowledged status."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM alerts
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_alerts_by_camera(camera_id: int, limit: int = 100) -> list[dict]:
    """Fetch the most recent alerts for one camera, newest first."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM alerts
            WHERE camera_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (camera_id, limit),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def acknowledge_alert(alert_id: int) -> bool:
    """
    Mark an alert as acknowledged (e.g. an operator clicked "seen" in
    the GUI). Returns True if a row was actually changed.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE alerts SET acknowledged = TRUE WHERE alert_id = %s",
            (alert_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def delete_alert(alert_id: int) -> bool:
    """Delete a single alert row."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM alerts WHERE alert_id = %s",
            (alert_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
