"""
scripts/vigorous_test.py - Vigorous E2E testing of Step 5.
"""
import sys
import logging
from pathlib import Path

# Add project root to path so this script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from unittest.mock import patch

from api.main import app
from registry.mock_registry import MockRegistry
from alerting.rule_engine import RuleEngine
from db.dao_alerts import get_unacknowledged_alerts
from db.dao_cameras import insert_camera
from db.dao_detections import insert_detection
import alerting.alert_dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vigorous_test")

def main():
    logger.info("Starting vigorous tests for Step 5...")
    client = TestClient(app)

    # 1. Test Registry Parsing
    logger.info("Test 1: Registry Parsing")
    registry = MockRegistry()
    registry.connect()
    record = registry.lookup("MH12AB1234")
    assert record is not None, "MH12AB1234 should be in registry"
    assert record.status == "stolen", "Status should be stolen"
    assert record.owner_info.get("description") != "", "Description should be parsed"
    logger.info("Test 1 Passed.")

    # 2. Database Insertion Test
    logger.info("Test 2: Database and Rule Engine E2E (without live HTTP)")
    try:
        cam_id = insert_camera("Vigorous Test Cam", "mock://", "active")
        det_id = insert_detection(cam_id, "license_plate", 0.99, 0,0,10,10, None, "MH12AB1234")
    except Exception as e:
        logger.error(f"DB insertion failed: {e}")
        sys.exit(1)

    # Patch httpx.Client to prevent actual HTTP call since server isn't running
    with patch("httpx.Client.post") as mock_post:
        engine = RuleEngine(registry)
        engine.process_detection(det_id, cam_id, "MH12AB1234")
        
        # Verify it tried to hit the API
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["alert_type"] == "plate_stolen"
        assert payload["camera_id"] == cam_id
        assert payload["detection_id"] == det_id
        logger.info("RuleEngine correctly triggered AlertDispatcher and formulated API payload.")

    # Check DB
    alerts = get_unacknowledged_alerts(limit=5)
    found = any(a["detection_id"] == det_id for a in alerts)
    assert found, "Alert was not successfully inserted into the database!"
    logger.info("Test 2 Passed. Alert was written to DB.")

    # 3. Test API and WebSockets using TestClient
    logger.info("Test 3: API & WebSocket Broadcast")
    # Connect a websocket client
    with client.websocket_connect("/alerts/ws") as websocket:
        # Simulate the alert_dispatcher pushing an alert via internal API
        push_resp = client.post("/alerts/internal/push", json=payload, headers={"X-API-Key": "cctv_secure_dev_key"})
        assert push_resp.status_code == 200, f"Internal push failed: {push_resp.text}"
        
        # Verify websocket receives it
        ws_data = websocket.receive_json()
        assert ws_data["detection_id"] == det_id
        assert ws_data["alert_type"] == "plate_stolen"
        logger.info("WebSocket successfully received the broadcasted alert!")

    # 4. Test GET endpoints
    logger.info("Test 4: REST Endpoints")
    resp = client.get("/alerts/", headers={"X-API-Key": "cctv_secure_dev_key"})
    assert resp.status_code == 200
    fetched_alerts = resp.json()
    assert len(fetched_alerts) > 0
    assert fetched_alerts[0]["camera_id"] == cam_id
    logger.info("Test 4 Passed. /alerts/ returned the database records.")
    
    logger.info("ALL VIGOROUS TESTS PASSED SUCCESSFULLY! No slacking detected.")

if __name__ == "__main__":
    main()
