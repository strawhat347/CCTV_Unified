"""
alerting/alert_dispatcher.py - Writes alerts to DB and broadcasts via WebSocket.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from mysql.connector import Error as MySQLError

import config
from db.dao_alerts import insert_alert
from registry.base_plate_registry import RegistryRecord

logger = logging.getLogger("alert_dispatcher")

# Reusable HTTP client and thread pool for non-blocking broadcasts
_http_client = httpx.Client(timeout=1.0)
_broadcast_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AlertBroadcaster")

# Broadcast host — defaults to loopback but can be overridden for
# Docker / multi-host deployments via API_HOST in .env.
_BROADCAST_HOST = getattr(config, "API_HOST", "127.0.0.1")

def _send_broadcast(alert_data: dict):
    try:
        response = _http_client.post(
            f"http://{_BROADCAST_HOST}:{config.API_PORT}/alerts/internal/push", 
            json=alert_data,
            headers={"X-API-Key": config.API_KEY}
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning(f"Alert broadcast returned HTTP {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        logger.warning(f"Failed to broadcast alert via WebSocket: {e}")

def dispatch_alert(
    camera_id: int, 
    detection_id: int, 
    plate_text: str, 
    record: RegistryRecord
) -> None:
    """
    Called by rule_engine.py when a plate triggers a rule.
    1. Writes to MySQL alerts table.
    2. Pushes to the API server via internal endpoint for WebSocket broadcast.
    """
    
    # Define severity based on status
    severity = "high" if "stolen" in record.status.lower() else "medium"
    
    flags_str = ", ".join(record.flags)
    message = f"Plate {plate_text} flagged! Status: {record.status.upper()}."
    if flags_str:
        message += f" Flags: {flags_str}"
    
    # Add custom description if present
    if record.owner_info.get("description"):
        message += f" Details: {record.owner_info['description']}"
        
    alert_type = f"plate_{record.status}"

    # Fetch camera location to include in the alert
    from db.dao_cameras import get_camera_by_id
    camera = get_camera_by_id(camera_id)
    camera_location = camera.get("location") if camera else None

    # 1. Write to database
    try:
        alert_id = insert_alert(
            camera_id=camera_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            location=camera_location,
            detection_id=detection_id
        )
    except MySQLError as e:
        logger.error(f"Failed to insert alert for plate {plate_text}: {e}")
        return

    # 2. Push to WebSocket via internal API
    # Create the payload mirroring the schema
    alert_data = {
        "alert_id": alert_id,
        "detection_id": detection_id,
        "camera_id": camera_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "location": camera_location,
        "acknowledged": False,
        # The DB sets created_at via CURRENT_TIMESTAMP but insert_alert()
        # doesn't return it — approximate with "now" since this runs right
        # after the insert. Good enough for a "x seconds ago" display.
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Offload the blocking HTTP call
    _broadcast_executor.submit(_send_broadcast, alert_data)

