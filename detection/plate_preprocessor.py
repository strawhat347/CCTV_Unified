"""
detection/plate_preprocessor.py — Lightweight OpenCV preprocessing for
cropped plate images before OCR.

Five stages, all pure OpenCV (CPU), combined ~3ms per crop:

1. **Smart upscaling** — If the crop is too small for OCR (< 64px tall or
   < 180px wide), upscale by 2×–3× using bicubic interpolation so text
   characters meet PaddleOCR's minimum feature-extraction threshold.

2. **Gamma correction for dark plates** — Detects pitch-dark crops by mean
   brightness and applies adaptive gamma lifting to recover characters
   hidden in shadow / nighttime / under-canopy lighting.

3. **CLAHE contrast enhancement** — Adaptive histogram equalisation on the
   L channel (LAB space) to bring out text edges while preserving overall
   tone balance.  Uses a gentle clip limit (1.5) to avoid washing out thin
   character strokes on curved or sticker-style plates.

4. **Unsharp mask sharpening** — Reconstructs crisp edges on slightly
   blurry or distant plate characters via Gaussian-blur + weighted subtract.

5. **Deskew / rotation correction** — Detects the dominant text angle with
   cv2.minAreaRect on contours and applies an affine rotation so tilted
   plates are straightened before OCR reads them.
"""

from __future__ import annotations

import cv2
import numpy as np


class PlatePreprocessor:
    """
    Enhance a cropped plate image for better OCR accuracy.

    Usage::

        pp = PlatePreprocessor()
        enhanced = pp.preprocess(cropped_plate_bgr)
        ocr_result = ocr_engine.read_text(enhanced)
    """

    def __init__(
        self,
        # Upscaling
        min_height: int = 64,
        min_width: int = 180,
        max_scale: float = 4.0,
        # Gamma / dark-plate recovery
        dark_threshold: float = 80.0,
        gamma_boost: float = 2.5,
        # CLAHE
        clahe_clip: float = 1.5,
        clahe_grid: int = 8,
        # Sharpening
        sharpen_sigma: float = 1.0,
        sharpen_strength: float = 1.5,
        # Deskew
        deskew: bool = True,
        max_deskew_angle: float = 15.0,
        # New edge & stroke enhancements
        apply_bilateral: bool = True,
        bilateral_d: int = 9,
        bilateral_sigma: float = 75.0,
        apply_morphology: bool = False,
        morph_kernel_size: int = 2,
    ):
        """
        Args:
            min_height:       Minimum crop height (px) before OCR; smaller
                              crops get upscaled.
            min_width:        Minimum crop width (px) before OCR.
            max_scale:        Maximum upscale factor (caps at 4×).
            dark_threshold:   Mean brightness (0–255) below which the crop
                              is considered "dark" and gamma correction is
                              applied.
            gamma_boost:      Gamma exponent for dark-plate recovery.
                              Higher = brighter shadow recovery.
                              2.0–3.0 works well for night / pitch-dark plates.
            clahe_clip:       CLAHE clip limit (1.5 = gentle, avoids
                              washing out thin strokes on sticker plates).
            clahe_grid:       CLAHE tile grid size.
            sharpen_sigma:    Gaussian sigma for unsharp masking.
            sharpen_strength: Blend weight for sharpened image.
            deskew:           Whether to apply rotation correction.
            max_deskew_angle: Ignore angles larger than this (degrees).
            apply_bilateral:  Use bilateral filter to preserve edges while smoothing noise.
            bilateral_d:      Diameter of pixel neighborhood for bilateral filter.
            bilateral_sigma:  Filter sigma in color and coordinate space.
            apply_morphology: Apply morphological erosion to thicken text strokes.
            morph_kernel_size:Size of the erosion kernel (e.g. 2 means 2x2).
        """
        self.min_height = min_height
        self.min_width = min_width
        self.max_scale = max_scale
        self.dark_threshold = dark_threshold
        self.gamma_boost = gamma_boost
        self.clahe_clip = clahe_clip
        self.clahe_grid = clahe_grid
        self.sharpen_sigma = sharpen_sigma
        self.sharpen_strength = sharpen_strength
        self.deskew = deskew
        self.max_deskew_angle = max_deskew_angle
        self.apply_bilateral = apply_bilateral
        self.bilateral_d = bilateral_d
        self.bilateral_sigma = bilateral_sigma
        self.apply_morphology = apply_morphology
        self.morph_kernel_size = morph_kernel_size

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """
        Run the full preprocessing pipeline on a BGR plate crop.

        Returns the enhanced BGR image (same dtype as input).
        """
        if img is None or img.size == 0:
            return img

        out = self._apply_upscale(img)
        out = self._apply_gamma_correction(out)
        out = self._apply_clahe(out)
        
        if self.apply_bilateral:
            out = self._apply_bilateral_filter(out)
            
        if self.apply_morphology:
            out = self._apply_morphology(out)
            
        out = self._apply_sharpen(out)

        if self.deskew:
            out = self._apply_deskew(out)

        return out

    # ------------------------------------------------------------------
    # Stage 1: Smart upscaling for tiny crops
    # ------------------------------------------------------------------
    def _apply_upscale(self, img: np.ndarray) -> np.ndarray:
        """
        Upscale crops that are too small for PaddleOCR's text detector.

        PaddleOCR's DBNet needs text lines to be at least ~30–40px tall.
        Motorcycle plates cropped from low-res frames can be 15–25px tall,
        causing OCR to return None.  A 2×–3× bicubic upscale fixes this
        with negligible latency (~0.5ms).
        """
        h, w = img.shape[:2]

        # Calculate the scale needed to meet minimum dimensions
        scale_h = self.min_height / h if h < self.min_height else 1.0
        scale_w = self.min_width / w if w < self.min_width else 1.0
        scale = max(scale_h, scale_w)

        if scale <= 1.0:
            return img  # Already large enough

        # Cap the scale to avoid creating absurdly large images
        scale = min(scale, self.max_scale)

        new_w = int(w * scale)
        new_h = int(h * scale)

        upscaled = cv2.resize(
            img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4,
        )
        return upscaled

    # ------------------------------------------------------------------
    # Stage 2: Gamma correction for pitch-dark plates
    # ------------------------------------------------------------------
    def _apply_gamma_correction(self, img: np.ndarray) -> np.ndarray:
        """
        Detect and recover plates in pitch-dark / deep-shadow areas.

        If the mean brightness of the crop falls below ``dark_threshold``,
        apply a gamma-lift transform to pull character edges out of the
        darkness.  This handles:
        - Plates under building canopies / parking pillars
        - Nighttime / no-streetlight conditions
        - IR camera footage with low contrast

        The gamma transform is: output = 255 × (input / 255) ^ (1/gamma)
        where gamma > 1 brightens the image non-linearly (shadows get
        lifted more than highlights).
        """
        # Check mean brightness on grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))

        if mean_brightness >= self.dark_threshold:
            return img  # Not dark — skip

        # Build a lookup table for the gamma transform (fast, vectorised)
        inv_gamma = 1.0 / self.gamma_boost
        table = np.array(
            [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
            dtype=np.uint8,
        )

        corrected = cv2.LUT(img, table)
        return corrected

    # ------------------------------------------------------------------
    # Stage 3: CLAHE on L-channel (LAB space) — adaptive
    # ------------------------------------------------------------------
    def _apply_clahe(self, img: np.ndarray) -> np.ndarray:
        """
        Adaptive histogram equalisation on the lightness channel.

        Skips CLAHE if the image already has good contrast (L-channel std
        deviation > 50), because over-processing high-contrast plates
        (e.g. white text on black background) washes out thin character
        strokes.
        """
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)

        # Check if contrast is already sufficient
        l_std = float(np.std(l_ch))
        if l_std > 50.0:
            # Already high contrast — CLAHE would over-process
            return img

        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip,
            tileGridSize=(self.clahe_grid, self.clahe_grid),
        )
        l_ch = clahe.apply(l_ch)

        lab = cv2.merge([l_ch, a_ch, b_ch])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # ------------------------------------------------------------------
    # New Stage: Bilateral Filter (Edge-Preserving Blur)
    # ------------------------------------------------------------------
    def _apply_bilateral_filter(self, img: np.ndarray) -> np.ndarray:
        """
        Removes noise while keeping edges (like the straight back of a 'D') sharp.
        """
        return cv2.bilateralFilter(
            img, 
            d=self.bilateral_d, 
            sigmaColor=self.bilateral_sigma, 
            sigmaSpace=self.bilateral_sigma
        )

    # ------------------------------------------------------------------
    # New Stage: Morphological Erosion
    # ------------------------------------------------------------------
    def _apply_morphology(self, img: np.ndarray) -> np.ndarray:
        """
        Thickens dark text on a bright background (closes gaps in 'D').
        """
        kernel = np.ones((self.morph_kernel_size, self.morph_kernel_size), np.uint8)
        # Using erosion because text is dark (black) and background is bright (white/yellow)
        return cv2.erode(img, kernel, iterations=1)

    # ------------------------------------------------------------------
    # Stage 4: Unsharp mask
    # ------------------------------------------------------------------
    def _apply_sharpen(self, img: np.ndarray) -> np.ndarray:
        """Sharpen edges via Gaussian-blur subtraction."""
        blurred = cv2.GaussianBlur(
            img,
            ksize=(0, 0),
            sigmaX=self.sharpen_sigma,
        )
        sharpened = cv2.addWeighted(
            img, self.sharpen_strength,
            blurred, 1.0 - self.sharpen_strength,
            gamma=0,
        )
        return sharpened

    # ------------------------------------------------------------------
    # Stage 5: Deskew via minAreaRect
    # ------------------------------------------------------------------
    def _apply_deskew(self, img: np.ndarray) -> np.ndarray:
        """
        Detect the dominant skew angle from text contours and apply
        an affine rotation to straighten the plate.
        """
        h, w = img.shape[:2]
        if h < 10 or w < 10:
            return img

        # Convert to grayscale and binarise with Otsu threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )

        # Find all contours (character blobs)
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return img

        # Merge all contour points and compute a single minimum-area
        # bounding rectangle — its angle gives us the text line skew.
        all_points = np.concatenate(contours)
        rect = cv2.minAreaRect(all_points)
        (rect_center, (rect_w, rect_h), angle) = rect

        # Normalise angle for all OpenCV versions.
        # Ensure the angle is for the longer edge of the rectangle.
        if rect_w < rect_h:
            angle += 90

        # Bound to [-45, 45]
        while angle > 45:
            angle -= 90
        while angle < -45:
            angle += 90

        # Skip if angle is too large (likely noise, not real skew)
        if abs(angle) > self.max_deskew_angle or abs(angle) < 0.5:
            return img

        # Rotate around the image centre
        centre = (w / 2.0, h / 2.0)
        rotation_matrix = cv2.getRotationMatrix2D(centre, angle, scale=1.0)
        
        # Calculate new bounding dimensions to prevent corners from being chopped off
        abs_cos = abs(rotation_matrix[0, 0])
        abs_sin = abs(rotation_matrix[0, 1])
        new_w = int(h * abs_sin + w * abs_cos)
        new_h = int(h * abs_cos + w * abs_sin)
        
        # Adjust matrix to take into account translation
        rotation_matrix[0, 2] += new_w / 2.0 - centre[0]
        rotation_matrix[1, 2] += new_h / 2.0 - centre[1]

        rotated = cv2.warpAffine(
            img, rotation_matrix, (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return rotated
