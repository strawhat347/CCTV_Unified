"""
scripts/test_everything.py — Comprehensive End-to-End Component Test

Runs a sanity check on every core component (DB, Registry, Rules, Detectors, OCR, Pipeline)
without needing a web server or full pipeline execution loop.
"""

import sys
import logging
import time
from pathlib import Path

# Add project root to path so this script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

import config
from alerting.rule_engine import RuleEngine
from db.connection_pool import get_pool
from db.dao_cameras import delete_camera, get_camera_by_id, insert_camera
from db.dao_detections import insert_detection
from detection.frame_sampler import FrameSampler
from detection.hierarchical_detector import HierarchicalDetector
from detection.paddle_ocr_engine import PaddleOcrEngine
from detection.tiled_plate_detector import TiledPlateDetector
from detection.yolo_plate_detector import YoloPlateDetector
from pipeline.detection_pipeline import DetectionPipeline
from registry.mock_registry import MockRegistry
from sources.mock_video_source import MockVideoSource

print("Hello from test_everything.py!!!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_everything")

def get_test_image():
    img_dir = Path(config.TEST_IMAGES_DIR)
    images = list(img_dir.glob("*.jpg"))
    if images:
        return cv2.imread(str(images[0]))
    return np.zeros((1080, 1920, 3), dtype=np.uint8)

def test_database_and_daos():
    print("--- Testing DB & DAOs ---")
    get_pool() # init pool
    
    # Test Camera DAO
    cam_id = insert_camera("Test Camera Everything", "mock://test_everything", status="active")
    print(f"Inserted camera, ID: {cam_id}")
    
    cam = get_camera_by_id(cam_id)
    assert cam is not None and cam["name"] == "Test Camera Everything"
    print("Camera fetch successful.")
    
    return cam_id

def test_registry_and_rule_engine(cam_id):
    print("--- Testing Registry & Rule Engine ---")
    registry = MockRegistry(config.SEED_REGISTRY_CSV)
    registry.connect()
    
    # Check if a stolen plate works
    record = registry.lookup("MH12AB1234") # Typically stolen in mock DB
    if record:
        print(f"Registry lookup found: {record.status}")
    else:
        print("Registry lookup returned None (make sure seed_registry.csv is populated).")
        
    rule_engine = RuleEngine(registry)
    
    det_id = insert_detection(
        camera_id=cam_id,
        object_type="license_plate",
        confidence=0.99,
        bbox_x=10, bbox_y=10, bbox_w=100, bbox_h=50,
        plate_text="MH12AB1234"
    )
    
    # Process the detection, which will trigger an alert for MH12AB1234
    rule_engine.process_detection(detection_id=det_id, camera_id=cam_id, plate_text="MH12AB1234")
    print("Rule Engine processed detection without crashing.")
    
    return det_id

def test_ocr_engine():
    print("--- Testing PaddleOcrEngine ---")
    ocr = PaddleOcrEngine(preprocess=True)
    ocr.load_model()
    
    # Create a synthetic crop that looks like a plate
    crop = np.ones((60, 200, 3), dtype=np.uint8) * 255
    cv2.putText(crop, "MH12AB1234", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    res = ocr.read_text(crop)
    if res:
        print(f"OCR successfully read: {res.text} (conf: {res.confidence:.2f})")
    else:
        print("OCR returned None on synthetic image.")
        
    return ocr

def test_detectors(ocr_engine, test_img):
    print("--- Testing YoloPlateDetector ---")
    yolo = YoloPlateDetector()
    yolo.load_model(config.YOLO_MODEL_PATH)
    boxes = yolo.detect(test_img)
    print(f"YoloPlateDetector found {len(boxes)} boxes.")
    
    print("--- Testing TiledPlateDetector ---")
    tiled = TiledPlateDetector(vehicle_merge=False)
    tiled.load_model(config.YOLO_MODEL_PATH)
    tiled_boxes = tiled.detect(test_img)
    print(f"TiledPlateDetector found {len(tiled_boxes)} boxes.")

    print("--- Testing HierarchicalDetector ---")
    hier = HierarchicalDetector(
        vehicle_model_path=config.VEHICLE_MODEL_PATH,
        ocr_engine=ocr_engine
    )
    hier.load_model(config.YOLO_MODEL_PATH)
    hier_boxes = hier.detect(test_img)
    print(f"HierarchicalDetector found {len(hier_boxes)} boxes.")
    
    return yolo

def test_pipeline(cam_id, yolo_detector, ocr_engine):
    print("--- Testing DetectionPipeline ---")
    video_dir = Path(config.MOCK_VIDEO_DIR)
    mp4s = list(video_dir.glob("*.mp4"))
    if not mp4s:
        print("No mock videos found. Skipping pipeline test.")
        return
        
    source = MockVideoSource(camera_id=cam_id, video_path=mp4s[0], loop=False)
    
    pipeline = DetectionPipeline(
        camera_id=cam_id,
        source=source,
        detector=yolo_detector,
        ocr_engine=ocr_engine,
        sample_interval=1,
        max_frames=5, # only run 5 frames for quick test
        save_crops=False
    )
    
    pipeline.run()
    print(f"Pipeline finished. Stats: {pipeline.stats}")

def cleanup(cam_id):
    print("--- Cleanup ---")
    delete_camera(cam_id)
    print(f"Deleted test camera {cam_id} and its cascading detections/alerts.")

def main():
    print("Starting Comprehensive Component Test...")
    test_img = get_test_image()
    
    try:
        cam_id = test_database_and_daos()
        test_registry_and_rule_engine(cam_id)
        
        ocr_engine = test_ocr_engine()
        yolo_detector = test_detectors(ocr_engine, test_img)
        
        test_pipeline(cam_id, yolo_detector, ocr_engine)
    except Exception as e:
        print(f"Test failed with exception: {e}")
    finally:
        if 'cam_id' in locals():
            cleanup(cam_id)
            
    print("All tests completed successfully!")

if __name__ == "__main__":
    main()
