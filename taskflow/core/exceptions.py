"""Custom exceptions for TaskFlow."""

from typing import Any, Optional


class TaskFlowError(Exception):
    """Base exception for TaskFlow."""
    
    def __init__(
        self,
        message: str,
        code: str = "TASKFLOW_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class TaskNotFoundError(TaskFlowError):
    """Raised when a task is not found."""
    
    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Task not found: {task_id}",
            code="TASK_NOT_FOUND",
            details={"task_id": task_id},
        )


class TaskAlreadyExistsError(TaskFlowError):
    """Raised when trying to create a task that already exists."""
    
    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Task already exists: {task_id}",
            code="TASK_ALREADY_EXISTS",
            details={"task_id": task_id},
        )


class TaskStateError(TaskFlowError):
    """Raised when a task is in an invalid state for the operation."""
    
    def __init__(self, task_id: str, current_state: str, expected_states: list[str]) -> None:
        super().__init__(
            message=f"Task {task_id} is in state '{current_state}', expected one of: {expected_states}",
            code="TASK_STATE_ERROR",
            details={
                "task_id": task_id,
                "current_state": current_state,
                "expected_states": expected_states,
            },
        )


class TaskCancellationError(TaskFlowError):
    """Raised when task cancellation fails."""
    
    def __init__(self, task_id: str, reason: str) -> None:
        super().__init__(
            message=f"Failed to cancel task {task_id}: {reason}",
            code="TASK_CANCELLATION_ERROR",
            details={"task_id": task_id, "reason": reason},
        )


class ScheduleNotFoundError(TaskFlowError):
    """Raised when a schedule is not found."""
    
    def __init__(self, schedule_id: str) -> None:
        super().__init__(
            message=f"Schedule not found: {schedule_id}",
            code="SCHEDULE_NOT_FOUND",
            details={"schedule_id": schedule_id},
        )


class ScheduleValidationError(TaskFlowError):
    """Raised when schedule validation fails."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="SCHEDULE_VALIDATION_ERROR",
            details=details or {},
        )


class WorkflowNotFoundError(TaskFlowError):
    """Raised when a workflow is not found."""
    
    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            message=f"Workflow not found: {workflow_id}",
            code="WORKFLOW_NOT_FOUND",
            details={"workflow_id": workflow_id},
        )


class WorkflowValidationError(TaskFlowError):
    """Raised when workflow validation fails."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="WORKFLOW_VALIDATION_ERROR",
            details=details or {},
        )


class WorkflowCycleError(TaskFlowError):
    """Raised when a cycle is detected in workflow DAG."""
    
    def __init__(self, workflow_id: str, cycle_path: list[str]) -> None:
        super().__init__(
            message=f"Cycle detected in workflow {workflow_id}",
            code="WORKFLOW_CYCLE_ERROR",
            details={"workflow_id": workflow_id, "cycle_path": cycle_path},
        )


class WorkflowExecutionError(TaskFlowError):
    """Raised when workflow execution fails."""
    
    def __init__(
        self,
        execution_id: str,
        node_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Workflow execution {execution_id} failed: {reason}",
            code="WORKFLOW_EXECUTION_ERROR",
            details={
                "execution_id": execution_id,
                "node_id": node_id,
                "reason": reason,
            },
        )


class WebhookNotFoundError(TaskFlowError):
    """Raised when a webhook is not found."""
    
    def __init__(self, webhook_id: str) -> None:
        super().__init__(
            message=f"Webhook not found: {webhook_id}",
            code="WEBHOOK_NOT_FOUND",
            details={"webhook_id": webhook_id},
        )


class WebhookDeliveryError(TaskFlowError):
    """Raised when webhook delivery fails."""
    
    def __init__(
        self,
        webhook_id: str,
        status_code: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Webhook delivery failed for {webhook_id}: {reason}",
            code="WEBHOOK_DELIVERY_ERROR",
            details={
                "webhook_id": webhook_id,
                "status_code": status_code,
                "reason": reason,
            },
        )


class QueueError(TaskFlowError):
    """Raised when queue operations fail."""
    
    def __init__(self, queue_name: str, operation: str, reason: str) -> None:
        super().__init__(
            message=f"Queue {operation} failed for '{queue_name}': {reason}",
            code="QUEUE_ERROR",
            details={
                "queue_name": queue_name,
                "operation": operation,
                "reason": reason,
            },
        )


class AuthenticationError(TaskFlowError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
        )


class AuthorizationError(TaskFlowError):
    """Raised when authorization fails."""
    
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
        )


class RateLimitError(TaskFlowError):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, limit: int, window: int) -> None:
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window} seconds",
            code="RATE_LIMIT_ERROR",
            details={"limit": limit, "window": window},
        )
