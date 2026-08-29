"""
main.py - Entry point: wires sources -> detection -> alerting.

Starts the FastAPI server and the background pipeline worker.
"""

import logging
import multiprocessing  # noqa: F401
from pathlib import Path

import uvicorn

import sys

import config
from pipeline.multiprocessing_workers import PipelineWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

def run_pipeline_for_camera(camera_id: int, stream_url: str, name: str, source_type: str):
    """Runs the pipeline for a single camera in a separate process."""
    # Imports inside the function to avoid CUDA context sharing issues across processes
    from alerting.rule_engine import RuleEngine
    from db.connection_pool import get_pool
    from detection.paddle_ocr_engine import PaddleOcrEngine
    
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
        source = MockVideoSource(camera_id=camera_id, video_path=Path(stream_url), loop=True)
    else:
        source = RTSPCameraSource(camera_id=camera_id, rtsp_url=stream_url)

    # 3. Detectors
    detector = YoloPlateDetector()
    detector.load_model(config.YOLO_MODEL_PATH)
    
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
        video_path = video_dir / "camera_3_test_2.mp4"
        if not video_path.exists():
            mp4s = list(video_dir.glob("*.mp4"))
            if mp4s:
                video_path = mp4s[0]
            else:
                raise FileNotFoundError(f"No mock videos found in {video_dir}. Add .mp4 files or check MOCK_VIDEO_DIR in .env.")
        
        worker = PipelineWorker(target=run_pipeline_for_camera, args=(camera_id, str(video_path), "Gate Camera (mock)", "mock"))
        workers.append(worker)
        # worker.start() # (DISABLED TO SAVE RESOURCES)
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
                        # insert_camera doesn't let us force the ID if it's auto-increment, 
                        # but we can try to just use insert_camera and let it assign an ID,
                        # or ideally we just insert it.
                        insert_camera(name=name, stream_url=stream_url, status="active", location=cam.get("location", ""), city=None, department_id=None)
                        logger.info(f"Synced Sentinel Camera to DB: {name}")
                    except Exception as e:
                        logger.error(f"Failed to sync camera to DB: {e}")

                # Prepare the worker (but leave disabled to save resources unless requested)
                worker = PipelineWorker(target=run_pipeline_for_camera, args=(cam_id, stream_url, name, "real"))
                workers.append(worker)
                # worker.start() # (DISABLED TO SAVE RESOURCES)

    # 2. Start FastAPI app in main process
    logger.info(f"Starting API server on port {config.API_PORT}...")
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
