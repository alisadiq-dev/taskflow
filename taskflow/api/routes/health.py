"""Health check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Kubernetes readiness probe."""
    # Could add checks for database, Redis, etc.
    return HealthResponse(status="ready", version="1.0.0")


@router.get("/live", response_model=HealthResponse)
async def liveness_check() -> HealthResponse:
    """Kubernetes liveness probe."""
    return HealthResponse(status="alive", version="1.0.0")
