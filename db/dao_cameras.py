"""
dao_cameras.py — DAO (Data Access Object) layer for the `cameras` table.

Think of this module as the getter/setter layer for `cameras`, similar to
a CameraRepository class in C++: nothing outside this file should ever
write raw SQL against `cameras` directly.

All queries use %s parameterized placeholders — never string formatting —
to prevent SQL injection.
"""

from typing import Optional

from db.connection_pool import get_connection


def insert_camera(
    name: str, 
    stream_url: str, 
    location: Optional[str] = None, 
    status: str = "active",
    department: Optional[str] = None,
    department_id: Optional[int] = None,
    city: Optional[str] = None,
    district: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    camera_type: Optional[str] = None,
    connectivity: Optional[str] = None,
    storage_details: Optional[str] = None
) -> int:
    """
    Insert a new camera row. Returns the new camera_id (auto-increment PK).

    Equivalent to a constructor + INSERT — like `db.add(Camera(...))`
    returning the generated primary key.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cameras (name, location, department, department_id, city, district, latitude, longitude, camera_type, connectivity, storage_details, stream_url, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, location, department, department_id, city, district, latitude, longitude, camera_type, connectivity, storage_details, stream_url, status),
        )
        conn.commit()  # like flushing a transaction — nothing is persisted until this runs
        return cursor.lastrowid  # the auto-generated camera_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_camera_by_id(camera_id: int) -> dict | None:
    """
    Fetch a single camera row as a dict, or None if it doesn't exist.
    Like a getCameraById() that returns nullptr / std::optional::nullopt on miss.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM cameras WHERE camera_id = %s",
            (camera_id,),
        )
        return cursor.fetchone()  # None if no row matched
    finally:
        cursor.close()
        conn.close()


def get_all_cameras(status: str = None, q: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """
    Fetch cameras, optionally filtered by status and search query, with pagination.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM cameras WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
            
        if q:
            query += " AND (name LIKE %s OR camera_id LIKE %s OR location LIKE %s OR department LIKE %s)"
            search_term = f"%{q}%"
            params.extend([search_term, search_term, search_term, search_term])
            
        query += " ORDER BY camera_id LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def bulk_insert_cameras(cameras_data: list[tuple]) -> int:
    """
    Insert multiple cameras efficiently. 
    cameras_data should be a list of tuples matching the INSERT statement.
    Uses chunking to handle massive bulk imports safely.
    """
    if not cameras_data:
        return 0

    conn = get_connection()
    try:
        cursor = conn.cursor()
        total_inserted = 0
        chunk_size = 5000
        
        for i in range(0, len(cameras_data), chunk_size):
            chunk = cameras_data[i:i + chunk_size]
            cursor.executemany(
                """
                INSERT INTO cameras (name, location, department, department_id, city, district, latitude, longitude, camera_type, connectivity, storage_details, stream_url, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                chunk
            )
            total_inserted += cursor.rowcount
            
        conn.commit()
        return total_inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def delete_all_cameras() -> int:
    """
    Deletes all cameras from the database. Due to ON DELETE CASCADE,
    this will also wipe all detections and alerts.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Truncate won't work with FK constraints, so we DELETE
        cursor.execute("DELETE FROM cameras")
        deleted_count = cursor.rowcount
        cursor.execute("ALTER TABLE cameras AUTO_INCREMENT = 1")
        conn.commit()
        return deleted_count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

# Columns that update_camera() is allowed to write. This DAO is reusable code
# that other callers may invoke directly (not just the Pydantic-validated API
# route), so it shouldn't rely on the caller being the only thing keeping the
# dynamically-built UPDATE query safe from arbitrary column names.
_ALLOWED_UPDATE_COLUMNS = {
    "name", "location", "department", "department_id", "city", "district", "latitude", "longitude",
    "camera_type", "connectivity", "storage_details", "stream_url", "status",
}


def update_camera(camera_id: int, camera_data: dict) -> bool:
    """Updates a single camera."""
    if not camera_data:
        return False

    bad_keys = set(camera_data) - _ALLOWED_UPDATE_COLUMNS
    if bad_keys:
        raise ValueError(f"Invalid update fields: {bad_keys}")

    # First verify camera exists
    if get_camera_by_id(camera_id) is None:
        return False
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Build dynamic update query
        set_clauses = []
        values = []
        for key, val in camera_data.items():
            set_clauses.append(f"{key} = %s")  # safe: key is allow-listed above
            values.append(val)
            
        values.append(camera_id)
        
        query = f"UPDATE cameras SET {', '.join(set_clauses)} WHERE camera_id = %s"
        cursor.execute(query, tuple(values))
        conn.commit()
        
        # We checked existence above, so return True even if rowcount is 0 
        # (which happens if the update data is identical to existing data)
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def update_camera_status(camera_id: int, status: str) -> bool:
    """
    Update just the status field (the most common mutation — a camera
    going active -> error, etc). Returns True if a row was actually changed.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cameras SET status = %s WHERE camera_id = %s",
            (status, camera_id),
        )
        conn.commit()
        return cursor.rowcount > 0  # rowcount = how many rows the UPDATE touched
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def delete_camera(camera_id: int) -> bool:
    """
    Hard delete a camera row. Because `detections.camera_id` has
    ON DELETE CASCADE, this will also delete every detection (and,
    transitively, every alert) tied to this camera. Returns True if a
    row was actually deleted.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM cameras WHERE camera_id = %s",
            (camera_id,),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
