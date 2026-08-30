"""
main.py - Entry point: wires sources -> detection -> alerting.

Starts the FastAPI server and the background pipeline worker.
"""

import logging
import multiprocessing as mp
import time
import os

# Disable PaddleX's slow internet connectivity check for OCR models
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import config
from pathlib import Path

import uvicorn

import sys

from pipeline.multiprocessing_workers import PipelineWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

def run_pipeline_for_camera(camera_id: int, stream_url: str, name: str, source_type: str):
    """Runs the pipeline for a single camera in a separate process."""
    # Imports inside the function to avoid CUDA context sharing issues across processes
    from alerting.rule_engine import RuleEngine
    from db.connection_pool import get_pool
    # IMPORT ORDER MATTERS ON WINDOWS: yolo (torch) must be imported before paddleocr 
    # to avoid a WinError 127 DLL conflict with shm.dll.
    from detection.yolo_plate_detector import YoloPlateDetector
    from metrics.metrics_logger import MetricsLogger
    from metrics.perf_counters import PerfCounter
    from pipeline.detection_pipeline import DetectionPipeline
    from registry.mock_registry import MockRegistry
    from sources.mock_video_source import MockVideoSource
    from sources.rtsp_camera_source import RTSPCameraSource

    logger.info(f"[{camera_id}] Initializing pipeline components...")
    get_pool() # init db connection pool in this process

    # 1. Registry & Rule Engine
    registry = MockRegistry(config.SEED_REGISTRY_CSV)
    registry.connect()
    rule_engine = RuleEngine(registry)

    # 2. Source
    if source_type == "mock":
        source = MockVideoSource(camera_id=camera_id, video_path=Path(stream_url), loop=False)
    else:
        source = RTSPCameraSource(camera_id=camera_id, rtsp_url=stream_url)

    # 3. Detectors
    if config.USE_HIERARCHICAL:
        from detection.hierarchical_detector import HierarchicalDetector
        detector = HierarchicalDetector(
            vehicle_model_path=config.VEHICLE_MODEL_PATH,
            vehicle_classes=config.VEHICLE_CLASSES,
            vehicle_padding=config.VEHICLE_PADDING
        )
        detector.load_model(config.YOLO_MODEL_PATH)
    else:
        from detection.yolo_plate_detector import YoloPlateDetector
        detector = YoloPlateDetector()
        detector.load_model(config.YOLO_MODEL_PATH)
    
    from detection.paddle_ocr_engine import PaddleOcrEngine
    ocr = PaddleOcrEngine()
    ocr.load_model()

    # 4. Metrics
    perf_counter = PerfCounter()
    metrics_logger = MetricsLogger(perf_counter, interval=10)

    # 5. Pipeline
    pipeline = DetectionPipeline(
        camera_id=camera_id,
        source=source,
        detector=detector,
        ocr_engine=ocr,
        rule_engine=rule_engine,
        perf_counter=perf_counter,
        sample_interval=10,
        max_frames=None,  # run forever
        save_crops=True,
    )
    pipeline.ensure_camera_row(
        name=name,
        stream_url=stream_url,
    )
    
    logger.info(f"[{camera_id}] Starting pipeline execution...")
    metrics_logger.start()
    try:
        pipeline.run()
    finally:
        metrics_logger.stop()


def main():
    logger.info(f"CCTV Unified Surveillance MVP starting in '{config.MODE}' mode...")
    
    # 1. Create pipeline workers based on mode
    workers = []
    
    if config.is_mock_mode():
        camera_id = 1
        video_dir = Path(config.MOCK_VIDEO_DIR)
        videos = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.webm"))
        if videos:
            video_path = videos[0]
            logger.info(f"Using mock video: {video_path.name}")
        else:
            raise FileNotFoundError(f"No mock videos found in {video_dir}. Add .mp4 or .webm files.")
        
        worker = PipelineWorker(run_pipeline_for_camera, camera_id, str(video_path), "Gate Camera (mock)", "mock")
        workers.append(worker)
        worker.start()
    else:
        # Real Mode: Fetch camera catalogue from Sentinel Grid
        logger.info("Fetching live camera catalogue from Sentinel API...")
        from clients.sentinel_client import SentinelClient
        from db.dao_cameras import get_camera_by_id, insert_camera
        
        client = SentinelClient(config.SENTINEL_API_HOST)
        cameras = client.get_cameras()
        
        if not cameras:
            logger.warning("No cameras found or failed to fetch catalogue.")
            
        for idx, cam in enumerate(cameras):
            cam_id = int(cam.get("id", idx + 1))
            stream_url = cam.get("rtsp_url") or cam.get("url")
            name = cam.get("location") or f"Sentinel Camera {cam_id}"
            
            if stream_url:
                # Sync to database so it appears in the frontend immediately
                existing = get_camera_by_id(cam_id)
                if not existing:
                    try:
                        cam_id = insert_camera(name=name, stream_url=stream_url, status="active", location=cam.get("location", ""), city=None, department_id=None)
                        logger.info(f"Synced Sentinel Camera to DB: {name} as ID {cam_id}")
                    except Exception as e:
                        logger.error(f"Failed to sync camera to DB: {e}")
                        continue  # skip if DB insert fails

                # Prepare the worker
                worker = PipelineWorker(run_pipeline_for_camera, cam_id, stream_url, name, "real")
                workers.append(worker)
                
                # Start only the first 5 active workers to save resources
                if len(workers) <= 5:
                    worker.start()

    # 2. Start FastAPI app in main process
    logger.info(f"Starting API server on port {config.API_PORT}...")
    
    # Inject workers into the app state so the API can check if they are running
    from api.main import app
    app.state.workers = workers
    
    try:
        import os
        if os.path.exists("key.pem") and os.path.exists("cert.pem"):
            logger.info("🔐 TLS Certificate found! Starting in HTTPS mode.")
            uvicorn.run("api.main:app", host="127.0.0.1", port=config.API_PORT, reload=False, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
        else:
            uvicorn.run("api.main:app", host="127.0.0.1", port=config.API_PORT, reload=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        pass
        # for w in workers:
        #     w.stop()

if __name__ == "__main__":
    main()
