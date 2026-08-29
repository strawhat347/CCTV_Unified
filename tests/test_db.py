"""
test_db.py — Manual end-to-end verification of the Step 2 DB layer.

This is NOT a formal pytest suite yet (that's Step 7) — it's a simple,
readable script you run directly to prove dao_cameras / dao_detections /
dao_alerts actually work against your live MySQL database.

Run it from the project root with:
    python tests/test_db.py
"""

from db import dao_cameras, dao_detections, dao_alerts

def main():
    print("=== Step 2 DB Layer Verification ===\n")

    # ------------------------------------------------------------------
    # 1. Insert a test camera
    # ------------------------------------------------------------------
    camera_id = dao_cameras.insert_camera(
        name="TEST_CAM_01",
        stream_url="mock://test_video.mp4",
        location="Test Location",
        status="active",
    )
    print(f"[1] Inserted camera -> camera_id = {camera_id}")

    # Track IDs for cleanup
    detection_id = None
    alert_id = None

    try:
        fetched_camera = dao_cameras.get_camera_by_id(camera_id)
        print(f"    Fetched back: {fetched_camera}\n")
        assert fetched_camera is not None, "Camera fetch failed!"
        assert fetched_camera["name"] == "TEST_CAM_01", "Camera name mismatch!"

        # ------------------------------------------------------------------
        # 2. Insert a test detection tied to that camera
        # ------------------------------------------------------------------
        detection_id = dao_detections.insert_detection(
            camera_id=camera_id,
            object_type="plate",
            confidence=0.93,
            bbox_x=100,
            bbox_y=150,
            bbox_w=80,
            bbox_h=30,
            image_path=None,
        )
        print(f"[2] Inserted detection -> detection_id = {detection_id}")

        fetched_detection = dao_detections.get_detection_by_id(detection_id)
        print(f"    Fetched back: {fetched_detection}\n")
        assert fetched_detection is not None, "Detection fetch failed!"
        assert fetched_detection["camera_id"] == camera_id, "FK camera_id mismatch!"

        # ------------------------------------------------------------------
        # 3. Insert a test alert tied to that detection
        # ------------------------------------------------------------------
        alert_id = dao_alerts.insert_alert(
            camera_id=camera_id,
            alert_type="blacklist_match",
            severity="high",
            message="TEST ALERT - plate matched blacklist (this is test data)",
            detection_id=detection_id,
        )
        print(f"[3] Inserted alert -> alert_id = {alert_id}")

        fetched_alert = dao_alerts.get_alert_by_id(alert_id)
        print(f"    Fetched back: {fetched_alert}\n")
        assert fetched_alert is not None, "Alert fetch failed!"
        assert fetched_alert["acknowledged"] == 0, "New alert should be unacknowledged!"

        # ------------------------------------------------------------------
        # 4. Exercise a couple of the "list" queries too
        # ------------------------------------------------------------------
        recent_detections = dao_detections.get_recent_detections(limit=5)
        print(f"[4] get_recent_detections(limit=5) returned {len(recent_detections)} row(s)")

        open_alerts = dao_alerts.get_unacknowledged_alerts(limit=5)
        print(f"    get_unacknowledged_alerts(limit=5) returned {len(open_alerts)} row(s)\n")

        # ------------------------------------------------------------------
        # 5. Exercise acknowledge_alert
        # ------------------------------------------------------------------
        ack_result = dao_alerts.acknowledge_alert(alert_id)
        print(f"[5] acknowledge_alert({alert_id}) -> {ack_result}")
        fetched_alert_after_ack = dao_alerts.get_alert_by_id(alert_id)
        print(f"    acknowledged now = {fetched_alert_after_ack['acknowledged']}\n")
        assert fetched_alert_after_ack["acknowledged"] == 1, "Acknowledge did not persist!"

        print("\n=== ALL CHECKS PASSED — Step 2 DB layer verified end-to-end ===")

    finally:
        # ------------------------------------------------------------------
        # 6. Cleanup - always runs even if assertions fail
        # ------------------------------------------------------------------
        print("\n[6] Cleaning up test data...")
        if alert_id is not None:
            print(f"    delete_alert     -> {dao_alerts.delete_alert(alert_id)}")
        if detection_id is not None:
            print(f"    delete_detection -> {dao_detections.delete_detection(detection_id)}")
        print(f"    delete_camera    -> {dao_cameras.delete_camera(camera_id)}")


if __name__ == "__main__":
    main()