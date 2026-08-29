"""
pipeline/detection_pipeline.py — Step 4: real detection pipeline.

Replaces the placeholder logic from IngestionPipeline with the full chain:
    source → FrameSampler → YoloPlateDetector → crop → PaddleOcrEngine → DB

Writes *real* detection rows (object_type='license_plate', confidence from
YOLO, actual bbox, optional saved crop image) instead of the
`mock_frame_sample` placeholders from Step 3.

All heavy components (detector, OCR engine, camera source) are injected
via constructor — the pipeline itself holds zero model-loading logic,
keeping it testable and swap-ready for Step 8.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional, Any

import cv2
import numpy as np

from sources.base_camera_source import BaseCameraSource
from detection.base_detector import BaseDetector
from detection.base_ocr_engine import BaseOcrEngine
from detection.frame_sampler import FrameSampler
from db.dao_cameras import get_camera_by_id, insert_camera
from db.dao_detections import insert_detection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("detection_pipeline")

MAX_CROPS_PER_CAMERA = 5000  # oldest crops are pruned once a camera exceeds this


class DetectionPipeline:
    """
    Reads frames from a camera source, runs plate detection + OCR on
    sampled frames, and persists results to the `detections` table.

    Usage:
        source = MockVideoSource(camera_id=1, video_path=...)
        detector = YoloPlateDetector()
        detector.load_model("models/plate_yolov8n.pt")
        ocr = PaddleOcrEngine()
        ocr.load_model()

        pipeline = DetectionPipeline(
            camera_id=1,
            source=source,
            detector=detector,
            ocr_engine=ocr,
        )
        pipeline.ensure_camera_row("Gate Camera", "rtsp://...")
        pipeline.run()
    """

    def __init__(
        self,
        camera_id: int,
        source: BaseCameraSource,
        detector: BaseDetector,
        ocr_engine: BaseOcrEngine,
        rule_engine: Optional[Any] = None,
        perf_counter: Optional[Any] = None,
        sample_interval: int = 10,
        max_frames: Optional[int] = None,
        min_detection_confidence: float = 0.4,
        min_ocr_confidence: float = 0.5,
        save_crops: bool = False,
        crop_dir: str = "data/crops",
        crop_padding: int = 8,
    ):
        """
        Args:
            camera_id:                DB camera FK.
            source:                   Any BaseCameraSource implementation.
            detector:                 Any BaseDetector (model already loaded).
            ocr_engine:               Any BaseOcrEngine (model already loaded).
            rule_engine:              Optional rule processing engine.
            perf_counter:             Optional PerfCounter for FPS/latency metrics.
            sample_interval:          Run detection every N frames (1 = every frame).
            max_frames:               Stop after N frames total (None = run forever).
            min_detection_confidence: Drop YOLO boxes below this threshold.
            min_ocr_confidence:       Drop OCR reads below this threshold.
            save_crops:               If True, save cropped plate images to disk.
            crop_dir:                 Where to save crop images.
            crop_padding:             Extra pixels around crop to help OCR.
        """
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.ocr_engine = ocr_engine
        self.rule_engine = rule_engine
        self.perf_counter = perf_counter
        self.min_detection_confidence = min_detection_confidence
        self.min_ocr_confidence = min_ocr_confidence
        self.save_crops = save_crops
        self.crop_dir = Path(crop_dir)
        self.crop_padding = crop_padding
        self.max_frames = max_frames

        self._sampler = FrameSampler(sample_interval=sample_interval)

        # Counters — exposed as properties for tests / metrics.
        self._frames_read = 0
        self._frames_processed = 0
        self._detections_written = 0
        self._ocr_reads = 0
        self.camera_location = None

    # ------------------------------------------------------------------
    # Camera row helper (same pattern as IngestionPipeline)
    # ------------------------------------------------------------------
    def ensure_camera_row(self, name: str, stream_url: str) -> None:
        """
        Guarantees a `cameras` row exists for self.camera_id before the
        pipeline starts inserting detection rows that FK-reference it.
        """
        existing = get_camera_by_id(self.camera_id)
        if existing is None:
            new_id = insert_camera(name=name, stream_url=stream_url, status="active")
            logger.info(
                f"No camera row for camera_id={self.camera_id}; "
                f"inserted new row id={new_id}."
            )
            self.camera_id = new_id
            self.source.camera_id = new_id
            self.camera_location = None
        else:
            logger.info(
                f"Camera row confirmed: {existing['name']} "
                f"(status={existing['status']})"
            )
            self.camera_location = existing.get("location")

    # ------------------------------------------------------------------
    # Crop persistence (optional — nice for demo, not required)
    # ------------------------------------------------------------------
    def _save_crop_image(self, crop: np.ndarray) -> Optional[str]:
        """Save a crop to disk and return the relative path, or None."""
        if not self.save_crops:
            return None
        if crop.size == 0:
            return None

        self.crop_dir.mkdir(parents=True, exist_ok=True)

        # Retention policy: prune oldest crops periodically (every 100 detections)
        # to avoid an expensive O(N log N) glob on every single detection.
        if self._detections_written % 100 == 0:
            existing = sorted(self.crop_dir.glob(f"cam{self.camera_id}_*.jpg"))
            while len(existing) >= MAX_CROPS_PER_CAMERA:
                oldest = existing.pop(0)
                try:
                    oldest.unlink()
                except OSError as e:
                    logger.warning(f"Could not prune old crop {oldest}: {e}")
                    continue  # skip locked files, try the next one

        filename = f"cam{self.camera_id}_{int(time.time() * 1000)}.jpg"
        filepath = self.crop_dir / filename
        if not cv2.imwrite(str(filepath), crop):
            logger.warning(f"cv2.imwrite failed for {filepath}")
            return None
        return str(filepath)

    # ------------------------------------------------------------------
    # Single-frame processing
    # ------------------------------------------------------------------
    def _process_frame(self, frame: np.ndarray) -> None:
        """
        Run detection + OCR on a single frame and persist results.

        For each bounding box YOLO returns:
          1. Filter by min_detection_confidence.
          2. Crop the plate region (with padding).
          3. Run OCR on the crop.
          4. Filter by min_ocr_confidence.
          5. Write the result to the `detections` table.
        """
        self._frames_processed += 1
        boxes = self.detector.detect(frame)

        for box in boxes:
            # --- Confidence gate ---
            if box.confidence < self.min_detection_confidence:
                continue

            # --- Crop the plate region ---
            crop = FrameSampler.crop_region(
                frame,
                box.x1, box.y1,
                box.x2, box.y2,
                padding=self.crop_padding,
            )
            if crop.size == 0:
                continue

            # --- OCR the crop ---
            ocr_result = self.ocr_engine.read_text(crop)

            # Determine the object_type and confidence to write.
            # If OCR succeeds, we use the plate text; otherwise we still
            # record the detection as "plate_detected_no_ocr" so the
            # alert pipeline (Step 5) can see that something was found
            # even if the text was unreadable.
            plate_text: Optional[str] = None
            if ocr_result is not None and ocr_result.confidence >= self.min_ocr_confidence:
                object_type = "license_plate"
                plate_text = ocr_result.text
                combined_confidence = round(box.confidence * ocr_result.confidence, 4)
                self._ocr_reads += 1
            else:
                object_type = "plate_detected_no_ocr"
                combined_confidence = round(box.confidence, 4)

            # --- Persist crop image (optional) ---
            image_path = self._save_crop_image(crop)

            # --- Write to DB ---
            bbox_x = int(box.x1)
            bbox_y = int(box.y1)
            bbox_w = int(box.x2 - box.x1)
            bbox_h = int(box.y2 - box.y1)

            detection_id = insert_detection(
                camera_id=self.camera_id,
                object_type=object_type,
                confidence=combined_confidence,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_w=bbox_w,
                bbox_h=bbox_h,
                image_path=image_path,
                plate_text=plate_text,
                location=self.camera_location,
            )
            self._detections_written += 1

            # Mask the plate text for PII security in logs (e.g. GJ02EC7324 -> GJ02***324)
            masked_plate = None
            if plate_text:
                if len(plate_text) >= 6:
                    masked_plate = f"{plate_text[:4]}***{plate_text[-3:]}"
                else:
                    masked_plate = "***"
                    
            logger.info(
                f"[cam {self.camera_id}] detection_id={detection_id} "
                f"type={object_type!r} plate_text={masked_plate!r} conf={combined_confidence} "
                f"bbox=({bbox_x},{bbox_y},{bbox_w},{bbox_h})"
            )
            
            # Step 5: Evaluate detection for alerts
            if self.rule_engine and plate_text:
                self.rule_engine.process_detection(
                    detection_id=detection_id,
                    camera_id=self.camera_id,
                    plate_text=plate_text
                )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """
        Connect to the camera source and run the detection loop until
        the source is exhausted or max_frames is reached.
        """
        self.source.connect()

        logger.info(
            f"DetectionPipeline started for camera_id={self.camera_id} "
            f"(sample_interval={self._sampler.sample_interval}, "
            f"max_frames={self.max_frames})"
        )

        try:
            while True:
                if self.max_frames is not None and self._frames_read >= self.max_frames:
                    logger.info(f"Reached max_frames={self.max_frames}, stopping.")
                    break

                if self.perf_counter:
                    self.perf_counter.start_frame()

                frame = self.source.read_frame()
                if frame is None:
                    logger.warning("Source returned no frame. Stopping.")
                    break

                self._frames_read += 1

                if self._sampler.should_process(frame):
                    try:
                        self._process_frame(frame)
                    except Exception as e:
                        # e.g., mysql.connector.errors.IntegrityError from insert_detection
                        # when the parent camera is deleted by the API
                        logger.warning(f"Stopping pipeline for camera_id={self.camera_id} due to error (camera likely deleted): {e}")
                        break

                if self.perf_counter:
                    self.perf_counter.end_frame()
                    
                # Periodic memory cleanup to prevent deep learning model leaks
                if self._frames_read % 100 == 0:
                    import gc
                    gc.collect()
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except ImportError:
                        pass

        finally:
            self.source.release()
            logger.info(
                f"DetectionPipeline stopped. "
                f"frames_read={self._frames_read}, "
                f"frames_processed={self._frames_processed}, "
                f"detections_written={self._detections_written}, "
                f"ocr_reads={self._ocr_reads}"
            )

    # ------------------------------------------------------------------
    # Read-only stats (for metrics / tests)
    # ------------------------------------------------------------------
    @property
    def stats(self) -> dict:
        return {
            "frames_read": self._frames_read,
            "frames_processed": self._frames_processed,
            "detections_written": self._detections_written,
            "ocr_reads": self._ocr_reads,
        }


if __name__ == "__main__":
    # End-to-end smoke test: python pipeline/detection_pipeline.py
    # Requires:
    #   1. MySQL running, db/schema.sql applied
    #   2. A YOLO .pt model at the path below (or set YOLO_MODEL_PATH in .env)
    #   3. PaddleOCR installed
    import config
    from sources.mock_video_source import MockVideoSource
    from detection.yolo_plate_detector import YoloPlateDetector
    from detection.paddle_ocr_engine import PaddleOcrEngine

    CAMERA_ID = 1
    VIDEO_PATH = Path("data/mock_videos/camera_3_test_2.mp4")

    # --- Build components ---
    source = MockVideoSource(camera_id=CAMERA_ID, video_path=VIDEO_PATH, loop=False)

    detector = YoloPlateDetector()
    detector.load_model(config.YOLO_MODEL_PATH)

    ocr = PaddleOcrEngine()
    ocr.load_model()

    # --- Build pipeline ---
    pipeline = DetectionPipeline(
        camera_id=CAMERA_ID,
        source=source,
        detector=detector,
        ocr_engine=ocr,
        sample_interval=10,
        max_frames=240,
        save_crops=True,
    )
    pipeline.ensure_camera_row(
        name="Gate Camera (mock)",
        stream_url=str(VIDEO_PATH),
    )
    pipeline.run()

    print("\n--- Final stats ---")
    for k, v in pipeline.stats.items():
        print(f"  {k}: {v}")