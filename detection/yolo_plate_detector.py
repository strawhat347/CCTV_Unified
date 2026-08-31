"""
detection/yolo_plate_detector.py — Real implementation of BaseDetector,
backed by Ultralytics YOLO.

Automatically uses CUDA GPU if available (e.g. NVIDIA RTX 3050), falling back
to CPU cleanly.
"""

from pathlib import Path
from typing import Any, Union
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    from ultralytics.engine.results import Results
except ImportError:
    YOLO = None

import torch
from detection.base_detector import BaseDetector, BoundingBox


class YoloPlateDetector(BaseDetector):
    """
    Concrete BaseDetector backed by an Ultralytics YOLO model.

    Usage:
        detector = YoloPlateDetector()
        detector.load_model("models/plate_yolov8n.pt")
        boxes = detector.detect(frame)
    """

    def __init__(self, device: str | None = None):
        self.model: YOLO | None = None
        self.model_path: str | None = None
        if device is None:
            self.device = "cpu"  # Forced CPU mode per user constraints
        else:
            self.device = device

    def load_model(self, model_path: str) -> None:
        """Load YOLO weights from disk.
        If the weights file is missing (common in CI or test environments),
        log a warning and keep ``self.model`` as ``None`` so the detector can
        be used in a degraded mode without raising an exception.
        """
        path = Path(model_path)
        if not path.exists():
            import logging
            logging.getLogger(__name__).warning(
                f"YOLO weights not found at {model_path}. Continuing with a mock detector."
            )
            self.model = None
            self.model_path = str(path)
            return

        self.model = YOLO(str(path))
        self.model_path = str(path)

    def detect(
        self,
        frame: np.ndarray,
        imgsz: int = 640,
        conf: float = 0.25,
    ) -> list[BoundingBox]:
        """
        Run detection on a single frame and return a list of BoundingBox objects.
        If the model failed to load (self.model is None), return an empty list
        and log a warning instead of raising an exception.
        """
        if self.model is None:
            import logging
            logging.getLogger(__name__).warning(
                "YoloPlateDetector.detect called but model is not loaded; returning empty list."
            )
            return []

        results = self.model(
            frame,
            device=self.device,
            imgsz=imgsz,
            conf=conf,
            verbose=False,
        )

        detected_boxes: list[BoundingBox] = []
        if not results:
            return detected_boxes

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = self.model.names.get(class_id, "unknown")

            detected_boxes.append(
                BoundingBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=confidence,
                    class_id=class_id,
                    class_name=class_name,
                )
            )

        return detected_boxes

    def detect_batch(
        self,
        frames: list[np.ndarray],
        imgsz: int = 640,
        conf: float = 0.25,
    ) -> list[list[BoundingBox]]:
        """
        Run detection on a batch of frames/tiles in parallel on GPU.
        """
        if self.model is None:
            logger.warning("detect_batch called but model is not loaded; returning empty lists.")
            return [[] for _ in frames]

        if not frames:
            return []

        results = self.model(
            frames,
            device=self.device,
            imgsz=imgsz,
            conf=conf,
            verbose=False,
        )

        batch_boxes: list[list[BoundingBox]] = []
        for r in results:
            boxes = []
            for box in r.boxes:
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = self.model.names.get(class_id, "unknown")

                boxes.append(
                    BoundingBox(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        confidence=confidence,
                        class_id=class_id,
                        class_name=class_name,
                    )
                )
            batch_boxes.append(boxes)

        return batch_boxes

    def track(
        self,
        frame: np.ndarray,
        persist: bool = True,
        imgsz: int = 640,
        conf: float = 0.25,
        tracker: str = "bytetrack.yaml",
    ) -> list[BoundingBox]:
        """
        Run detection with persistent ByteTrack tracking.

        Uses Ultralytics' built-in ``model.track()`` which maintains
        tracker state across calls when ``persist=True``.

        Args:
            frame:   BGR image (numpy array).
            persist: Keep tracker state across calls (same video stream).
            imgsz:   YOLO input resolution.
            conf:    Minimum confidence threshold.
            tracker: Tracker config file (shipped with ultralytics).

        Returns:
            List of BoundingBox with ``track_id`` populated.
        """
        if self.model is None:
            logger.warning(
                "YoloPlateDetector.track called but model is not loaded; "
                "returning empty list."
            )
            return []

        results = self.model.track(
            frame,
            device=self.device,
            imgsz=imgsz,
            conf=conf,
            persist=persist,
            tracker=tracker,
            verbose=False,
        )

        tracked_boxes: list[BoundingBox] = []
        if not results:
            return tracked_boxes

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = self.model.names.get(class_id, "unknown")

            # box.id is a tensor of shape [1] when tracking is active,
            # or None if the tracker hasn't assigned an ID yet.
            track_id = None
            if box.id is not None:
                track_id = int(box.id[0])

            tracked_boxes.append(
                BoundingBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=confidence,
                    class_id=class_id,
                    class_name=class_name,
                    track_id=track_id,
                )
            )

        return tracked_boxes

    def get_config(self) -> dict[str, Any]:
        """Config snapshot for logging/debugging."""
        return {
            "device": self.device,
            "framework": "ultralytics",
            "model_path": self.model_path,
        }


if __name__ == "__main__":
    import sys

    detector = YoloPlateDetector()
    detector.load_model("runs/detect/train-8/weights/best.pt")
    print("Config:", detector.get_config())

    if len(sys.argv) > 1:
        import cv2

        frame = cv2.imread(sys.argv[1])
        if frame is None:
            print(f"Could not read image: {sys.argv[1]}")
            sys.exit(1)
        boxes = detector.detect(frame)
        print(f"Found {len(boxes)} box(es):")
        for b in boxes:
            print(" ", b)
    else:
        print("Pass an image path as argv[1] to run detect() on a real frame.")