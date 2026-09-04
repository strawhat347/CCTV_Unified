"""
api/main.py — FastAPI app entrypoint (Step 11: Enterprise Security).

Run from the PROJECT ROOT:

    python -m uvicorn api.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger UI.
Use the "Authorize" button to log in with username/password.

Security:
  - All routes are protected by JWT Bearer tokens (OAuth2).
  - Internal pipeline endpoints (/alerts/internal/push, /detections/internal/push)
    are authenticated via the legacy X-API-Key header for backward compatibility
    with the pipeline processes.
  - Swagger docs are open in mock mode for development convenience.
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
from api.routes_auth import router as auth_router
from db.dao_videos import create_videos_table
from db.dao_users import ensure_users_table, get_user_by_username, create_user

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api.main")

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /system/status") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

API_KEY = config.API_KEY


def _seed_admin_user():
    """Create the default admin account on first run if it doesn't exist."""
    from api.auth import hash_password

    admin = get_user_by_username(config.ADMIN_SEED_USERNAME)
    if admin is None:
        hashed = hash_password(config.ADMIN_SEED_PASSWORD)
        create_user(
            username=config.ADMIN_SEED_USERNAME,
            password_hash=hashed,
            role="admin",
        )
        logger.info(
            "Seeded default admin user '%s'. CHANGE THE PASSWORD after first login!",
            config.ADMIN_SEED_USERNAME,
        )
    else:
        logger.info("Admin user '%s' already exists — skipping seed.", config.ADMIN_SEED_USERNAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up — routers mounted: /cameras, /detections, /alerts, /streams, /auth")
    create_videos_table()
    ensure_users_table()
    _seed_admin_user()
    # Initialize worker lists on app.state to avoid lost-reference bugs
    if not hasattr(app.state, "workers"):
        app.state.workers = []
    if not hasattr(app.state, "ocr_workers"):
        app.state.ocr_workers = []
    if not hasattr(app.state, "fast_queue"):
        import multiprocessing
        from pipeline.multiprocessing_workers import MasterOcrProcess
        import config
        try:
            from main import run_master_ocr
        except ImportError:
            import sys, os
            sys.path.append(os.getcwd())
            from main import run_master_ocr
            
        app.state.manager = multiprocessing.Manager()
        app.state.cooldown_cache = app.state.manager.dict()
        app.state.fast_queue = multiprocessing.Queue(maxsize=200)
        app.state.heavy_queue = multiprocessing.Queue(maxsize=200)
        
        # Initialize OCR workers
        for _ in range(2):
            worker = MasterOcrProcess(run_master_ocr, app.state.fast_queue, app.state.cooldown_cache, "fast")
            app.state.ocr_workers.append(worker)
        for _ in range(3):
            worker = MasterOcrProcess(run_master_ocr, app.state.heavy_queue, app.state.cooldown_cache, "heavy")
            app.state.ocr_workers.append(worker)
    yield
    logger.info("API shutting down — stopping stream sources...")
    stream_manager.shutdown()
    copilot.unload_model()
    logger.info("API shutdown complete.")


app = FastAPI(
    title="CCTV Unified — Backend API",
    description="Enterprise-secured CCTV backend with JWT auth, RBAC, and real-time WebSocket alerts.",
    version="2.0.0",
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


# Docs endpoints are only exempt from API-key auth in mock/dev mode (the
# default for this hackathon MVP). In "real" mode they're treated like any
# other route and require the X-API-Key header, same as the rest of the API.
DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}

# Internal pipeline endpoints that still use the legacy X-API-Key auth
# because they are called by backend pipeline processes (not browser clients).
INTERNAL_PATHS = {"/alerts/internal/push", "/detections/internal/push"}

# NOTE ON MIDDLEWARE ORDER: Starlette treats the *last* middleware added as
# the outermost layer (it sees the request first and the response last), so
# we add these back-to-front relative to how we want them to actually run:
#
#   security headers  (outermost — decorate every response, even 401/429s)
#   └── CORS              (attach CORS headers to every response, incl. short-circuits)
#       └── rate limiting     (throttle even repeated bad-auth requests)
#           └── internal_api_key_check    (only for pipeline internal endpoints)
#               └── route handlers (JWT auth handled by FastAPI Depends)

@app.middleware("http")
async def verify_internal_api_key(request: Request, call_next):
    """
    Middleware that ONLY checks X-API-Key for internal pipeline endpoints.
    All other endpoints are secured by JWT via FastAPI's Depends(get_current_user).
    """
    # Allow CORS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    # Healthcheck is always open (used for liveness probes with no auth context).
    if request.url.path == "/health":
        return await call_next(request)

    # Docs are open without auth in mock/dev mode.
    if config.is_mock_mode() and any(request.url.path.startswith(p) for p in DOCS_PATHS):
        return await call_next(request)

    # Auth endpoints must be reachable without prior auth (login, refresh).
    if request.url.path.startswith("/auth/"):
        return await call_next(request)

    # Internal pipeline endpoints: check legacy X-API-Key
    if request.url.path in INTERNAL_PATHS:
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not api_key or not secrets.compare_digest(api_key, API_KEY):
            logger.warning(f"Unauthorized internal API request to {request.url.path} from {request.client.host}")
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid API Key"})

    # All other routes: JWT auth is handled by FastAPI Depends — just pass through.
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
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Prevent browsers from caching sensitive API responses (tokens, user data)
    if request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


app.include_router(auth_router)
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
    
    worker = next((w for w in workers if getattr(w, "camera_id", None) == camera_id and not getattr(w, "is_video", False)), None)
    
    if body.scanning:
        if not worker:
            camera = get_camera_by_id(camera_id)
            if not camera:
                raise HTTPException(status_code=404, detail="Camera not found")
            fast_queue = getattr(app.state, "fast_queue", None)
            heavy_queue = getattr(app.state, "heavy_queue", None)
            if fast_queue and heavy_queue:
                from pipeline.multiprocessing_workers import CameraFeederProcess
                import multiprocessing
                try:
                    from main import run_edge_feeder
                    worker = CameraFeederProcess(run_edge_feeder, camera_id, camera["stream_url"], camera["name"], "real", fast_queue, heavy_queue)
                    app.state.workers.append(worker)
                    worker.start()
                except ImportError:
                    pass
            
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
    
    worker = next((w for w in workers if getattr(w, "camera_id", None) == -video_id and getattr(w, "is_video", False)), None)
    
    if body.scanning:
        if not worker:
            video = get_video_by_id(video_id)
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")
            fast_queue = getattr(app.state, "fast_queue", None)
            heavy_queue = getattr(app.state, "heavy_queue", None)
            if fast_queue and heavy_queue:
                worker = CameraFeederProcess(run_edge_feeder, -video_id, video["filepath"], video["filename"], "mock", fast_queue, heavy_queue)
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

