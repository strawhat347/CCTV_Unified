"""
Abstract interface for object/plate detectors.

Any concrete detector (YOLOv8/v11 plate localizer, or a future/alternate
model) must implement this contract so the detection pipeline can call
`detect()` without caring which underlying model is doing the work.
"""

from abc import ABC, abstractmethod
from typing import Any
import numpy as np


class BoundingBox:
    """
    Simple container for a single detection result.

    Attributes:
        x1, y1, x2, y2: Corner coordinates of the box (pixels).
        confidence:     Detection confidence score, 0.0-1.0.
        class_id:       Integer class label (e.g. 0 = license plate).
        class_name:     Human-readable label (e.g. "plate").
    """

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        confidence: float,
        class_id: int,
        class_name: str = "",
    ):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence
        self.class_id = class_id
        self.class_name = class_name

    def __repr__(self) -> str:
        return (
            f"BoundingBox(x1={self.x1}, y1={self.y1}, x2={self.x2}, "
            f"y2={self.y2}, confidence={self.confidence:.2f}, "
            f"class_id={self.class_id}, class_name='{self.class_name}')"
        )


class BaseDetector(ABC):
    """
    Contract for any object detector used in the pipeline.

    Usage:
        detector = SomeConcreteDetector(model_path=...)
        boxes = detector.detect(frame)
        for box in boxes:
            crop = frame[int(box.y1):int(box.y2), int(box.x1):int(box.x2)]
    """

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Run detection on a single frame.

        Args:
            frame: A numpy array representing the image (e.g. BGR from OpenCV).

        Returns:
            A list of BoundingBox objects, one per detected object.
            Returns an empty list if nothing is detected.
        """
        raise NotImplementedError

    @abstractmethod
    def load_model(self, model_path: str) -> None:
        """
        Load/initialize the underlying model weights.

        Kept separate from __init__ so implementations can control
        when the (potentially expensive) model load happens.
        """
        raise NotImplementedError

    def get_config(self) -> dict[str, Any]:
        """
        Optional: return detector configuration (thresholds, input size, etc.)
        for logging/debugging purposes. Default returns an empty dict.
        """
        return {}
