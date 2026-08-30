import pytest
import os
import subprocess
import time
import httpx
import numpy as np
from unittest.mock import patch, MagicMock

# --- Issue 1 ---
def test_gitignore():
    # Write dummy secret
    with open("secrets.json", "w") as f:
        f.write("{}")
    
    try:
        # Check if git is available to check-ignore
        result = subprocess.run(["git", "check-ignore", "secrets.json"], capture_output=True)
        assert result.returncode == 0, "secrets.json is not ignored by git"
    except FileNotFoundError:
        # Fallback if git binary is not installed on PATH: verify .gitignore file directly
        with open(".gitignore", "r") as f:
            content = f.read()
        assert "secrets.json" in content, "secrets.json is not listed in .gitignore"
    finally:
        if os.path.exists("secrets.json"):
            os.remove("secrets.json")

# --- Issue 2 & 3 ---
from sources.rtsp_camera_source import RTSPCameraSource
def test_rtsp_camera_source():
    # Should instantiate without crashing
    src = RTSPCameraSource(camera_id="cam_1", rtsp_url="rtsp://dummy")
    assert src.camera_id == "cam_1"
    
    # Test metadata
    meta = src.get_metadata()
    assert meta["camera_id"] == "cam_1"
    assert "timestamp" in meta

# --- Issue 4, 5, 17, 22 ---
from fastapi.testclient import TestClient
from api.main import app
import config

client = TestClient(app)

@patch("api.routes_cameras.get_all_cameras", return_value=[])
def test_api_auth_and_cors(mock_get_all):
    # Normal request without API key should 401
    resp = client.get("/cameras")
    assert resp.status_code == 401
    
    # Normal request with API key
    resp = client.get("/cameras", headers={"X-API-Key": config.API_KEY})
    assert resp.status_code == 200

    # WebSocket without API key should be rejected
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/alerts/ws"):
            pass
    assert exc.value.code == 1008
    
    # WebSocket with API key
    with client.websocket_connect(f"/alerts/ws?api_key={config.API_KEY}") as ws:
        # Should connect successfully
        pass

# --- Issue 6 ---
def test_requirements_file():
    target = "requirements/requirements.txt"
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    assert "paddleocr" in content

# --- Issue 7 & 20 ---
from alerting.alert_dispatcher import dispatch_alert
from registry.base_plate_registry import RegistryRecord

@patch("db.dao_cameras.get_camera_by_id")
@patch("alerting.alert_dispatcher.insert_alert")
@patch("alerting.alert_dispatcher._http_client.post")
def test_dispatch_alert_async(mock_post, mock_insert, mock_get_camera):
    mock_insert.return_value = 1
    mock_get_camera.return_value = {"location": "test_location"}
    
    # Make the HTTP post mock block for 1 second
    def slow_post(*args, **kwargs):
        time.sleep(1)
    mock_post.side_effect = slow_post
    
    record = RegistryRecord(plate_number="MH01AA1111", status="stolen", flags=[], owner_info={})
    
    start_time = time.time()
    dispatch_alert(camera_id=1, detection_id=1, plate_text="MH01AA1111", record=record)
    duration = time.time() - start_time
    
    # Must return instantly (less than 0.1s), proving it's non-blocking
    assert duration < 0.1, f"dispatch_alert blocked for {duration} seconds!"
    
    # Wait for the background thread to finish
    time.sleep(1.5)
    mock_post.assert_called_once()

# --- Issue 8 & 9 ---
from detection.hierarchical_detector import HierarchicalDetector
from detection.base_ocr_engine import BaseOcrEngine, OcrResult

class MockOcrEngine(BaseOcrEngine):
    def __init__(self):
        self.call_count = 0
        
    def load_model(self): pass
    
    def read_text(self, img):
        self.call_count += 1
        # Mock finding a plate on the second call (preprocessed)
        return OcrResult("MH01AA1111", 0.9)

def test_ocr_sliding_window_scan():
    detector = HierarchicalDetector()
    mock_ocr = MockOcrEngine()
    detector.ocr_engine = mock_ocr
    
    dummy_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    
    boxes = detector._ocr_sliding_window_scan(dummy_crop)
    
    # Should only be called a maximum of 2 times (2 enhancements)
    assert mock_ocr.call_count <= 2, f"Expected <= 2 calls, got {mock_ocr.call_count}"
    assert len(boxes) == 1
    assert boxes[0].class_name == "license_plate"
