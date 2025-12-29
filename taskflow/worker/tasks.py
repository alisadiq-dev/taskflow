"""Celery task definitions."""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from sqlalchemy import update

from taskflow.core.config import get_settings
from taskflow.core.logging import get_logger, set_correlation_id
from taskflow.database.session import AsyncSessionLocal
from taskflow.models.task import Task as TaskModel, TaskResult, TaskStatus
from taskflow.worker.celery_app import celery_app

settings = get_settings()
logger = get_logger(__name__)


class TaskFlowTask(Task):
    """
    Base task class with error handling and lifecycle hooks.
    """
    
    abstract = True
    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    
    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Called when task succeeds."""
        logger.info(
            "Task succeeded",
            task_id=task_id,
            result_type=type(retval).__name__,
        )
    
    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called when task fails."""
        logger.error(
            "Task failed",
            task_id=task_id,
            error=str(exc),
            traceback=str(einfo),
        )
    
    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called when task is retried."""
        logger.warning(
            "Task retrying",
            task_id=task_id,
            error=str(exc),
            retry_count=self.request.retries,
        )


def run_async(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=TaskFlowTask,
    name="taskflow.worker.tasks.execute_task",
    acks_late=True,
)
def execute_task(
    self,
    task_db_id: str,
    task_type: str,
    payload: dict[str, Any],
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute a task from the database.
    
    This is the main task executor that:
    1. Updates task status to RUNNING
    2. Executes the task handler
    3. Saves results or handles errors
    4. Publishes progress updates
    
    Args:
        task_db_id: Database task ID
        task_type: Type of task to execute (maps to handler)
        payload: Task payload/arguments
        correlation_id: Request correlation ID for tracing
        
    Returns:
        Task result dictionary
    """
    if correlation_id:
        set_correlation_id(correlation_id)
    
    logger.info(
        "Executing task",
        task_db_id=task_db_id,
        task_type=task_type,
        celery_task_id=self.request.id,
    )
    
    async def _execute():
        async with AsyncSessionLocal() as session:
            # Update status to RUNNING
            await session.execute(
                update(TaskModel)
                .where(TaskModel.id == task_db_id)
                .values(
                    status=TaskStatus.RUNNING,
                    celery_task_id=self.request.id,
                    started_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            
            try:
                # Get task handler
                handler = get_task_handler(task_type)
                if handler is None:
                    raise ValueError(f"Unknown task type: {task_type}")
                
                # Execute with progress callback
                async def update_progress(progress: float, message: Optional[str] = None):
                    await session.execute(
                        update(TaskModel)
                        .where(TaskModel.id == task_db_id)
                        .values(
                            progress=progress,
                            progress_message=message,
                        )
                    )
                    await session.commit()
                    
                    # Publish progress event via Redis
                    from taskflow.database.redis import get_redis_context
                    async with get_redis_context() as redis:
                        import json
                        await redis.publish(
                            f"taskflow:progress:{task_db_id}",
                            json.dumps({
                                "task_id": task_db_id,
                                "progress": progress,
                                "message": message,
                            })
                        )
                
                # Execute handler
                result = await handler(payload, update_progress)
                
                # Save result
                task_result = TaskResult(
                    task_id=task_db_id,
                    result=result if isinstance(result, dict) else {"value": result},
                )
                session.add(task_result)
                
                # Update task status
                await session.execute(
                    update(TaskModel)
                    .where(TaskModel.id == task_db_id)
                    .values(
                        status=TaskStatus.SUCCESS,
                        progress=1.0,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
                
                logger.info(
                    "Task completed successfully",
                    task_db_id=task_db_id,
                    task_type=task_type,
                )
                
                return result if isinstance(result, dict) else {"value": result}
                
            except SoftTimeLimitExceeded:
                await session.execute(
                    update(TaskModel)
                    .where(TaskModel.id == task_db_id)
                    .values(
                        status=TaskStatus.TIMEOUT,
                        error_message="Task exceeded time limit",
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
                raise
                
            except Exception as e:
                error_tb = traceback.format_exc()
                
                # Check if we should retry
                task = await session.get(TaskModel, task_db_id)
                if task and task.retry_count < task.max_retries:
                    await session.execute(
                        update(TaskModel)
                        .where(TaskModel.id == task_db_id)
                        .values(
                            status=TaskStatus.RETRYING,
                            retry_count=TaskModel.retry_count + 1,
                            error_message=str(e),
                            error_traceback=error_tb,
                        )
                    )
                    await session.commit()
                    raise self.retry(exc=e, countdown=task.retry_delay)
                else:
                    # Move to dead letter queue
                    await session.execute(
                        update(TaskModel)
                        .where(TaskModel.id == task_db_id)
                        .values(
                            status=TaskStatus.DEAD_LETTER,
                            error_message=str(e),
                            error_traceback=error_tb,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    
                    # Queue for dead letter processing
                    process_dead_letter.delay(task_db_id)
                    raise
    
    return run_async(_execute())


@celery_app.task(
    bind=True,
    name="taskflow.worker.tasks.process_dead_letter",
    queue="dead_letter",
)
def process_dead_letter(self, task_db_id: str) -> dict[str, Any]:
    """
    Process a task that has been moved to the dead letter queue.
    
    This task handles failed tasks that have exhausted all retries:
    - Logs the failure
    - Sends notifications
    - Stores for manual review
    
    Args:
        task_db_id: Database task ID
        
    Returns:
        Processing result
    """
    logger.warning(
        "Processing dead letter task",
        task_db_id=task_db_id,
    )
    
    async def _process():
        async with AsyncSessionLocal() as session:
            task = await session.get(TaskModel, task_db_id)
            if not task:
                logger.error("Dead letter task not found", task_db_id=task_db_id)
                return {"status": "error", "message": "Task not found"}
            
            # Send webhook notification
            from taskflow.services.webhook_service import WebhookService
            webhook_service = WebhookService(session)
            await webhook_service.trigger_event(
                "task.failed",
                task_id=task_db_id,
                payload={
                    "task_id": task.id,
                    "task_name": task.name,
                    "task_type": task.task_type,
                    "error_message": task.error_message,
                    "retry_count": task.retry_count,
                },
            )
            
            logger.info(
                "Dead letter task processed",
                task_db_id=task_db_id,
                task_name=task.name,
            )
            
            return {
                "status": "processed",
                "task_id": task_db_id,
                "task_name": task.name,
            }
    
    return run_async(_process())


@celery_app.task(
    bind=True,
    base=TaskFlowTask,
    name="taskflow.worker.tasks.send_webhook",
    queue="webhooks",
    max_retries=5,
)
def send_webhook(
    self,
    webhook_id: str,
    delivery_id: str,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    secret: Optional[str] = None,
) -> dict[str, Any]:
    """
    Send a webhook notification.
    
    Args:
        webhook_id: Webhook configuration ID
        delivery_id: Delivery attempt ID
        url: Webhook endpoint URL
        payload: Webhook payload
        headers: HTTP headers
        secret: Optional secret for signing
        
    Returns:
        Delivery result
    """
    import hashlib
    import hmac
    import json
    import httpx
    from datetime import datetime, timezone
    
    logger.info(
        "Sending webhook",
        webhook_id=webhook_id,
        delivery_id=delivery_id,
        url=url,
    )
    
    async def _send():
        async with AsyncSessionLocal() as session:
            from taskflow.models.webhook import WebhookDelivery, DeliveryStatus
            
            # Prepare request
            body = json.dumps(payload)
            request_headers = {
                "Content-Type": "application/json",
                "User-Agent": "TaskFlow/1.0",
                "X-TaskFlow-Delivery-ID": delivery_id,
                "X-TaskFlow-Event": payload.get("event", "unknown"),
                **headers,
            }
            
            # Sign payload if secret provided
            if secret:
                signature = hmac.new(
                    secret.encode(),
                    body.encode(),
                    hashlib.sha256,
                ).hexdigest()
                request_headers["X-TaskFlow-Signature"] = f"sha256={signature}"
            
            # Update delivery status
            await session.execute(
                update(WebhookDelivery)
                .where(WebhookDelivery.id == delivery_id)
                .values(
                    status=DeliveryStatus.PENDING,
                    request_headers=request_headers,
                    request_body=body,
                    sent_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            
            # Send request
            start_time = datetime.now(timezone.utc)
            try:
                async with httpx.AsyncClient(timeout=settings.webhook_timeout) as client:
                    response = await client.post(
                        url,
                        content=body,
                        headers=request_headers,
                    )
                
                end_time = datetime.now(timezone.utc)
                duration_ms = int((end_time - start_time).total_seconds() * 1000)
                
                # Update delivery with response
                status = (
                    DeliveryStatus.SUCCESS
                    if 200 <= response.status_code < 300
                    else DeliveryStatus.FAILED
                )
                
                await session.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.id == delivery_id)
                    .values(
                        status=status,
                        response_status_code=response.status_code,
                        response_headers=dict(response.headers),
                        response_body=response.text[:10000],  # Limit response body
                        response_at=end_time,
                        duration_ms=duration_ms,
                    )
                )
                await session.commit()
                
                if status == DeliveryStatus.FAILED:
                    raise Exception(f"Webhook returned {response.status_code}")
                
                return {
                    "status": "success",
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
                
            except Exception as e:
                end_time = datetime.now(timezone.utc)
                duration_ms = int((end_time - start_time).total_seconds() * 1000)
                
                await session.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.id == delivery_id)
                    .values(
                        status=DeliveryStatus.FAILED,
                        error_message=str(e),
                        response_at=end_time,
                        duration_ms=duration_ms,
                        attempt=self.request.retries + 1,
                    )
                )
                await session.commit()
                
                raise self.retry(exc=e, countdown=settings.webhook_retry_delay)
    
    return run_async(_send())


# Task Handler Registry
_task_handlers: dict[str, Any] = {}


def register_task_handler(task_type: str):
    """Decorator to register a task handler."""
    def decorator(func):
        _task_handlers[task_type] = func
        return func
    return decorator


def get_task_handler(task_type: str):
    """Get handler for task type."""
    return _task_handlers.get(task_type)


# Built-in task handlers
@register_task_handler("echo")
async def echo_handler(payload: dict, update_progress) -> dict:
    """Simple echo task for testing."""
    await update_progress(0.5, "Processing...")
    import asyncio
    await asyncio.sleep(1)
    await update_progress(1.0, "Complete")
    return {"echo": payload}


@register_task_handler("http_request")
async def http_request_handler(payload: dict, update_progress) -> dict:
    """Make an HTTP request."""
    import httpx
    
    await update_progress(0.1, "Preparing request...")
    
    method = payload.get("method", "GET").upper()
    url = payload["url"]
    headers = payload.get("headers", {})
    body = payload.get("body")
    timeout = payload.get("timeout", 30)
    
    await update_progress(0.3, "Sending request...")
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
        )
    
    await update_progress(1.0, "Complete")
    
    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text[:10000],
    }


@register_task_handler("compute")
async def compute_handler(payload: dict, update_progress) -> dict:
    """CPU-intensive computation task."""
    import asyncio
    
    operation = payload.get("operation", "fibonacci")
    n = payload.get("n", 10)
    
    await update_progress(0.1, f"Starting {operation}...")
    
    if operation == "fibonacci":
        def fib(n):
            if n <= 1:
                return n
            return fib(n - 1) + fib(n - 2)
        
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fib, min(n, 35))
        
    elif operation == "factorial":
        import math
        result = math.factorial(min(n, 1000))
        
    else:
        result = n * 2
    
    await update_progress(1.0, "Complete")
    
    return {"operation": operation, "input": n, "result": result}


@register_task_handler("email")
async def email_handler(payload: dict, update_progress) -> dict:
    """Send email task (mock implementation)."""
    await update_progress(0.5, "Sending email...")
    
    # Mock email sending
    import asyncio
    await asyncio.sleep(0.5)
    
    await update_progress(1.0, "Email sent")
    
    return {
        "to": payload.get("to"),
        "subject": payload.get("subject"),
        "status": "sent",
    }
