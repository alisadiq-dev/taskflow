"""Task API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from taskflow.api.schemas import TaskCreate, TaskResponse, PaginatedResponse
from taskflow.core.exceptions import TaskNotFoundError, TaskFlowError
from taskflow.database.session import get_async_session
from taskflow.models.task import TaskStatus, TaskPriority
from taskflow.services.task_service import TaskService

router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    session: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """
    Create a new task.
    
    Tasks are queued immediately unless `scheduled_at` is provided.
    """
    service = TaskService(session)
    
    task = await service.create_task(
        name=task_data.name,
        task_type=task_data.task_type,
        payload=task_data.payload,
        priority=task_data.priority,
        scheduled_at=task_data.scheduled_at,
        max_retries=task_data.max_retries,
        retry_delay=task_data.retry_delay,
        timeout=task_data.timeout,
        tags=task_data.tags,
        metadata=task_data.metadata,
    )
    
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """Get a task by ID."""
    service = TaskService(session)
    
    try:
        task = await service.get_task(task_id)
        return TaskResponse.model_validate(task)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    task_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[TaskResponse]:
    """List tasks with optional filtering."""
    service = TaskService(session)
    
    tasks = await service.list_tasks(
        status=status,
        priority=priority,
        task_type=task_type,
        skip=skip,
        limit=limit,
    )
    
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """Cancel a pending or running task."""
    service = TaskService(session)
    
    try:
        task = await service.cancel_task(task_id)
        return TaskResponse.model_validate(task)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except TaskFlowError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str,
    reset_retries: bool = Query(False),
    session: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """Retry a failed task."""
    service = TaskService(session)
    
    try:
        task = await service.retry_task(task_id, reset_retries=reset_retries)
        return TaskResponse.model_validate(task)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except TaskFlowError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/stats", response_model=dict)
async def get_task_stats(
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get task statistics."""
    service = TaskService(session)
    return await service.get_task_stats()
