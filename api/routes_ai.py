"""
api/routes_ai.py - AI Copilot Endpoints (Step 10)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging
from alerting.ai_copilot import AICopilot
from db.dao_alerts import get_all_alerts
from db.dao_detections import get_recent_detections
from db.dao_cameras import get_all_cameras

logger = logging.getLogger("api.routes_ai")

router = APIRouter(prefix="/ai", tags=["ai"])
copilot = AICopilot(model_name="qwen2.5:1.5b")

class AIQueryRequest(BaseModel):
    query: str = Field(..., description="The natural language query to ask the AI.")
    context_limit: Optional[int] = Field(15, description="How many recent alerts and detections to include in the context.")

class AIQueryResponse(BaseModel):
    query: str
    response: str

class AIStatusResponse(BaseModel):
    status: str

@router.get("/status", response_model=AIStatusResponse)
def check_ai_status():
    """
    Check if the Ollama AI service is running on the host machine.
    """
    is_online = copilot.check_status()
    return AIStatusResponse(status="online" if is_online else "offline")

@router.post("/query", response_model=AIQueryResponse)
def query_ai_copilot(req: AIQueryRequest):
    """
    Query the local AI Copilot using natural language.
    Retrieves the most recent alerts and detections and passes them to the LLM.
    """
    try:
        # Fetch the context from the database
        recent_alerts = get_all_alerts(limit=req.context_limit)
        recent_detections = get_recent_detections(limit=req.context_limit)
        all_cameras = get_all_cameras()
        
        # Query the local Ollama LLM
        answer = copilot.query_alerts(
            user_prompt=req.query, 
            context_alerts=recent_alerts, 
            context_detections=recent_detections,
            context_cameras=all_cameras
        )
        
        # Temporarily log AI responses to the main server console for debugging
        logger.info(f"[AI Query] User: '{req.query}' | Copilot: '{answer}'")
        
        return AIQueryResponse(query=req.query, response=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
