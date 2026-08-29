"""
tests/test_api.py — API route and schema serialization tests.
Run with: pytest tests/test_api.py
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime

from api.main import app
import config

client = TestClient(app)
client.headers.update({"X-API-Key": config.API_KEY})

# Dummy data mimicking DAO outputs
MOCK_CAMERA = {
    "camera_id": 1,
    "name": "Gate Camera",
    "location": "North Gate",
    "stream_url": "mock://stream",
    "status": "active",
    "created_at": datetime(2026, 1, 1, 12, 0, 0)
}

MOCK_DETECTION = {
    "detection_id": 100,
    "camera_id": 1,
    "detected_at": datetime(2026, 1, 1, 12, 5, 0),
    "object_type": "vehicle",
    "confidence": 0.95,
    "bbox_x": 10,
    "bbox_y": 20,
    "bbox_w": 100,
    "bbox_h": 50,
    "image_path": None
}


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("api.routes_cameras.get_all_cameras")
def test_list_cameras(mock_get_all):
    mock_get_all.return_value = [MOCK_CAMERA]
    
    response = client.get("/cameras")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    assert data[0]["camera_id"] == 1
    assert data[0]["name"] == "Gate Camera"
    # Pydantic handles datetime serialization automatically
    assert data[0]["created_at"] == "2026-01-01T12:00:00"


@patch("api.routes_cameras.get_camera_by_id")
def test_get_camera_not_found(mock_get_by_id):
    mock_get_by_id.return_value = None
    
    response = client.get("/cameras/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Camera 999 not found"}


@patch("api.routes_detections.get_recent_detections")
def test_list_recent_detections(mock_get_recent):
    mock_get_recent.return_value = [MOCK_DETECTION]
    
    response = client.get("/detections?limit=10")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    assert data[0]["object_type"] == "vehicle"
    assert data[0]["confidence"] == 0.95
    mock_get_recent.assert_called_once_with(limit=10)