"""
api/routes_detections.py — Read-only routes wrapping db/dao_detections.py.

detections is high-volume, so every list endpoint here is bounded by
`limit` (default 100, capped at 500) — never an unbounded SELECT *.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from db.dao_detections import (
    get_detection_by_id,
    get_detections_by_camera,
    get_recent_detections,
)
from api.schemas import Detection

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("", response_model=List[Detection])
def list_recent_detections(limit: int = Query(default=100, ge=1, le=500)):
    """GET /detections — most recent detections across all cameras."""
    return get_recent_detections(limit=limit)


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
    return get_detections_by_camera(camera_id=camera_id, limit=limit)
