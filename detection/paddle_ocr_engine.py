"""
detection/paddle_ocr_engine.py — Real implementation of BaseOcrEngine,
backed by PaddleOCR.

Handles both single-line and multi-line/stacked license plates (e.g. Indian
two-wheeler or commercial vehicle plates where the state code like 'GJ07F' is on top
and the registration number 'H9779' is on the bottom).

Filters out HSRP artifacts (e.g. 'IND' watermark) and stitches lines in
spatial reading order (top-to-bottom, left-to-right).

Optionally applies PlatePreprocessor (CLAHE + sharpen + deskew) to every
crop before recognition for improved accuracy on blurry/angled/dark plates.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
from paddleocr import PaddleOCR

from detection.base_ocr_engine import BaseOcrEngine, OcrResult
from detection.indian_plate_formatter import extract_indian_plate, normalize_plate_chars
from detection.plate_preprocessor import PlatePreprocessor

import logging
_logger = logging.getLogger("paddle_ocr_engine")


class PaddleOcrEngine(BaseOcrEngine):
    """
    Concrete BaseOcrEngine backed by PaddleOCR.

    Usage:
        ocr = PaddleOcrEngine()
        ocr.load_model()
        result = ocr.read_text(cropped_plate_img)
    """

    def __init__(self, preprocess: bool = True):
        """
        Args:
            preprocess: If True (default), apply CLAHE + sharpen + deskew
                        to every crop before running OCR.
        """
        self.ocr: PaddleOCR | None = None
        self._preprocessor: PlatePreprocessor | None = (
            PlatePreprocessor() if preprocess else None
        )

    def load_model(self) -> None:
        import os
        from pathlib import Path
        import config

        # Restore PATH hacks for paddlepaddle-gpu to find its pip-installed DLLs
        # Dynamically discover the venv path for CUDA/cuDNN DLLs
        import sys
        venv_site = Path(sys.prefix) / "Lib" / "site-packages"
        _cudnn_bin = venv_site / "nvidia" / "cudnn" / "bin"
        _cublas_bin = venv_site / "nvidia" / "cublas" / "bin"
        if _cudnn_bin.exists():
            os.environ["PATH"] = f"{_cudnn_bin};{os.environ.get('PATH', '')}"
        if _cublas_bin.exists():
            os.environ["PATH"] = f"{_cublas_bin};{os.environ.get('PATH', '')}"

        # Bypass PaddleX startup network hang
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

        use_gpu = config.should_use_gpu()
        
        from pathlib import Path
        custom_rec_dir = Path("models/en_PP-OCRv4_rec_infer").resolve()
        
        import paddleocr
        is_v3 = getattr(paddleocr, '__version__', '2.0').startswith('3.')
        
        kwargs = {
            "use_angle_cls": True,
            "lang": "en",
            "use_gpu": use_gpu,
        }
        
        if not is_v3 and custom_rec_dir.exists():
            kwargs["rec_model_dir"] = str(custom_rec_dir)
            kwargs["show_log"] = False
        
        # Strip Nones
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        
        while True:
            try:
                self.ocr = PaddleOCR(**kwargs)
                break
            except ValueError as e:
                error_str = str(e)
                if "Unknown argument:" in error_str:
                    bad_arg = error_str.split("Unknown argument:")[-1].strip().strip("'\"")
                    if bad_arg in kwargs:
                        _logger.warning(f"API changed in this PaddleOCR version. Removing unsupported argument: '{bad_arg}'")
                        del kwargs[bad_arg]
                        continue
                # If it's a different ValueError, re-raise it
                raise
            except Exception as e:
                if use_gpu and kwargs.get("use_gpu"):
                    _logger.warning(f"GPU init failed ({e}), falling back to CPU.")
                    kwargs["use_gpu"] = False
                    continue
                raise

    def read_text(self, cropped_img: np.ndarray) -> Optional[OcrResult]:
        """
        Run OCR on a cropped plate region.

        Handles single-line and multi-line/stacked plates.
        Filters out 'IND' country stickers and sorts lines top-to-bottom.

        When preprocessing is enabled, tries both the preprocessed image
        and a simple 2× upscaled raw image, keeping whichever produces
        the better OCR result.  This handles both dark/faded plates
        (where preprocessing helps) and high-contrast plates (where
        CLAHE can wash out characters).
        """
        if self.ocr is None:
            raise RuntimeError("OCR model not loaded. Call load_model() first.")

        # Guard against zero-pixel crops crashing the engine.
        if cropped_img.size == 0:
            return None

        # Build candidate images to try OCR on
        candidates: list[np.ndarray] = []

        if self._preprocessor is not None:
            candidates.append(self._preprocessor.preprocess(cropped_img))

            # Also try a simple 2× bicubic upscale as a fallback
            import cv2
            h, w = cropped_img.shape[:2]
            if h < 64 or w < 180:
                upscaled = cv2.resize(
                    cropped_img, (0, 0), fx=2, fy=2,
                    interpolation=cv2.INTER_CUBIC,
                )
                candidates.append(upscaled)
        else:
            candidates.append(cropped_img)

        # Run OCR on each candidate in order. 
        # Prioritize the properly preprocessed candidate if it yields a valid plate
        # with reasonable confidence, to prevent overconfident hallucinations from the raw fallback.
        best_result: OcrResult | None = None

        for img in candidates:
            parsed = self._parse_ocr_result(img)
            if parsed is None:
                continue

            extracted = extract_indian_plate(parsed.text)
            if extracted is None:
                continue

            normalised = normalize_plate_chars(extracted)
            valid_parsed = OcrResult(text=normalised, confidence=parsed.confidence)

            # If the preprocessed image gave a decent valid read, take it immediately!
            if valid_parsed.confidence > 0.65:
                return valid_parsed

            if best_result is None or valid_parsed.confidence > best_result.confidence:
                best_result = valid_parsed

        return best_result

    def _parse_ocr_result(self, img: np.ndarray) -> Optional[OcrResult]:
        """
        Run PaddleOCR on a single image and parse the result into an
        OcrResult, handling multi-line plates and HSRP filtering.
        """
        import paddleocr
        is_v3 = getattr(paddleocr, '__version__', '2.0').startswith('3.')
        
        if is_v3:
            result = self.ocr.ocr(img)
        else:
            result = self.ocr.ocr(img, cls=True)

        if not result or not result[0]:
            return None

        valid_lines = []
        for item in result[0]:
            box_pts, (text, conf) = item
            # Clean text: keep only alphanumeric uppercase characters
            cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()

            # Ignore empty strings or standalone HSRP country stamps ('IND')
            if not cleaned or cleaned in ("IND", "INDIA", "IN"):
                continue

            # Calculate center Y and center X for spatial sorting
            cy = sum(pt[1] for pt in box_pts) / 4.0
            cx = sum(pt[0] for pt in box_pts) / 4.0
            valid_lines.append((cy, cx, cleaned, float(conf)))

        if not valid_lines:
            return None

        # Sort top-to-bottom primarily (using bucketed Y coordinate to group lines),
        # then left-to-right on the same line
        valid_lines.sort(key=lambda line: (round(line[0] / 15.0), line[1]))

        combined_text = "".join(line[2] for line in valid_lines)
        avg_confidence = sum(line[3] for line in valid_lines) / len(valid_lines)

        return OcrResult(text=combined_text, confidence=float(avg_confidence))


if __name__ == "__main__":
    # Quick smoke test: python detection/paddle_ocr_engine.py <path_to_cropped_plate_image>
    import sys

    if len(sys.argv) < 2:
        print("Usage: python paddle_ocr_engine.py <cropped_plate_image_path>")
        sys.exit(1)

    import cv2

    crop = cv2.imread(sys.argv[1])
    if crop is None:
        print(f"Could not read image: {sys.argv[1]}")
        sys.exit(1)

    engine = PaddleOcrEngine()
    engine.load_model()
    result = engine.read_text(crop)
    print("Result:", result)