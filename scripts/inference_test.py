"""
inference_test.py — Visual inference test with annotated output images.

Uses HierarchicalDetector by default (vehicle→plate two-stage), with
automatic fallback to TiledPlateDetector when no vehicles are found.
Saves annotated images to runs/detect/predict_tiled/ for visual inspection.
"""

import sys
from pathlib import Path

# Add project root to path so this script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
from ultralytics.utils.plotting import Annotator

import config
from detection.tiled_plate_detector import TiledPlateDetector
from detection.hierarchical_detector import HierarchicalDetector

# Path to your freshly trained weights
MODEL_PATH = config.YOLO_MODEL_PATH
TEST_IMAGES_DIR = config.TEST_IMAGES_DIR

# Output directory for annotated images
OUTPUT_DIR = Path("runs/detect/predict_tiled")


def _build_detector():
    """Build the appropriate detector based on config."""
    if config.USE_HIERARCHICAL:
        print("[Mode] Hierarchical detector (vehicle → plate)")
        detector = HierarchicalDetector(
            vehicle_model_path=config.VEHICLE_MODEL_PATH,
            vehicle_classes=config.VEHICLE_CLASSES,
            vehicle_padding=config.VEHICLE_PADDING,
            plate_conf=0.25,
            plate_iou_threshold=0.5,
            fallback_tile_size=1280,
            fallback_overlap=0.2,
            fallback_full_frame_imgsz=2560,
        )
    else:
        print("[Mode] Tiled detector (SAHI-style)")
        detector = TiledPlateDetector(
            tile_size=1280,
            overlap_ratio=0.2,
            conf_threshold=0.25,
            iou_threshold=0.5,
            full_frame_pass=True,
            full_frame_imgsz=2560,
            vehicle_merge=True,
        )

    detector.load_model(MODEL_PATH)
    return detector


def main():
    detector = _build_detector()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(Path(TEST_IMAGES_DIR).glob("*"))
    image_paths = [p for p in image_paths if p.suffix.lower() in (".jpg", ".jpeg", ".png")]

    for img_path in image_paths:
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"\n{img_path.name}: could not read, skipping.")
            continue

        boxes = detector.detect(frame)

        h, w = frame.shape[:2]
        print(f"\nImage: {img_path.name} ({w}×{h})")
        if not boxes:
            print("  No plates detected.")
        else:
            for box in boxes:
                print(
                    f"  Detected plate - confidence: {box.confidence:.3f}, "
                    f"box: [{box.x1:.0f}, {box.y1:.0f}, {box.x2:.0f}, {box.y2:.0f}]"
                )

        # Draw bounding boxes and save annotated image.
        annotator = Annotator(frame)
        for box in boxes:
            annotator.box_label(
                [box.x1, box.y1, box.x2, box.y2],
                label=f"{box.confidence:.2f}",
            )
        out_path = OUTPUT_DIR / img_path.name
        cv2.imwrite(str(out_path), annotator.result())
        print(f"  Saved → {out_path}")


if __name__ == "__main__":
    main()
