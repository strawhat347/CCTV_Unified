"""
dao_detections.py — DAO (Data Access Object) layer for the `detections` table.

This is a HIGH-VOLUME table (a new row per detected plate per frame), so
unlike `cameras`, we also provide filtered/paginated reads — you'll rarely
want "every detection ever" in one query once the pipeline has been
running a while.

All queries use %s parameterized placeholders — never string formatting.
"""

from db.connection_pool import get_connection


def insert_detection(
    camera_id: int,
    object_type: str,
    confidence: float,
    bbox_x: int,
    bbox_y: int,
    bbox_w: int,
    bbox_h: int,
    image_path: str = None,
    plate_text: str = None,
    location: str = None,
) -> int:
    """
    Insert a new detection row. Returns the new detection_id.

    This is the function detection_pipeline.py will call every time
    YOLO+OCR successfully identifies something in a frame.

    plate_text: the OCR-read plate string (or None if OCR didn't return a
    confident read). Kept as its own column -- separate from object_type --
    so Step 5's rule_engine.py can match it against plate_registry directly
    instead of parsing it out of a formatted string.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO detections
                (camera_id, object_type, confidence, bbox_x, bbox_y, bbox_w, bbox_h, image_path, plate_text, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (camera_id, object_type, confidence, bbox_x, bbox_y, bbox_w, bbox_h, image_path, plate_text, location),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_detection_by_id(detection_id: int) -> dict | None:
    """Fetch a single detection row as a dict, or None if it doesn't exist."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM detections WHERE detection_id = %s",
            (detection_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_detections_by_camera(camera_id: int, limit: int = 100) -> list[dict]:
    """
    Fetch the most recent detections for one camera, newest first.
    `limit` matters here — this table can grow huge, so we never
    fetch "everything" by default (same reason you'd never do
    `SELECT *` with no bound on a fast-growing log table in C++/SQL).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM detections
            WHERE camera_id = %s
            ORDER BY detected_at DESC, detection_id DESC
            LIMIT %s
            """,
            (camera_id, limit),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_recent_detections(limit: int = 100) -> list[dict]:
    """Fetch the most recent detections across ALL cameras, newest first."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM detections ORDER BY detected_at DESC, detection_id DESC LIMIT %s",
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def delete_detection(detection_id: int) -> bool:
    """
    Delete a single detection row. Note: any alert linked to this
    detection will have its alert.detection_id set to NULL automatically
    (ON DELETE SET NULL in the schema) rather than being deleted itself —
    the alert record survives even if the underlying detection is purged.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM detections WHERE detection_id = %s",
            (detection_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()