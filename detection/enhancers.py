import cv2
import numpy as np
import os
import logging

logger = logging.getLogger("enhancers")

class ImageEnhancer:
    def __init__(self, fsrcnn_model_path: str = "weights/FSRCNN_x2.pb"):
        self.fsrcnn_path = fsrcnn_model_path
        self.sr = None
        
        # Initialize FSRCNN if available
        if os.path.exists(self.fsrcnn_path):
            try:
                self.sr = cv2.dnn_superres.DnnSuperResImpl_create()
                self.sr.readModel(self.fsrcnn_path)
                self.sr.setModel("fsrcnn", 2)
                logger.info(f"Loaded FSRCNN super resolution model from {self.fsrcnn_path}")
            except Exception as e:
                logger.error(f"Failed to load FSRCNN model: {e}")
                self.sr = None
        else:
            logger.warning(f"FSRCNN model not found at {self.fsrcnn_path}. AI upscaling will fallback to Bicubic.")

    def enhance_traditional_cv(self, image: np.ndarray) -> np.ndarray:
        if image is None or image.size == 0:
            return image
            
        h, w = image.shape[:2]
        upscaled = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)
        
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        enhanced_gray = clahe.apply(gray)
        enhanced = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
        
        gaussian = cv2.GaussianBlur(enhanced, (5, 5), 1.0)
        sharpened = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)
        
        return sharpened

    def enhance_safe_ai(self, image: np.ndarray) -> np.ndarray:
        if image is None or image.size == 0:
            return image
            
        if self.sr is not None:
            try:
                return self.sr.upsample(image)
            except Exception as e:
                logger.error(f"FSRCNN upsample failed: {e}")
        
        h, w = image.shape[:2]
        return cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)
