"""WebSocket handler for real-time task progress updates."""

import json
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from taskflow.core.logging import get_logger
from taskflow.database.redis import get_redis_context

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for task progress updates."""
    
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
    
    async def connect(self, task_id: str, websocket: WebSocket):
        """Connect a client to task updates."""
        await websocket.accept()
        
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        
        self.active_connections[task_id].append(websocket)
        logger.info("WebSocket connected", task_id=task_id)
    
    def disconnect(self, task_id: str, websocket: WebSocket):
        """Disconnect a client."""
        if task_id in self.active_connections:
            self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        
        logger.info("WebSocket disconnected", task_id=task_id)
    
    async def broadcast(self, task_id: str, message: dict):
        """Broadcast message to all clients watching a task."""
        if task_id in self.active_connections:
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


async def task_progress_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for task progress updates.
    
    Clients connect to /ws/tasks/{task_id} to receive real-time
    progress updates for a specific task.
    """
    await manager.connect(task_id, websocket)
    
    try:
        # Subscribe to Redis pub/sub for this task
        async with get_redis_context() as redis:
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"taskflow:progress:{task_id}")
            
            # Keep connection alive and forward messages
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
    
    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)
    except Exception as e:
        logger.error("WebSocket error", task_id=task_id, error=str(e))
        manager.disconnect(task_id, websocket)
