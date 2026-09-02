from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import shutil
import uuid
from db.dao_videos import insert_video, get_all_videos, get_video_by_id, delete_video

router = APIRouter(prefix="/videos", tags=["videos"])

VIDEOS_DIR = os.path.join("data", "offline_videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename.endswith(('.mp4', '.webm')):
        raise HTTPException(status_code=400, detail="Only MP4 or WebM files are allowed.")
    
    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(VIDEOS_DIR, unique_filename)
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    video_id = insert_video(file.filename, filepath)
    return {"id": video_id, "filename": file.filename, "status": "uploaded"}

@router.get("/list")
def list_videos():
    return get_all_videos()

@router.get("/play/{video_id}")
def play_video(video_id: int):
    video = get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    filepath = video["filepath"]
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video file missing on disk")
        
    return FileResponse(filepath, media_type="video/mp4")

@router.delete("/delete/{video_id}")
def delete_video_route(video_id: int):
    video = get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    filepath = video["filepath"]
    if os.path.exists(filepath):
        os.remove(filepath)
        
    delete_video(video_id)
    return {"status": "success", "message": "Video deleted"}
