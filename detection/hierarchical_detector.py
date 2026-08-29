"""
detection/hierarchical_detector.py — Two-stage coarse-to-fine detector.

Stage 1 (Vehicle Detection):
    Uses a COCO-pretrained YOLO model (yolov8n.pt) at 640px to quickly
    locate vehicles (car, motorcycle, bus, truck) in the full frame.
    Runtime: ~15ms on RTX 3050.

Stage 2 (Plate Detection):
    Crops each vehicle bounding box (with padding) from the *raw
    full-resolution* frame and runs the custom plate detector on each
    crop at native resolution — effectively "zooming in" on each vehicle.
    Runtime: ~10ms per vehicle.

Fallback:
    If Stage 1 finds zero vehicles (e.g. the image is a standalone plate
    photo, or the vehicle is partially occluded), falls back to the
    TiledPlateDetector to ensure no plates are missed.

Implements BaseDetector so it's a drop-in replacement everywhere.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
import torch
from ultralytics import YOLO
from pathlib import Path

from detection.base_detector import BaseDetector, BoundingBox
from detection.tiled_plate_detector import TiledPlateDetector
from detection.yolo_plate_detector import YoloPlateDetector

logger = logging.getLogger(__name__)


class HierarchicalDetector(BaseDetector):
    """
    Two-stage vehicle → plate detector with tiled fallback.

    Usage::

        detector = HierarchicalDetector(
            vehicle_model_path="yolov8n.pt",
            vehicle_classes=[2, 3, 5, 7],  # car, motorcycle, bus, truck
        )
        detector.load_model("runs/detect/.../best.pt")  # plate model
        boxes = detector.detect(frame)  # returns plate BoundingBoxes
    """

    def __init__(
        self,
        vehicle_model_path: str = "yolov8n.pt",
        vehicle_classes: list[int] | None = None,
        vehicle_conf: float = 0.30,
        vehicle_imgsz: int = 640,
        vehicle_padding: float = 0.20,
        plate_conf: float = 0.25,
        plate_iou_threshold: float = 0.5,
        device: str | None = None,
        # Motorcycle-specific multi-scale settings
        motorcycle_classes: list[int] | None = None,
        motorcycle_plate_conf: float = 0.12,
        motorcycle_imgsz_scales: list[int] | None = None,
        motorcycle_extra_padding: float = 0.30,
        # Fallback tiled detector settings
        fallback_tile_size: int = 1280,
        fallback_overlap: float = 0.2,
        fallback_full_frame_imgsz: int = 2560,
        ocr_engine: Any | None = None,
    ):
        """
        Args:
            vehicle_model_path:  Path to COCO-pretrained YOLO weights.
            vehicle_classes:     COCO class IDs to treat as vehicles.
                                 Default: [2, 3, 5, 7] (car, motorcycle, bus, truck).
            vehicle_conf:        Confidence threshold for vehicle detection.
            vehicle_imgsz:       Inference size for vehicle detection (keep small for speed).
            vehicle_padding:     Fractional padding around each vehicle box
                                 (0.20 = 20% on each side).
            plate_conf:          Confidence threshold for plate detection.
            plate_iou_threshold: NMS IoU threshold for plate merging.
            device:              Torch device string or None for auto.
            motorcycle_classes:  COCO class IDs for motorcycles/scooters.
                                 Default: [3] (motorcycle).  These get a
                                 deeper multi-scale scan because 2-wheeler
                                 front plates are small, angled, and often
                                 mounted on curved cowls.
            motorcycle_plate_conf: Lower confidence threshold for plate
                                 detection on motorcycle crops (default 0.12).
            motorcycle_imgsz_scales: List of imgsz values to try on each
                                 motorcycle crop (default: [640, 1024, 1280]).
                                 The best detection across scales is kept.
            motorcycle_extra_padding: Extra padding for motorcycle crops
                                 (default 0.30 = 30%) to capture front
                                 plates that extend beyond the vehicle bbox.
            fallback_tile_size:  Tile size for the fallback TiledPlateDetector.
            fallback_overlap:    Overlap ratio for fallback tiling.
            fallback_full_frame_imgsz: Full-frame imgsz for fallback.
            ocr_engine:          Shared BaseOcrEngine instance for sliding-window fallback.
        """
        if vehicle_classes is None:
            vehicle_classes = [2, 3, 5, 7]
        if motorcycle_classes is None:
            motorcycle_classes = [3]
        if motorcycle_imgsz_scales is None:
            motorcycle_imgsz_scales = [640, 1024, 1280]

        self.vehicle_model_path = vehicle_model_path
        self.vehicle_classes = vehicle_classes
        self.vehicle_conf = vehicle_conf
        self.vehicle_imgsz = vehicle_imgsz
        self.vehicle_padding = vehicle_padding
        self.plate_conf = plate_conf
        self.plate_iou_threshold = plate_iou_threshold
        self.ocr_engine = ocr_engine

        # Motorcycle-specific
        self.motorcycle_classes = set(motorcycle_classes)
        self.motorcycle_plate_conf = motorcycle_plate_conf
        self.motorcycle_imgsz_scales = motorcycle_imgsz_scales
        self.motorcycle_extra_padding = motorcycle_extra_padding

        if device is None:
            import config
            self.device = "cuda:0" if config.should_use_gpu() else "cpu"
        else:
            self.device = device

        self._vehicle_model: YOLO | None = None
        self._plate_detector = YoloPlateDetector(device=self.device)

        # Fallback tiled detector (lazy-initialised on first use)
        self._fallback_tile_size = fallback_tile_size
        self._fallback_overlap = fallback_overlap
        self._fallback_full_frame_imgsz = fallback_full_frame_imgsz
        self._fallback: TiledPlateDetector | None = None
        self._fallback_lock = threading.Lock()

    # ------------------------------------------------------------------
    # BaseDetector interface
    # ------------------------------------------------------------------
    def load_model(self, model_path: str) -> None:
        """Load both vehicle and plate models."""
        # Vehicle model (COCO pretrained)
        vp = Path(self.vehicle_model_path)
        if not vp.exists():
            raise FileNotFoundError(
                f"Vehicle model not found: {self.vehicle_model_path}"
            )
        self._vehicle_model = YOLO(str(vp))
        logger.info(f"Vehicle model loaded: {vp} on {self.device}")

        # Plate model (custom trained)
        self._plate_detector.load_model(model_path)
        logger.info(f"Plate model loaded: {model_path} on {self.device}")

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Two-stage detection:
        1. Find vehicles in the full frame (fast, low-res).
        2. Crop each vehicle at native resolution and detect plates.
        3. If no vehicles found, fall back to tiled scanning.
        """
        if self._vehicle_model is None:
            raise RuntimeError("Models not loaded. Call load_model() first.")

        # --- Stage 1: Vehicle detection ---
        # Dynamically boost vehicle detection resolution for high-res images
        # (e.g. 4K/8K photos) so distant cars don't disappear when squashed.
        h, w = frame.shape[:2]
        max_dim = max(h, w)
        dynamic_imgsz = self.vehicle_imgsz
        if max_dim > 3000:
            dynamic_imgsz = min(1920, (max_dim // 32) * 32)
            logger.debug(f"High-res input ({w}x{h}), boosting vehicle_imgsz to {dynamic_imgsz}")

        vehicle_boxes = self._detect_vehicles(frame, imgsz=dynamic_imgsz)

        if not vehicle_boxes:
            # Fallback: no vehicles visible — use tiled detector
            logger.debug("No vehicles detected → falling back to tiled scan")
            return self._run_fallback(frame)

        logger.debug(f"Found {len(vehicle_boxes)} vehicle(s) → cropping for plates")

        # --- Stage 2: Plate detection on each vehicle crop ---
        h, w = frame.shape[:2]
        all_plates: list[BoundingBox] = []

        for vbox in vehicle_boxes:
            # --- Motorcycle multi-scale deep scan ---
            is_motorcycle = vbox.class_id in self.motorcycle_classes

            # Use extra padding for motorcycles (front plates often extend
            # beyond the COCO bbox which focuses on the body/rider)
            padding = (
                self.motorcycle_extra_padding if is_motorcycle
                else self.vehicle_padding
            )

            # Compute padded vehicle crop coordinates
            vw = vbox.x2 - vbox.x1
            vh = vbox.y2 - vbox.y1
            pad_x = vw * padding
            pad_y = vh * padding

            cx1 = max(0, int(vbox.x1 - pad_x))
            cy1 = max(0, int(vbox.y1 - pad_y))
            cx2 = min(w, int(vbox.x2 + pad_x))
            cy2 = min(h, int(vbox.y2 + pad_y))

            crop = frame[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue

            if is_motorcycle:
                plate_boxes = self._detect_plates_multiscale(
                    crop,
                    scales=self.motorcycle_imgsz_scales,
                    conf=self.motorcycle_plate_conf,
                )
                logger.debug(
                    f"Multi-scale scan: {len(plate_boxes)} plate(s) "
                    f"at scales {self.motorcycle_imgsz_scales}"
                )
            else:
                plate_boxes = self._plate_detector.detect(
                    crop, conf=self.plate_conf
                )

            # Remap crop-local coordinates back to full-frame coordinates
            for pbox in plate_boxes:
                all_plates.append(
                    BoundingBox(
                        x1=pbox.x1 + cx1,
                        y1=pbox.y1 + cy1,
                        x2=pbox.x2 + cx1,
                        y2=pbox.y2 + cy1,
                        confidence=pbox.confidence,
                        class_id=pbox.class_id,
                        class_name=pbox.class_name,
                    )
                )

        if len(all_plates) > 1:
            all_plates = TiledPlateDetector._nms(all_plates, self.plate_iou_threshold)

        return all_plates

    def get_config(self) -> dict[str, Any]:
        return {
            "type": "HierarchicalDetector",
            "vehicle_model_path": self.vehicle_model_path,
            "vehicle_classes": self.vehicle_classes,
            "vehicle_conf": self.vehicle_conf,
            "vehicle_imgsz": self.vehicle_imgsz,
            "vehicle_padding": self.vehicle_padding,
            "plate_conf": self.plate_conf,
            "motorcycle_classes": list(self.motorcycle_classes),
            "motorcycle_plate_conf": self.motorcycle_plate_conf,
            "motorcycle_imgsz_scales": self.motorcycle_imgsz_scales,
            "motorcycle_extra_padding": self.motorcycle_extra_padding,
            "device": self.device,
            "plate_detector": self._plate_detector.get_config(),
        }

    # ------------------------------------------------------------------
    # Motorcycle multi-scale plate scan
    # ------------------------------------------------------------------
    def _detect_plates_multiscale(
        self,
        crop: np.ndarray,
        scales: list[int],
        conf: float,
    ) -> list[BoundingBox]:
        """
        Run plate detection on *crop* at multiple ``imgsz`` values and
        merge results.

        Motorcycle front plates are notoriously hard to detect at a single
        scale because they vary wildly in apparent size (handlebar sticker
        vs mudguard plate vs rear plate).  Running at 640, 1024, and 1280
        ensures at least one scale captures the plate's feature signature.

        If YOLO finds nothing at any scale, falls back to an OCR-assisted
        sliding-window scan over the bottom 60% of the motorcycle crop
        (where plates are typically mounted).

        Returns deduplicated plates via NMS.
        """
        all_boxes: list[BoundingBox] = []

        for scale in scales:
            boxes = self._plate_detector.detect(
                crop, imgsz=scale, conf=conf,
            )
            all_boxes.extend(boxes)

        if len(all_boxes) > 1:
            all_boxes = TiledPlateDetector._nms(
                all_boxes, self.plate_iou_threshold,
            )

        # --- OCR-assisted sliding window fallback ---
        if not all_boxes and self.ocr_engine is not None:
            ocr_boxes = self._ocr_sliding_window_scan(crop)
            all_boxes.extend(ocr_boxes)

        return all_boxes

    def _ocr_sliding_window_scan(
        self,
        crop: np.ndarray,
    ) -> list[BoundingBox]:
        """
        Run OCR on the bottom 70% of the motorcycle crop as a last-resort fallback.
        Avoids sliding windows to prevent severe latency on CPU (Issue 8), and uses
        the BaseOcrEngine.read_text abstraction (Issue 9).
        """
        # Imports used by fallback — kept at method scope to avoid circular
        # imports but only evaluated once per call, not per iteration.
        import re
        import cv2 as _cv2
        from detection.plate_preprocessor import PlatePreprocessor

        h, w = crop.shape[:2]
        if h < 20 or w < 20:
            return []

        # Indian plate regex: 2 alpha + 1-2 digits + 0-3 alpha/digit + 3-4 digits
        plate_pattern = re.compile(
            r'^[A-Z]{2}\d{1,2}[A-Z0-9]{0,3}\d{3,4}$'
        )

        pp = PlatePreprocessor()

        if self.ocr_engine is None:
            return []

        # Just take the bottom 70% instead of hundreds of sliding windows
        scan_top = int(h * 0.3)
        window = crop[scan_top:h, 0:w]
        if window.shape[0] < 10 or window.shape[1] < 10:
            return []

        # Try two approaches and keep the best match:
        # 1. Simple 2x bicubic upscale
        # 2. Full preprocessor
        candidates = [
            _cv2.resize(window, (0, 0), fx=2, fy=2, interpolation=_cv2.INTER_CUBIC),
            pp.preprocess(window),
        ]

        best_conf = 0.0
        best_text = ""

        for enhanced in candidates:
            # Use proper abstraction instead of direct engine access
            result = self.ocr_engine.read_text(enhanced)
            if not result:
                continue

            cleaned = re.sub(r'[^A-Za-z0-9]', '', result.text).upper()
            if len(cleaned) < 6 or cleaned in ('IND', 'INDIA', 'IN'):
                continue

            if plate_pattern.match(cleaned) and result.confidence > best_conf:
                best_conf = result.confidence
                best_text = cleaned

        if best_text:
            logger.info(
                f"OCR fallback found plate: {best_text!r} conf={best_conf:.3f} "
                f"in bottom 70% region"
            )
            # Create a synthetic bounding box covering the scanned area
            box = BoundingBox(
                x1=0.0,
                y1=float(scan_top),
                x2=float(w),
                y2=float(h),
                confidence=float(best_conf) * 0.5,
                class_id=0,
                class_name="license_plate",
            )
            return [box]

        return []

    # ------------------------------------------------------------------
    # Stage 1: Vehicle detection
    # ------------------------------------------------------------------
    def _detect_vehicles(self, frame: np.ndarray, imgsz: int | None = None) -> list[BoundingBox]:
        """Run COCO YOLO on the frame and filter to vehicle classes only."""
        inference_imgsz = imgsz if imgsz is not None else self.vehicle_imgsz
        results = self._vehicle_model(
            frame,
            device=self.device,
            imgsz=inference_imgsz,
            conf=self.vehicle_conf,
            classes=self.vehicle_classes,
            verbose=False,
        )

        boxes: list[BoundingBox] = []
        if not results:
            return boxes

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = self._vehicle_model.names.get(class_id, "vehicle")

            boxes.append(
                BoundingBox(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=confidence,
                    class_id=class_id,
                    class_name=class_name,
                )
            )

        return boxes

    # ------------------------------------------------------------------
    # Fallback: tiled detection (lazy init)
    # ------------------------------------------------------------------
    def _run_fallback(self, frame: np.ndarray) -> list[BoundingBox]:
        """Lazy-init and run the TiledPlateDetector fallback."""
        if self._fallback is None:
            with self._fallback_lock:
                if self._fallback is None:
                    fallback = TiledPlateDetector(
                        tile_size=self._fallback_tile_size,
                        overlap_ratio=self._fallback_overlap,
                        conf_threshold=self.plate_conf,
                        iou_threshold=self.plate_iou_threshold,
                        full_frame_pass=True,
                        full_frame_imgsz=self._fallback_full_frame_imgsz,
                        device=self.device,
                        vehicle_merge=False,
                    )
                    # Share the already-loaded plate model
                    fallback._yolo = self._plate_detector
                    logger.info("Fallback TiledPlateDetector initialised (model shared)")
                    self._fallback = fallback

        return self._fallback.detect(frame)
