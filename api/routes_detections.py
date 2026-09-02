"""
api/routes_detections.py — Read-only routes wrapping db/dao_detections.py.

detections is high-volume, so every list endpoint here is bounded by
`limit` (default 100, capped at 500) — never an unbounded SELECT *.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query, Request

from db.dao_detections import (
    get_detection_by_id,
    get_detections_by_camera,
    get_recent_detections,
)
from api.schemas import Detection, InternalDetectionPush

router = APIRouter(prefix="/detections", tags=["detections"])


import re
from datetime import datetime

_STANDARD_PLATE_REGEX = re.compile(r'^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$')
_BH_PLATE_REGEX = re.compile(r'^[0-9]{2}BH[0-9]{4}[A-Z]{2}$')

def _filter_duplicate_standard_plates(raw_detections: List[dict]) -> List[dict]:
    # Process from oldest to newest to suppress chains (work on a copy to avoid mutating caller's list)
    raw_detections = list(reversed(raw_detections))
    
    filtered = []
    last_seen = {}
    
    for det in raw_detections:
        plate = det.get("plate_text")
        cam_id = det.get("camera_id")
        dt = det.get("detected_at")
        
        if not plate or not cam_id or not dt:
            filtered.append(det)
            continue
            
        # Ensure dt is a datetime object just in case the DB driver returned a string
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                filtered.append(det)
                continue
                
        is_standard = bool(_STANDARD_PLATE_REGEX.match(plate)) or \
                      bool(_BH_PLATE_REGEX.match(plate))
                      
        if is_standard:
            key = (cam_id, plate)
            if key in last_seen:
                time_diff = (dt - last_seen[key]).total_seconds()
                if time_diff < 5:
                    last_seen[key] = dt
                    continue
            last_seen[key] = dt
            
        filtered.append(det)
        
    filtered.reverse()
    return filtered


@router.get("", response_model=List[Detection])
def list_recent_detections(limit: int = Query(default=100, ge=1, le=500)):
    """GET /detections — most recent detections across all cameras."""
    raw_detections = get_recent_detections(limit=limit * 3)
    filtered = _filter_duplicate_standard_plates(raw_detections)
    return filtered[:limit]


@router.get("/{detection_id}", response_model=Detection)
def get_detection(detection_id: int):
    """GET /detections/{detection_id} — single detection or 404."""
    detection = get_detection_by_id(detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail=f"Detection {detection_id} not found")
    return detection


@router.get("/by-camera/{camera_id}", response_model=List[Detection])
def list_detections_by_camera(camera_id: int, limit: int = Query(default=100, ge=1, le=500)):
    """GET /detections/by-camera/{camera_id} — most recent detections for one camera."""
    raw_detections = get_detections_by_camera(camera_id=camera_id, limit=limit * 3)
    filtered = _filter_duplicate_standard_plates(raw_detections)
    return filtered[:limit]



@router.delete("")
def delete_all_logs(confirm: str = Query(default="")):
    """DELETE /detections - Clear all detection and alert logs. Requires confirm=DELETE_ALL_LOGS."""
    if confirm != "DELETE_ALL_LOGS":
        raise HTTPException(status_code=400, detail="Pass ?confirm=DELETE_ALL_LOGS to confirm this destructive action.")
    from db.connection_pool import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM alerts')
        cursor.execute('DELETE FROM detections')
        conn.commit()
        return {"status": "success", "message": "All logs deleted"}
    finally:
        cursor.close()
        conn.close()

@router.post("/internal/push")
async def internal_push_detection(detection_data: InternalDetectionPush):
    """
    Called by backend pipeline workers to broadcast a raw detection to the GUI.
    Authenticated via the global X-API-Key middleware.
    """
    from api.ws_alerts import manager
    
    payload = {
        "type": "detection",
        "data": detection_data.model_dump(mode="json")
    }
    await manager.broadcast_message(payload)
    return {"status": "broadcasted"}
