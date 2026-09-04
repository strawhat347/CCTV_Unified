import time
import logging
from typing import Any, Optional, Dict
from multiprocessing import Queue

import config
from detection.track_manager import TrackManager, FinalizedTrack
from sources.base_camera_source import BaseCameraSource
from detection.base_detector import BaseDetector
from detection.base_ocr_engine import BaseOcrEngine, OcrResult
from db.dao_cameras import get_camera_by_id, insert_camera, update_camera
from db.dao_detections import insert_detection
from collections import Counter
import itertools

logger = logging.getLogger("pipeline")
_track_id_counter = itertools.count(start=1_000_000)

class CameraEdgeFeeder:
    def __init__(self, camera_id: int, source: BaseCameraSource, detector: BaseDetector, fast_queue: Queue, heavy_queue: Queue, sample_interval: int = 1):
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.fast_queue = fast_queue
        self.heavy_queue = heavy_queue
        self.sample_interval = sample_interval
        self.track_manager = TrackManager(stale_after_frames=15, max_crops=5, sharpness_threshold=60.0)
        self.camera_location = None
        self._running = False
        self.stats = {"frames_read": 0, "tracks_finalized": 0}

    def ensure_camera_row(self, name: str, stream_url: str) -> None:
        existing = get_camera_by_id(self.camera_id)
        if existing is None:
            new_id = insert_camera(name=name, stream_url=stream_url, status="active")
            self.camera_id = new_id
            self.source.camera_id = new_id
        else:
            self.camera_location = existing.get("location")
            if existing.get("stream_url") != stream_url:
                update_camera(self.camera_id, {"stream_url": stream_url})

    def run(self) -> None:
        logger.info(f"Edge Feeder for Camera {self.camera_id} started.")
        self._running = True
        self.source.connect()
        
        frame_idx = 0
        while self._running:
            frame = self.source.read_frame()
            if frame is None:
                logger.warning(f"Edge Feeder {self.camera_id} source ended.")
                break
                
            frame_idx += 1
            self.stats["frames_read"] += 1
            if frame_idx % self.sample_interval != 0:
                self._finalize_stale_tracks(frame_idx)
                continue
                
            active_tracks = self.detector.track(frame)
            
            for box in active_tracks:
                # If the detector doesn't support tracking (e.g. Hierarchical), assign a unique ID per detection
                t_id = box.track_id if box.track_id is not None else next(_track_id_counter)
                bbox = (int(box.x1), int(box.y1), int(box.x2), int(box.y2))
                conf = float(box.confidence)

                # Add 12% padding around plate bounding box to prevent clipping edge characters
                bw = max(1, bbox[2] - bbox[0])
                bh = max(1, bbox[3] - bbox[1])
                pad_x = int(bw * 0.12)
                pad_y = int(bh * 0.12)
                
                h, w = frame.shape[:2]
                y1, y2 = max(0, bbox[1] - pad_y), min(h, bbox[3] + pad_y)
                x1, x2 = max(0, bbox[0] - pad_x), min(w, bbox[2] + pad_x)
                
                if y2 <= y1 or x2 <= x1:
                    continue
                    
                # Drop detections that are physically too small to contain a readable plate
                # This prevents wasting OCR compute on tiny false positive crops
                if bw < 40 or bh < 15:
                    continue
                    
                crop = frame[y1:y2, x1:x2]
                
                is_sharp, sharpness = self.track_manager.is_sharp(crop)
                was_blurry = not is_sharp
                self.track_manager.update(t_id, crop, bbox, conf, frame_idx, sharpness, was_blurry)
                
            self._finalize_stale_tracks(frame_idx)

        logger.info(f"Edge Feeder {self.camera_id} stopping. Flushing tracks...")
        for ft in self.track_manager.flush_all():
            self._push_to_queue(ft)

    def _finalize_stale_tracks(self, frame_idx: int):
        for ft in self.track_manager.finalize_stale(frame_idx):
            self._push_to_queue(ft)
            
    def _push_to_queue(self, ft: FinalizedTrack):
        self.stats["tracks_finalized"] += 1
        
        import cv2
        blur_score = 0.0
        if ft.best_crop is not None:
            gray = cv2.cvtColor(ft.best_crop, cv2.COLOR_BGR2GRAY)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            
        logger.info(f"Edge Feeder {self.camera_id} pushing track {ft.track_id} to OCR queue with {len(ft.sharp_crops)} sharp crops (Blur Score: {blur_score:.1f})")
        # Push payload to central AI with backpressure
        try:
            payload = {
                "camera_id": self.camera_id,
                "camera_location": self.camera_location,
                "ft": ft
            }
            if blur_score > 60.0:
                self.fast_queue.put(payload, timeout=5.0)
            else:
                self.heavy_queue.put(payload, timeout=5.0)
        except Exception:
            logger.warning(f"OCR queue full — dropping track {ft.track_id} from camera {self.camera_id}")

    def stop(self) -> None:
        self._running = False
        self.source.release()


class CentralOcrWorker:
    def __init__(self, ocr_engine: BaseOcrEngine, rule_engine: Any, ocr_queue: Queue, cooldown_cache: dict, worker_type: str = "both"):
        from detection.enhancers import ImageEnhancer
        self.ocr_engine = ocr_engine
        self.rule_engine = rule_engine
        self.ocr_queue = ocr_queue
        self.enhancer = ImageEnhancer()
        self._running = False
        self.cooldown_cache = cooldown_cache
        self.cooldown_seconds = 30
        self.worker_type = worker_type
        
    def run(self):
        logger.info("Central AI Worker started and listening to OCR queue.")
        self._running = True
        while self._running:
            try:
                # Block for up to 1 second to allow clean shutdown checks
                payload = self.ocr_queue.get(timeout=1.0)
                if payload is None:
                    continue
                    
                self._process_payload(payload)
            except Exception as e:
                # queue.Empty is expected on timeout, otherwise log error
                if type(e).__name__ != 'Empty':
                    logger.error(f"Central OCR error: {e}")
                    
    def stop(self):
        self._running = False
        
    def _process_payload(self, payload: dict):
        camera_id = payload["camera_id"]
        camera_location = payload["camera_location"]
        ft: FinalizedTrack = payload["ft"]
        
        reads = []
        for crop in ft.sharp_crops:
            if crop is None:
                continue
            
            try:
                if self.worker_type in ("fast", "both"):
                    cv_crop = self.enhancer.enhance_traditional_cv(crop)
                    res_cv = self.ocr_engine.read_text(cv_crop)
                    if res_cv and res_cv.text:
                        reads.append((res_cv.text, res_cv.confidence))
                        
                if self.worker_type in ("heavy", "both"):
                    ai_crop = self.enhancer.enhance_safe_ai(crop)
                    res_ai = self.ocr_engine.read_text(ai_crop)
                    if res_ai and res_ai.text:
                        reads.append((res_ai.text, res_ai.confidence))
            except Exception as e:
                logger.warning(f"Failed to process crop for track {ft.track_id}: {e}")
                continue
                
        plate_text, ocr_conf = None, 0.0
        if reads:
            voted = self._vote_consensus(reads)
            if voted:
                raw_text, ocr_conf = voted
                from pipeline.plate_corrector import PlateCorrector
                corrector = PlateCorrector()
                plate_text = corrector.correct(raw_text)
                
        img_path = None
        if ft.best_crop is not None:
            safe_text = plate_text if plate_text else "unknown"
            # Enhance the best crop before saving so we can visually inspect the quality
            display_crop = self.enhancer.enhance_safe_ai(ft.best_crop)
            img_path = self._save_crop(display_crop, camera_id, safe_text)
            
        if plate_text:
            import time
            import re
            
            # Supports 2-letter state, 1-2 digit district, 0-3 series letters, and 1-4 registration digits
            _STANDARD_PLATE_REGEX = re.compile(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$')
            _BH_PLATE_REGEX = re.compile(r'^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$')
            
            is_valid_rto = bool(_STANDARD_PLATE_REGEX.match(plate_text)) or bool(_BH_PLATE_REGEX.match(plate_text))
            
            if not is_valid_rto:
                logger.debug(f"[Central AI] Plate {plate_text} is invalid. Dropping to prevent flood.")
                return

            now = time.time()
            cache_key = f"{camera_id}_{plate_text}"
            
            if cache_key in self.cooldown_cache:
                if now - self.cooldown_cache[cache_key] < 30:
                    logger.debug(f"[Central AI] Camera {camera_id} Plate {plate_text} in cooldown. Skipping duplicate alert.")
                    return
            
            self.cooldown_cache[cache_key] = now
            
            # Clean up old cache entries
            for k, v in list(self.cooldown_cache.items()):
                if now - v > 30:
                    del self.cooldown_cache[k]
                    
            logger.info(f"[Central AI] Camera {camera_id} Finalized Track {ft.track_id}: {plate_text} (conf={ocr_conf:.2f}) saved to {img_path}")
            
            bbox_x, bbox_y, bbox_w, bbox_h = ft.bbox if ft.bbox else (0, 0, 0, 0)
            
            det_id = insert_detection(
                camera_id=camera_id,
                object_type="vehicle",
                confidence=ocr_conf,
                bbox_x=int(bbox_x),
                bbox_y=int(bbox_y),
                bbox_w=int(bbox_w),
                bbox_h=int(bbox_h),
                image_path=img_path,
                plate_text=plate_text,
                location=camera_location
            )
            
            if self.rule_engine:
                self.rule_engine.process_detection(
                    detection_id=det_id,
                    plate_text=plate_text,
                    camera_id=camera_id
                )
                
            # Broadcast the detection to the GUI instantly
            import httpx
            import config
            from datetime import datetime, timezone
            try:
                det_data = {
                    "detection_id": det_id,
                    "camera_id": camera_id,
                    "object_type": "vehicle",
                    "confidence": ocr_conf,
                    "bbox": f"{int(bbox_x)},{int(bbox_y)},{int(bbox_w)},{int(bbox_h)}",
                    "plate_text": plate_text,
                    "image_path": img_path,
                    "detected_at": datetime.now(timezone.utc).isoformat()
                }
                import os, ssl
                use_tls = os.path.exists("cert.pem")
                protocol = "https" if use_tls else "http"
                verify_cert = ssl.create_default_context(cafile="cert.pem") if use_tls else True
                api_host = getattr(config, "API_HOST", "127.0.0.1")
                if api_host in ("0.0.0.0", ""):
                    api_host = "127.0.0.1"
                httpx.post(
                    f"{protocol}://{api_host}:{config.API_PORT}/detections/internal/push",
                    json=det_data,
                    headers={"X-API-Key": config.API_KEY},
                    timeout=3.0,
                    verify=verify_cert
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast raw detection: {e}")
        else:
            logger.info(f"[Central AI] Camera {camera_id} Track {ft.track_id} yielded no OCR text. (Attempted {len(ft.sharp_crops)} sharp crops, {ft.blurry_skips} blurry skips)")
            
    def _vote_consensus(self, reads: list[tuple[str, float]]) -> Optional[tuple[str, float]]:
        if not reads:
            return None
        length_counter = Counter(len(r[0]) for r in reads)
        dominant_length = length_counter.most_common(1)[0][0]
        filtered = [(text, conf) for text, conf in reads if len(text) == dominant_length]
        if not filtered:
            return None

        voted_chars = []
        for pos in range(dominant_length):
            char_weights = {}
            for text, conf in filtered:
                ch = text[pos]
                char_weights[ch] = char_weights.get(ch, 0.0) + conf
            best_char = max(char_weights, key=char_weights.get)
            voted_chars.append(best_char)

        voted_text = "".join(voted_chars)
        avg_conf = sum(conf for _, conf in filtered) / len(filtered)
        return voted_text, avg_conf

    def _save_crop(self, crop, camera_id, text) -> str:
        import os, cv2, re
        from datetime import datetime
        os.makedirs("data/crops", exist_ok=True)
        # Create a more professional name: camX_plate_YYYYMMDD_HHMMSS.jpg
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_text = text if text and text != "unknown" else "unreadable"
        # Security: strip any path separators or special chars from plate text
        # to prevent path traversal via adversarial OCR output
        safe_text = re.sub(r'[^A-Za-z0-9_\-]', '', safe_text)
        if not safe_text:
            safe_text = "unreadable"
        fname = f"cam{camera_id}_{safe_text}_{timestamp}.jpg"
        path = os.path.join("data", "crops", fname)
        cv2.imwrite(path, crop)
        # Return filename only — the static mount serves data/crops/ at /crops/
        return fname
