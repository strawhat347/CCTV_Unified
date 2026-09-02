"""
api/ws_alerts.py - WebSocket manager for real-time alert broadcasts.
"""
from typing import List

from fastapi import WebSocket

MAX_WS_CONNECTIONS = 50


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> bool:
        """
        Accept and register a new connection. Returns False (and closes the
        socket with 'server busy') if we're already at MAX_WS_CONNECTIONS,
        without ever having accepted it — callers must not read/write to the
        websocket if this returns False.
        """
        if len(self.active_connections) >= MAX_WS_CONNECTIONS:
            await websocket.close(code=1013, reason="Server busy")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_message(self, data: dict):
        # We need to copy the list because connections might be removed during iteration
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
