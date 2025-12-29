"""FastAPI routers for TaskFlow API."""

from fastapi import APIRouter

from taskflow.api.routes import tasks, schedules, workflows, webhooks, monitoring, health

api_router = APIRouter()

# Include all route modules
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(health.router, tags=["health"])
