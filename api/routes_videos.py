from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from api.rbac import get_current_user, require_role
from fastapi.responses import FileResponse
import mimetypes
import os
import shutil
import uuid
from db.dao_videos import insert_video, get_all_videos, get_video_by_id, delete_video

router = APIRouter(prefix="/videos", tags=["videos"])

VIDEOS_DIR = os.path.join("data", "offline_videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB

@router.post("/upload")
async def upload_video(file: UploadFile = File(...), user: dict = Depends(require_role(['admin', 'operator']))):
    if not file.filename or not file.filename.endswith(('.mp4', '.webm')):
        raise HTTPException(status_code=400, detail="Only MP4 or WebM files are allowed.")
    
    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{safe_name}"
    filepath = os.path.join(VIDEOS_DIR, unique_filename)
    
    # Stream to disk with size limit
    bytes_written = 0
    with open(filepath, "wb") as buffer:
        while chunk := await file.read(8192):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                buffer.close()
                os.remove(filepath)
                raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.")
            buffer.write(chunk)
            
    # Verify the uploaded video is actually decodable
    import cv2
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        cap.release()
        os.remove(filepath)
        raise HTTPException(status_code=400, detail="Invalid video file: Cannot open file.")
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        os.remove(filepath)
        raise HTTPException(status_code=400, detail="Invalid video file: Cannot decode video frames. Ensure it is a valid MP4 or WebM.")
        
    video_id = insert_video(file.filename, filepath)
    return {"id": video_id, "filename": file.filename, "status": "uploaded"}

@router.get("/list")
def list_videos(user: dict = Depends(require_role(['admin', 'operator', 'auditor']))):
    return get_all_videos()

@router.get("/play/{video_id}")
def play_video(video_id: int, user: dict = Depends(require_role(['admin', 'operator', 'auditor']))):
    video = get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    filepath = video["filepath"]
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video file missing on disk")
    
    # Detect MIME type dynamically
    media_type = mimetypes.guess_type(filepath)[0] or "video/mp4"
    return FileResponse(filepath, media_type=media_type)

from fastapi import Request
import asyncio

@router.delete("/delete/{video_id}")
async def delete_video_route(video_id: int, request: Request, user: dict = Depends(require_role(['admin']))):
    video = get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Stop the worker if it's currently scanning this video
    workers = getattr(request.app.state, "workers", [])
    worker = next((w for w in workers if getattr(w, "is_video", False) and getattr(w, "video_id", None) == video_id), None)
    if worker and worker.is_alive():
        worker.stop()
        await asyncio.sleep(0.5)
        
    filepath = video["filepath"]
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass # Windows might lock it briefly, ignore failure
        
    delete_video(video_id)
    return {"status": "success", "message": "Video deleted"}
