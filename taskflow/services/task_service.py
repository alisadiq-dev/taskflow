"""Task service for managing tasks."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from taskflow.core.config import get_settings
from taskflow.core.exceptions import (
    TaskNotFoundError,
    TaskStateError,
    TaskCancellationError,
)
from taskflow.core.logging import get_logger, LoggerMixin
from taskflow.database.repository import BaseRepository
from taskflow.models.task import Task, TaskResult, TaskStatus, TaskPriority, PRIORITY_QUEUE_MAP
from taskflow.worker.celery_app import get_queue_for_priority, get_priority_value

settings = get_settings()
logger = get_logger(__name__)


class TaskService(LoggerMixin):
    """
    Service for managing tasks.
    
    Provides high-level operations for task creation, execution,
    cancellation, and querying.
    """
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BaseRepository(Task, session)
    
    async def create_task(
        self,
        name: str,
        task_type: str,
        payload: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        tenant_id: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        max_retries: int = 3,
        retry_delay: int = 60,
        timeout: Optional[int] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        workflow_node_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        """
        Create a new task.
        
        Args:
            name: Human-readable task name
            task_type: Type of task (maps to handler)
            payload: Task arguments/payload
            priority: Task priority level
            tenant_id: Optional tenant ID for multi-tenancy
            scheduled_at: Optional time to execute task
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            timeout: Optional task timeout in seconds
            tags: Optional tags for filtering
            metadata: Optional metadata
            workflow_id: Optional workflow ID
            workflow_node_id: Optional workflow node ID
            parent_task_id: Optional parent task ID
            
        Returns:
            Created task instance
        """
        task = await self.repository.create(
            id=str(uuid4()),
            name=name,
            task_type=task_type,
            payload=payload,
            priority=priority,
            queue=PRIORITY_QUEUE_MAP.get(priority, "default"),
            tenant_id=tenant_id,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            tags=tags or [],
            metadata=metadata or {},
            workflow_id=workflow_id,
            workflow_node_id=workflow_node_id,
            parent_task_id=parent_task_id,
            status=TaskStatus.PENDING if scheduled_at else TaskStatus.QUEUED,
        )
        
        # If not scheduled, queue immediately
        if not scheduled_at:
            await self._enqueue_task(task)
        
        self.logger.info(
            "Task created",
            task_id=task.id,
            task_type=task_type,
            priority=priority.value,
        )
        
        return task
    
    async def _enqueue_task(self, task: Task) -> None:
        """Enqueue task to Celery."""
        from taskflow.worker.tasks import execute_task
        from taskflow.core.logging import get_correlation_id
        
        # Submit to Celery
        queue = get_queue_for_priority(task.priority.value)
        priority_value = get_priority_value(task.priority.value)
        
        celery_task = execute_task.apply_async(
            args=[task.id, task.task_type, task.payload],
            kwargs={"correlation_id": get_correlation_id()},
            queue=queue,
            priority=priority_value,
            eta=task.eta,
            task_id=f"taskflow-{task.id}",
        )
        
        # Update with Celery task ID
        await self.repository.update(
            task.id,
            celery_task_id=celery_task.id,
            status=TaskStatus.QUEUED,
        )
        
        self.logger.info(
            "Task enqueued",
            task_id=task.id,
            celery_task_id=celery_task.id,
            queue=queue,
        )
    
    async def get_task(
        self,
        task_id: str,
        tenant_id: Optional[str] = None,
    ) -> Task:
        """
        Get a task by ID.
        
        Args:
            task_id: Task ID
            tenant_id: Optional tenant ID for filtering
            
        Returns:
            Task instance
            
        Raises:
            TaskNotFoundError: If task not found
        """
        if tenant_id:
            task = await self.repository.get_by(
                id=task_id,
                tenant_id=tenant_id,
                load_relations=["result"],
            )
        else:
            task = await self.repository.get(task_id, load_relations=["result"])
        
        if not task:
            raise TaskNotFoundError(task_id)
        
        return task
    
    async def list_tasks(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        task_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        """
        List tasks with filtering.
        
        Args:
            tenant_id: Optional tenant ID filter
            status: Optional status filter
            priority: Optional priority filter
            task_type: Optional task type filter
            tags: Optional tags filter (any match)
            skip: Number of records to skip
            limit: Maximum records to return
            
        Returns:
            List of tasks
        """
        query = select(Task)
        
        if tenant_id:
            query = query.where(Task.tenant_id == tenant_id)
        if status:
            query = query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
        if task_type:
            query = query.where(Task.task_type == task_type)
        if tags:
            # PostgreSQL array overlap operator
            query = query.where(Task.tags.overlap(tags))
        
        query = query.order_by(Task.created_at.desc())
        query = query.offset(skip).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def cancel_task(
        self,
        task_id: str,
        tenant_id: Optional[str] = None,
    ) -> Task:
        """
        Cancel a pending or running task.
        
        Args:
            task_id: Task ID
            tenant_id: Optional tenant ID for authorization
            
        Returns:
            Updated task
            
        Raises:
            TaskNotFoundError: If task not found
            TaskStateError: If task cannot be cancelled
        """
        task = await self.get_task(task_id, tenant_id)
        
        # Check if task can be cancelled
        cancellable_states = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING}
        if task.status not in cancellable_states:
            raise TaskStateError(
                task_id,
                task.status.value,
                [s.value for s in cancellable_states],
            )
        
        # Cancel Celery task if running
        if task.celery_task_id:
            from taskflow.worker.celery_app import celery_app
            celery_app.control.revoke(task.celery_task_id, terminate=True)
        
        # Update status
        updated_task = await self.repository.update(
            task_id,
            status=TaskStatus.CANCELLED,
            completed_at=datetime.now(timezone.utc),
        )
        
        self.logger.info("Task cancelled", task_id=task_id)
        
        return updated_task
    
    async def retry_task(
        self,
        task_id: str,
        tenant_id: Optional[str] = None,
        reset_retries: bool = False,
    ) -> Task:
        """
        Retry a failed task.
        
        Args:
            task_id: Task ID
            tenant_id: Optional tenant ID for authorization
            reset_retries: Reset retry count to 0
            
        Returns:
            Updated task
            
        Raises:
            TaskNotFoundError: If task not found
            TaskStateError: If task cannot be retried
        """
        task = await self.get_task(task_id, tenant_id)
        
        # Check if task can be retried
        retriable_states = {
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.DEAD_LETTER,
            TaskStatus.CANCELLED,
        }
        if task.status not in retriable_states:
            raise TaskStateError(
                task_id,
                task.status.value,
                [s.value for s in retriable_states],
            )
        
        # Reset task state
        update_data = {
            "status": TaskStatus.QUEUED,
            "error_message": None,
            "error_traceback": None,
            "started_at": None,
            "completed_at": None,
            "progress": 0.0,
            "progress_message": None,
        }
        
        if reset_retries:
            update_data["retry_count"] = 0
        
        updated_task = await self.repository.update(task_id, **update_data)
        
        # Re-enqueue
        await self._enqueue_task(updated_task)
        
        self.logger.info("Task retried", task_id=task_id)
        
        return updated_task
    
    async def update_progress(
        self,
        task_id: str,
        progress: float,
        message: Optional[str] = None,
    ) -> None:
        """
        Update task progress.
        
        Args:
            task_id: Task ID
            progress: Progress value (0.0 to 1.0)
            message: Optional progress message
        """
        await self.repository.update(
            task_id,
            progress=min(max(progress, 0.0), 1.0),
            progress_message=message,
        )
    
    async def get_task_stats(
        self,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get task statistics.
        
        Args:
            tenant_id: Optional tenant ID filter
            
        Returns:
            Statistics dictionary
        """
        base_query = select(Task)
        if tenant_id:
            base_query = base_query.where(Task.tenant_id == tenant_id)
        
        # Count by status
        status_counts = {}
        for status in TaskStatus:
            query = select(func.count()).select_from(
                base_query.where(Task.status == status).subquery()
            )
            result = await self.session.execute(query)
            status_counts[status.value] = result.scalar() or 0
        
        # Count by priority
        priority_counts = {}
        for priority in TaskPriority:
            query = select(func.count()).select_from(
                base_query.where(Task.priority == priority).subquery()
            )
            result = await self.session.execute(query)
            priority_counts[priority.value] = result.scalar() or 0
        
        # Average duration for completed tasks
        duration_query = select(
            func.avg(
                func.extract("epoch", Task.completed_at) -
                func.extract("epoch", Task.started_at)
            )
        ).where(
            Task.status == TaskStatus.SUCCESS,
            Task.started_at.isnot(None),
            Task.completed_at.isnot(None),
        )
        if tenant_id:
            duration_query = duration_query.where(Task.tenant_id == tenant_id)
        
        result = await self.session.execute(duration_query)
        avg_duration = result.scalar()
        
        return {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
            "by_priority": priority_counts,
            "average_duration_seconds": round(avg_duration, 2) if avg_duration else None,
        }
    
    async def cleanup_old_tasks(
        self,
        days: int = 30,
        statuses: Optional[list[TaskStatus]] = None,
    ) -> int:
        """
        Delete old completed tasks.
        
        Args:
            days: Delete tasks older than this many days
            statuses: Only delete tasks with these statuses
            
        Returns:
            Number of deleted tasks
        """
        from sqlalchemy import delete
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = delete(Task).where(
            Task.completed_at < cutoff,
        )
        
        if statuses:
            query = query.where(Task.status.in_(statuses))
        else:
            query = query.where(
                Task.status.in_([
                    TaskStatus.SUCCESS,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ])
            )
        
        result = await self.session.execute(query)
        await self.session.commit()
        
        deleted_count = result.rowcount
        self.logger.info(
            "Cleaned up old tasks",
            deleted_count=deleted_count,
            days=days,
        )
        
        return deleted_count
