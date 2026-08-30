"""
inference_with_ocr.py — Run detection + OCR together on a folder of test
images, and print exactly what plate text was read per detection.

This is the "full chain" version of inference_test.py — that script only
showed YOLO boxes/confidence, this one also runs the crop through
PaddleOCR so you can see the actual scanned text, same as what
detection_pipeline.py writes to the DB, but without needing MySQL running.

Uses HierarchicalDetector by default (vehicle→plate two-stage), with
automatic fallback to TiledPlateDetector when no vehicles are found.
Set USE_HIERARCHICAL=false in .env to force tiled-only mode.

After detection + OCR, results are deduplicated per vehicle: if multiple
bounding boxes on the same image produce the same plate text, only the
highest-confidence read is printed.
"""

import sys
from pathlib import Path

# Add project root to path so this script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

import config
from detection.frame_sampler import FrameSampler
from detection.hierarchical_detector import HierarchicalDetector
from detection.indian_plate_formatter import extract_indian_plate, normalize_plate_chars
from detection.paddle_ocr_engine import PaddleOcrEngine
from detection.tiled_plate_detector import TiledPlateDetector

# --- Paths ---
MODEL_PATH = config.YOLO_MODEL_PATH
TEST_IMAGES_DIR = config.TEST_IMAGES_DIR

# --- Thresholds (match your pipeline's defaults) ---
DET_CONF_THRESHOLD = 0.02   # Drastically lowered! Regex protects us from false positives.
CROP_PADDING = 4


def _build_detector(ocr_engine=None):
    """Build the appropriate detector based on config."""
    if config.USE_HIERARCHICAL:
        print("[Mode] Hierarchical detector (vehicle → plate → OCR)")
        detector = HierarchicalDetector(
            vehicle_model_path=config.VEHICLE_MODEL_PATH,
            vehicle_classes=config.VEHICLE_CLASSES,
            vehicle_padding=config.VEHICLE_PADDING,
            plate_conf=DET_CONF_THRESHOLD,
            motorcycle_plate_conf=DET_CONF_THRESHOLD,
            plate_iou_threshold=0.5,
            fallback_tile_size=1280,
            fallback_overlap=0.2,
            fallback_full_frame_imgsz=2560,
            ocr_engine=ocr_engine,
        )
    else:
        print("[Mode] Tiled detector (SAHI-style)")
        detector = TiledPlateDetector(
            tile_size=1280,
            overlap_ratio=0.2,
            conf_threshold=DET_CONF_THRESHOLD,
            iou_threshold=0.5,
            full_frame_pass=True,
            full_frame_imgsz=2560,
            vehicle_merge=True,
        )

    detector.load_model(MODEL_PATH)
    return detector


def main():
    if config.should_use_gpu():
        print("[Hardware] Using GPU (CUDA enabled)")
    else:
        print("[Hardware] Using CPU")

    from detection.paddle_ocr_engine import PaddleOcrEngine
    ocr_engine = PaddleOcrEngine(preprocess=True)
    ocr_engine.load_model()

    detector = _build_detector(ocr_engine)

    image_paths = sorted(Path(TEST_IMAGES_DIR).glob("*"))
    image_paths = [p for p in image_paths if p.suffix.lower() in (".jpg", ".jpeg", ".png")]

    if not image_paths:
        print(f"No images found in {TEST_IMAGES_DIR}")
        return

    for img_path in image_paths:
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"\n{img_path.name}: could not read image, skipping.")
            continue

        h, w = frame.shape[:2]
        print(f"\n--- {img_path.name} ({w}×{h}) ---")
        boxes = detector.detect(frame)

        if len(boxes) == 0:
            print("  No plate detected.")
            continue

        # --- Run OCR on each detected plate ---
        raw_reads = []
        for i, box in enumerate(boxes):
            crop = FrameSampler.crop_region(frame, box.x1, box.y1, box.x2, box.y2, padding=CROP_PADDING)
            if crop.size == 0:
                print(f"  Box {i}: det_conf={box.confidence:.3f} — empty crop, skipping OCR.")
                continue

            ocr_result = ocr_engine.read_text(crop)

            if ocr_result is None:
                raw_reads.append({
                    "box_idx": i,
                    "det_conf": box.confidence,
                    "plate_text": None,
                    "ocr_conf": 0.0,
                })
            else:
                raw_reads.append({
                    "box_idx": i,
                    "det_conf": box.confidence,
                    "plate_text": ocr_result.text,
                    "ocr_conf": ocr_result.confidence,
                })

        # --- Deduplicate: keep best read per unique plate text ---
        seen_plates: dict[str, dict] = {}
        no_ocr_reads = []

        for read in raw_reads:
            text = read["plate_text"]
            if text is None:
                no_ocr_reads.append(read)
                continue

            combined_conf = read["det_conf"] * read["ocr_conf"]
            if text not in seen_plates or combined_conf > seen_plates[text]["combined_conf"]:
                seen_plates[text] = {
                    **read,
                    "combined_conf": combined_conf,
                }

        # --- Print deduplicated results ---
        if not seen_plates and not no_ocr_reads:
            print("  No plates readable.")
            continue

        for plate_text, best in seen_plates.items():
            print(
                f"  Plate: {plate_text!r}  "
                f"(det_conf={best['det_conf']:.3f}, "
                f"ocr_conf={best['ocr_conf']:.3f}, "
                f"combined={best['combined_conf']:.3f})"
            )

        for read in no_ocr_reads:
            print(
                f"  Box {read['box_idx']}: det_conf={read['det_conf']:.3f}, "
                f"plate_text=<no OCR read>"
            )


if __name__ == "__main__":
    main()
