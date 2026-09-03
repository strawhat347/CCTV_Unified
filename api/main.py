"""
api/main.py — FastAPI app entrypoint (Step 3.5: read-only API skeleton).

Run from the PROJECT ROOT (same convention as pipeline/ingestion_pipeline.py
— everything in this repo is invoked as a module, never as a bare script):

    python -m uvicorn api.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger UI.

CORS is wide open (allow_origins=["*"]) for now since desktop_client/
is a local pywebview/Electron shell talking to localhost — tighten this
before Step 7.5 (auth) or before anything ever touches a real network.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.routes_cameras import router as cameras_router
from api.routes_detections import router as detections_router
from api.routes_alerts import router as alerts_router
from api.routes_streams import router as streams_router, stream_manager
from api.routes_videos import router as videos_router
from api.routes_ai import router as ai_router, copilot
from db.dao_videos import create_videos_table

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api.main")

API_KEY = config.API_KEY

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up — routers mounted: /cameras, /detections, /alerts, /streams")
    create_videos_table()
    # Initialize worker lists on app.state to avoid lost-reference bugs
    if not hasattr(app.state, "workers"):
        app.state.workers = []
    if not hasattr(app.state, "ocr_workers"):
        app.state.ocr_workers = []
    # Ensure ocr_queue exists even if main.py wasn't the entry point
    if not hasattr(app.state, "ocr_queue") or app.state.ocr_queue is None:
        import multiprocessing
        app.state.ocr_queue = multiprocessing.Queue()
        logger.warning("ocr_queue was not initialized by main.py — created a fallback queue")
    yield
    logger.info("API shutting down — stopping workers and stream sources...")
    # Stop pipeline workers before streams
    for w in getattr(app.state, "workers", []):
        w.stop()
    for w in getattr(app.state, "ocr_workers", []):
        w.stop()
    stream_manager.shutdown()
    copilot.unload_model()
    logger.info("API shutdown complete.")


app = FastAPI(
    title="CCTV Unified — Backend API",
    description="Read-only Step 3.5 skeleton wrapping db/dao_cameras.py and db/dao_detections.py.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for anything that isn't already an HTTPException (which FastAPI
    handles separately). Prevents raw tracebacks / file paths / DB error text
    from leaking to clients — logs the real error server-side instead.
    """
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(ExceptionGroup)
async def exception_group_handler(request: Request, exc: ExceptionGroup):
    """
    Python 3.11+ wraps concurrent errors in ExceptionGroup, which doesn't
    inherit from Exception — the generic handler above won't catch it.
    """
    logger.exception("Unhandled ExceptionGroup on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Docs endpoints are only exempt from API-key auth in mock/dev mode (the
# default for this hackathon MVP). In "real" mode they're treated like any
# other route and require the X-API-Key header, same as the rest of the API.
DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}

# NOTE ON MIDDLEWARE ORDER: Starlette treats the *last* middleware added as
# the outermost layer (it sees the request first and the response last), so
# we add these back-to-front relative to how we want them to actually run:
#
#   security headers  (outermost — decorate every response, even 401/429s)
#   └── CORS              (attach CORS headers to every response, incl. short-circuits)
#       └── rate limiting     (throttle even repeated bad-auth requests)
#           └── verify_api_key    (innermost of these — auth check)
#               └── route handlers

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Allow CORS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    # Healthcheck is always open (used for liveness probes with no auth context).
    if request.url.path == "/health":
        return await call_next(request)

    # Docs are only open without a key in mock/dev mode.
    if config.is_mock_mode() and any(request.url.path.startswith(p) for p in DOCS_PATHS):
        return await call_next(request)

    # Streams use query-param auth because browsers can't set headers on
    # <img>/<video> src — verified per-route in api/routes_streams.py.
    if request.url.path.startswith("/streams/"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not api_key or not secrets.compare_digest(api_key, API_KEY):
        logger.warning(f"Unauthorized API request to {request.url.path} from {request.client.host}")
        # Security: Return generic 401 Unauthorized for missing/bad keys
        return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid API Key"})

    return await call_next(request)


# Rate limiting (slowapi) — simple per-client-IP limit as a basic abuse guard.
# Sits outside verify_api_key so repeated bad-key guesses get throttled too.
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Tightened CORS: Only allow local clients (like the desktop client's random pywebview port)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|.*\.trycloudflare\.com|.*\.ngrok.*)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(cameras_router)
app.include_router(detections_router)
app.include_router(alerts_router)
app.include_router(streams_router)
app.include_router(videos_router)
app.include_router(ai_router)

# Mount the crops directory so the frontend can display the raw detection images
os.makedirs("data/crops", exist_ok=True)
app.mount("/crops", StaticFiles(directory="data/crops"), name="crops")

# Mount the mock_videos directory so the frontend can play local videos directly with a native media player
os.makedirs("data/mock_videos", exist_ok=True)
app.mount("/videos", StaticFiles(directory="data/mock_videos"), name="videos")


@app.get("/health", tags=["health"])
def health_check():
    """GET /health — trivial liveness probe, no DB touch."""
    return {"status": "ok"}


@app.get("/system/status", tags=["system"])
@limiter.exempt
def system_status(request: Request):
    """Returns the current status of the backend, including whether pipeline workers are active."""
    workers = getattr(app.state, "workers", [])
    ocr_workers = getattr(app.state, "ocr_workers", [])
    active_cameras = [w.camera_id for w in workers if w.is_alive() and not getattr(w, "is_video", False)]
    active_videos = [w.video_id for w in workers if w.is_alive() and getattr(w, "is_video", False)]
    ocr_active = any(w.is_alive() for w in ocr_workers)
    any_active = ocr_active or len(active_cameras) > 0 or len(active_videos) > 0
    return {"workers_active": any_active, "ocr_active": ocr_active, "worker_count": len(workers), "active_cameras": active_cameras, "active_videos": active_videos}

from pydantic import BaseModel
class ScanToggleRequest(BaseModel):
    scanning: bool

import asyncio

@app.post("/system/scan", tags=["system"])
@limiter.exempt
async def toggle_scan(request: Request, body: ScanToggleRequest):
    """Starts or stops the pipeline workers."""
    workers = getattr(app.state, "workers", [])
    ocr_workers = getattr(app.state, "ocr_workers", [])
    
    if body.scanning:
        # Start OCR workers if not running
        for w in ocr_workers:
            if not w.is_alive():
                logger.info("API: Starting OCR worker")
                w.start()

        # Camera feeders are NOT started here.
        # Use POST /system/scan/{camera_id} to start individual camera feeders.
        
        # Wait for the OCR worker processes to initialise
        await asyncio.sleep(2.5)
        return {"status": "started"}
    else:
        # Stop all workers
        for w in workers:
            w.stop()
        for w in ocr_workers:
            w.stop()
        
        # Wait for processes to safely terminate and flush tracks
        await asyncio.sleep(1.5)
        return {"status": "stopped"}

@app.post("/system/scan/{camera_id}", tags=["system"])
@limiter.exempt
async def toggle_scan_camera(camera_id: int, request: Request, body: ScanToggleRequest):
    """Starts or stops the pipeline worker for a specific camera."""
    from pipeline.multiprocessing_workers import CameraFeederProcess
    from db.dao_cameras import get_camera_by_id
    try:
        from main import run_edge_feeder
    except ImportError:
        import sys, os
        sys.path.append(os.getcwd())
        from main import run_edge_feeder
        
    workers = getattr(app.state, "workers", [])
    ocr_workers = getattr(app.state, "ocr_workers", [])
    ocr_queue = getattr(app.state, "ocr_queue", None)
    
    worker = next((w for w in workers if not getattr(w, "is_video", False) and getattr(w, "camera_id", None) == camera_id), None)
    
    if body.scanning:
        if not worker:
            cam = get_camera_by_id(camera_id)
            if not cam:
                raise HTTPException(status_code=404, detail="Camera not found in database")
            
            stream_url = cam["stream_url"]
            # Assume real mode for existing cameras, unless stream_url is a local file
            mode = "mock" if stream_url.endswith((".mp4", ".webm")) and not stream_url.startswith("http") else "real"
            
            worker = CameraFeederProcess(run_edge_feeder, camera_id, stream_url, cam["name"], mode, ocr_queue)
            workers.append(worker)
            
        # Ensure OCR workers are running
        for ow in ocr_workers:
            if not ow.is_alive():
                logger.info("API: Starting OCR worker")
                ow.start()
                
        if not worker.is_alive():
            logger.info(f"API: Starting worker for Camera {camera_id}")
            worker.start()
            await asyncio.sleep(2.5) # Wait for model load
        return {"status": "started", "camera_id": camera_id}
    else:
        if worker and worker.is_alive():
            logger.info(f"API: Stopping worker for Camera {camera_id}")
            worker.stop()
            await asyncio.sleep(1.5) # Wait for flush
        return {"status": "stopped", "camera_id": camera_id}

@app.post("/system/scan/video/{video_id}", tags=["system"])
@limiter.exempt
async def toggle_scan_video(video_id: int, request: Request, body: ScanToggleRequest):
    from pipeline.multiprocessing_workers import CameraFeederProcess
    from db.dao_videos import get_video_by_id
    try:
        from main import run_edge_feeder
    except ImportError:
        import sys, os
        sys.path.append(os.getcwd())
        from main import run_edge_feeder
    
    workers = getattr(app.state, "workers", [])
    ocr_workers = getattr(app.state, "ocr_workers", [])
    ocr_queue = getattr(app.state, "ocr_queue", None)
    
    worker = next((w for w in workers if getattr(w, "is_video", False) and getattr(w, "video_id", None) == video_id), None)
    
    if body.scanning:
        if not worker:
            video = get_video_by_id(video_id)
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")
            worker = CameraFeederProcess(run_edge_feeder, -video_id, video["filepath"], video["filename"], "mock", ocr_queue)
            worker.is_video = True
            worker.video_id = video_id
            workers.append(worker)
            
        for ow in ocr_workers:
            if not ow.is_alive():
                logger.info("API: Starting OCR worker")
                ow.start()
                
        if not worker.is_alive():
            logger.info(f"API: Starting worker for Video {video_id}")
            worker.start()
            await asyncio.sleep(2.5)
        return {"status": "started", "video_id": video_id}
    else:
        if worker and worker.is_alive():
            logger.info(f"API: Stopping worker for Video {video_id}")
            worker.stop()
            await asyncio.sleep(1.5)
        return {"status": "stopped", "video_id": video_id}
