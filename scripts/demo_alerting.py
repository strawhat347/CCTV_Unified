"""
scripts/demo_alerting.py - Quickly test the alerting engine on a specific plate.
"""
import sys
import logging
from pathlib import Path

# Add project root to path so this script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from registry.mock_registry import MockRegistry
from alerting.rule_engine import RuleEngine

# Enable logging to see the output
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.demo_alerting <PLATE_NUMBER>")
        print("Example: python -m scripts.demo_alerting MH12AB1234")
        sys.exit(1)
        
    plate_text = sys.argv[1]
    
    # 1. Load the mock registry (reads from data/seed_registry.csv)
    registry = MockRegistry()
    registry.connect()
    
    record = registry.lookup(plate_text)
    if record:
        print(f"\n[Registry] Found {plate_text}: Status is '{record.status}'. Flags: {record.flags}")
    else:
        print(f"\n[Registry] Plate {plate_text} not found in the database. (No alert will fire)")
    
    print("\n--- Sending to Rule Engine ---")
    
    # 2. Fire the rule engine
    engine = RuleEngine(registry)
    
    # We must provide a valid camera_id and detection_id for the foreign key constraints.
    # In the real pipeline, the DetectionPipeline creates these before calling the rule engine.
    # For this standalone demo, we will insert dummy ones into the database directly.
    from db.dao_cameras import insert_camera
    from db.dao_detections import insert_detection
    
    try:
        demo_cam_id = insert_camera("Demo Camera", "mock://demo", status="active")
        demo_det_id = insert_detection(
            camera_id=demo_cam_id, 
            object_type="license_plate", 
            confidence=0.99, 
            bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=50, 
            plate_text=plate_text
        )
        
        # This will trigger alert_dispatcher if the status is 'stolen' or 'flagged'
        engine.process_detection(detection_id=demo_det_id, camera_id=demo_cam_id, plate_text=plate_text)
        print("--- Done! Check the MySQL 'alerts' table if an alert was supposed to fire. ---\n")
    except Exception as e:
        print(f"Database error during demo setup: {e}")
        print("Make sure your MySQL database is running and schema is applied!")

if __name__ == "__main__":
    main()
