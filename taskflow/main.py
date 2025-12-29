"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from taskflow.api import api_router
from taskflow.core.config import get_settings
from taskflow.core.exceptions import TaskFlowError
from taskflow.core.logging import configure_logging, set_correlation_id
from taskflow.database.session import init_db, close_db
from taskflow.database.redis import close_redis
from taskflow.services.schedule_service import start_scheduler, stop_scheduler

settings = get_settings()

# Configure logging
configure_logging(
    level=settings.log_level,
    format=settings.log_format,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    if settings.scheduler_enabled:
        await start_scheduler()
    
    yield
    
    # Shutdown
    if settings.scheduler_enabled:
        await stop_scheduler()
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Distributed Task Processing System",
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_url=settings.openapi_url,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to requests."""
    correlation_id = request.headers.get(
        settings.log_correlation_id_header,
        None,
    )
    set_correlation_id(correlation_id)
    
    response = await call_next(request)
    response.headers[settings.log_correlation_id_header] = correlation_id or ""
    return response


@app.exception_handler(TaskFlowError)
async def taskflow_exception_handler(request: Request, exc: TaskFlowError):
    """Handle TaskFlow exceptions."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )


# Include API router
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": settings.docs_url,
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "taskflow.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
