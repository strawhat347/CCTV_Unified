"""
Abstract interface for OCR engines that read text from cropped plate images.

Any concrete engine (PaddleOCR, EasyOCR, Tesseract, etc.) must implement
this contract so the detection pipeline can call `read_text()` without
caring which OCR library is doing the recognition.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class OcrResult:
    """
    Container for a single OCR read.

    Attributes:
        text:       The recognized plate string (raw, before any
                    normalization/cleanup rules are applied downstream).
        confidence: Recognition confidence score, 0.0-1.0.
    """

    def __init__(self, text: str, confidence: float):
        self.text = text
        self.confidence = confidence

    def __repr__(self) -> str:
        return f"OcrResult(text='{self.text}', confidence={self.confidence:.2f})"


class BaseOcrEngine(ABC):
    """
    Contract for any OCR engine used to read plate text from a cropped
    image region produced by a BaseDetector implementation.

    Usage:
        ocr = SomeConcreteOcrEngine()
        result = ocr.read_text(cropped_plate_img)
        if result is not None:
            print(result.text, result.confidence)
    """

    @abstractmethod
    def read_text(self, cropped_img: np.ndarray) -> Optional[OcrResult]:
        """
        Run OCR on a cropped image (expected to contain a single plate).

        Args:
            cropped_img: A numpy array representing the cropped plate
                         region (e.g. BGR from OpenCV).

        Returns:
            An OcrResult with the recognized text and confidence,
            or None if no text could be confidently read.
        """
        raise NotImplementedError

    @abstractmethod
    def load_model(self) -> None:
        """
        Load/initialize the underlying OCR model/engine.

        Kept separate from __init__ so implementations can control
        when the (potentially expensive) model load happens.
        """
        raise NotImplementedError
