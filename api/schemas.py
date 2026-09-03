"""
api/schemas.py - Pydantic response models mirroring the dict shapes
returned by db/dao_cameras.py and db/dao_detections.py.

These are READ-ONLY response models for Step 3.5 (API skeleton).
Field names/types match the schema.sql columns exactly so DAO dicts
can be unpacked straight into these without transformation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CameraStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class Camera(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_id: int
    name: str
    location: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[int] = None
    city: Optional[str] = None
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    camera_type: Optional[str] = None
    connectivity: Optional[str] = None
    storage_details: Optional[str] = None
    stream_url: str
    status: str  # 'active' | 'inactive' | 'error'
    created_at: datetime


# Field lengths below mirror the VARCHAR column widths in db/schema.sql so
# oversized input gets a clean 422 instead of a raw MySQL "Data too long" error.
class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., max_length=150)
    department: str = Field(..., max_length=100)
    department_id: int
    city: str = Field(..., max_length=100)
    district: str = Field(..., max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    camera_type: Optional[str] = Field(None, max_length=50)
    connectivity: Optional[str] = Field(None, max_length=50)
    storage_details: Optional[str] = Field(None, max_length=100)
    stream_url: str = Field(..., min_length=1, max_length=255)
    status: CameraStatus = CameraStatus.active

    @field_validator("stream_url")
    @classmethod
    def validate_stream_url(cls, v: str) -> str:
        ALLOWED_PROTOCOLS = ("rtsp://", "rtsps://", "http://", "https://")
        if not any(v.startswith(proto) for proto in ALLOWED_PROTOCOLS):
            raise ValueError('stream_url must start with rtsp://, rtsps://, http://, or https://. Local files and other protocols are not allowed.')
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    department_id: Optional[int] = None
    city: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    camera_type: Optional[str] = Field(None, max_length=50)
    connectivity: Optional[str] = Field(None, max_length=50)
    storage_details: Optional[str] = Field(None, max_length=100)
    stream_url: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[CameraStatus] = None

    @field_validator("stream_url")
    @classmethod
    def validate_stream_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
            
        ALLOWED_PROTOCOLS = ("rtsp://", "rtsps://", "http://", "https://")
        if not any(v.startswith(proto) for proto in ALLOWED_PROTOCOLS):
            raise ValueError('stream_url must start with rtsp://, rtsps://, http://, or https://. Local files and other protocols are not allowed.')
        return v


class Detection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detection_id: int
    camera_id: Optional[int] = None
    detected_at: datetime
    object_type: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    image_path: Optional[str] = None
    plate_text: Optional[str] = None
    location: Optional[str] = None

class Alert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    detection_id: Optional[int] = None
    camera_id: Optional[int] = None
    created_at: datetime
    alert_type: str
    severity: str
    message: Optional[str] = None
    location: Optional[str] = None
    acknowledged: bool


class InternalAlertPush(BaseModel):
    """
    Payload for POST /alerts/internal/push. Only ever called by
    alerting/alert_dispatcher.py from a local pipeline process (see the
    origin check in api/routes_alerts.py) right after the same alert is
    written to the `alerts` table — the shape mirrors that row (see `Alert`
    above) so the WebSocket broadcast carries everything AlertPanel.jsx
    needs (alert_id, created_at, etc.) to render a freshly-pushed alert
    without a refetch.
    """
    alert_id: int
    detection_id: Optional[int] = None
    camera_id: Optional[int] = None
    alert_type: str = Field(..., max_length=50)
    severity: Literal["low", "medium", "high"] = "medium"
    message: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=150)
    acknowledged: bool = False
    created_at: Optional[datetime] = None


class InternalDetectionPush(BaseModel):
    detection_id: int
    camera_id: int
    object_type: str
    confidence: float
    bbox: Optional[str] = None
    plate_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    image_path: Optional[str] = None
    detected_at: Optional[datetime] = None
