import logging
import sys
from pathlib import Path
import uvicorn
import multiprocessing

import config
from pipeline.multiprocessing_workers import MasterOcrProcess, CameraFeederProcess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

def run_master_ocr(queue: multiprocessing.Queue, stop_event: multiprocessing.synchronize.Event):
    from pipeline.detection_pipeline import CentralOcrWorker
    from detection.paddle_ocr_engine import PaddleOcrEngine
    from alerting.rule_engine import RuleEngine
    from registry.mock_registry import MockRegistry

    logger.info("Initializing PaddleOCR (GPU/CPU) in Master process...")
    ocr = PaddleOcrEngine()
    ocr.load_model()
    
    # Fix PaddleOCR hijacking the root logger and silencing INFO logs
    logging.getLogger().setLevel(logging.INFO)
    
    registry = MockRegistry(config.SEED_REGISTRY_CSV)
    registry.connect()
    rule_engine = RuleEngine(registry)
    
    worker = CentralOcrWorker(ocr, rule_engine, queue)
    
    # We use stop_event in a non-blocking loop via queue timeout
    while not stop_event.is_set():
        try:
            payload = queue.get(timeout=1.0)
            if payload is None:
                break
            worker._process_payload(payload)
        except Exception as e:
            if type(e).__name__ != 'Empty':
                logger.error(f"Central OCR error: {e}")

def run_edge_feeder(camera_id: int, source_url: str, camera_name: str, mode: str, queue: multiprocessing.Queue, stop_event: multiprocessing.synchronize.Event):
    from pipeline.detection_pipeline import CameraEdgeFeeder
    from sources.rtsp_camera_source import RTSPCameraSource
    import config
    import os

    if mode == "mock":
        from sources.mock_video_source import MockVideoSource
        video_path = os.path.join("data", "mock_videos", "high_res_test.mp4")
        logger.info(f"Using mock video: {os.path.basename(video_path)}")
        source = MockVideoSource(camera_id, video_path, loop=False)
    else:
        source = RTSPCameraSource(camera_id, source_url)

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

    feeder = CameraEdgeFeeder(camera_id, source, detector, queue)
    feeder.ensure_camera_row(camera_name, source_url)
    
    logger.info(f"Edge Feeder {camera_id} starting loop.")
    source.connect()
    frame_idx = 0
    try:
        while not stop_event.is_set():
            frame = source.read_frame()
            if frame is None:
                logger.warning(f"Edge Feeder {camera_id} source ended.")
                try:
                    from db.redis_registry import registry
                    registry.connect()
                    registry.set_camera_active(camera_id, False)
                except Exception as ex:
                    logger.error(f"Failed to unregister camera {camera_id}: {ex}")
                break
                
            frame_idx += 1
            if frame_idx % feeder.sample_interval != 0:
                feeder._finalize_stale_tracks(frame_idx)
                continue
                
            active_tracks = feeder.detector.track(frame)
            if active_tracks:
                logger.debug(f"Edge Feeder {camera_id} found {len(active_tracks)} tracks in frame {frame_idx}")
            for box in active_tracks:
                t_id = box.track_id if box.track_id is not None else id(box)
                bbox = (int(box.x1), int(box.y1), int(box.x2), int(box.y2))
                conf = float(box.confidence)
                
                h, w = frame.shape[:2]
                y1, y2 = max(0, bbox[1]), min(h, bbox[3])
                x1, x2 = max(0, bbox[0]), min(w, bbox[2])
                
                if y2 <= y1 or x2 <= x1:
                    continue
                    
                crop = frame[y1:y2, x1:x2]
                
                is_sharp, sharpness = feeder.track_manager.is_sharp(crop)
                was_blurry = not is_sharp
                feeder.track_manager.update(t_id, crop, bbox, conf, frame_idx, sharpness, was_blurry)
                
            feeder._finalize_stale_tracks(frame_idx)
    finally:
        for ft in feeder.track_manager.flush_all():
            feeder._push_to_queue(ft)
        source.release()

def main():
    multiprocessing.set_start_method('spawn')
    logger.info(f"CCTV Unified MVP (Distributed Queue Mode) starting in '{config.MODE}' mode...")
    
    # 1. Create the Shared OCR Queue
    ocr_queue = multiprocessing.Queue()
    
    # 2. Spin up Master OCR Workers (The GPU Pool)
    ocr_workers = []
    logger.info(f"Spawning {config.OCR_WORKER_COUNT} Master OCR Workers...")
    for _ in range(config.OCR_WORKER_COUNT):
        worker = MasterOcrProcess(run_master_ocr, ocr_queue)
        worker.start()
        ocr_workers.append(worker)
        
    # 3. Create Camera Edge Feeders
    camera_workers = []
    
    if config.is_mock_mode():
        camera_id = 1
        video_dir = Path(config.MOCK_VIDEO_DIR)
        videos = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.webm"))
        if videos:
            video_path = videos[0]
            logger.info(f"Using mock video: {video_path.name}")
            
            from db.dao_cameras import get_camera_by_id, insert_camera, update_camera
            existing = get_camera_by_id(camera_id)
            if not existing:
                insert_camera(name="Gate Camera (mock)", stream_url=str(video_path), status="active")
            elif existing.get("stream_url") != str(video_path):
                update_camera(camera_id, {"stream_url": str(video_path)})
                
        else:
            raise FileNotFoundError(f"No mock videos found in {video_dir}. Add .mp4 or .webm files.")
        
        worker = CameraFeederProcess(run_edge_feeder, camera_id, str(video_path), "Gate Camera (mock)", "mock", ocr_queue)
        camera_workers.append(worker)
    else:
        logger.info("Fetching live camera catalogue from Sentinel API...")
        from clients.sentinel_client import SentinelClient
        from db.dao_cameras import get_camera_by_id, insert_camera
        
        client = SentinelClient(config.SENTINEL_API_HOST)
        cameras = client.get_cameras()
        
        if cameras:
            for idx, cam in enumerate(cameras):
                cam_id = int(cam.get("id", idx + 1))
                stream_url = cam.get("rtsp_url") or cam.get("url")
                name = cam.get("location") or f"Sentinel Camera {cam_id}"
                
                if stream_url:
                    existing = get_camera_by_id(cam_id)
                    if not existing:
                        try:
                            cam_id = insert_camera(name=name, stream_url=stream_url, status="active", location=cam.get("location", ""), city=None, department_id=None)
                        except Exception:
                            continue

                    worker = CameraFeederProcess(run_edge_feeder, cam_id, stream_url, name, "real", ocr_queue)
                    camera_workers.append(worker)

    logger.info(f"Starting API server on port {config.API_PORT}...")
    from api.main import app
    # Inject camera workers into app state so they can be toggled via frontend
    app.state.workers = camera_workers
    app.state.ocr_workers = ocr_workers
    app.state.ocr_queue = ocr_queue
    
    try:
        import os
        if os.path.exists("key.pem") and os.path.exists("cert.pem"):
            logger.info("TLS Certificate found! Starting in HTTPS mode.")
            uvicorn.run("api.main:app", host="127.0.0.1", port=config.API_PORT, reload=False, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
        else:
            logger.info("No TLS certs found. Starting in HTTP mode.")
            uvicorn.run("api.main:app", host="127.0.0.1", port=config.API_PORT, reload=False)
    finally:
        logger.info("Shutting down... stopping all workers.")
        for cw in camera_workers:
            cw.stop()
        for ow in ocr_workers:
            ow.stop()

if __name__ == "__main__":
    main()
