"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from taskflow.models.task import TaskStatus, TaskPriority
from taskflow.models.schedule import ScheduleType
from taskflow.models.workflow import WorkflowStatus, NodeType


# Task Schemas
class TaskCreate(BaseModel):
    """Schema for creating a task."""
    
    name: str
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    scheduled_at: Optional[datetime] = None
    max_retries: int = 3
    retry_delay: int = 60
    timeout: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Schema for task response."""
    
    id: str
    name: str
    task_type: str
    status: TaskStatus
    priority: TaskPriority
    progress: float
    progress_message: Optional[str]
    celery_task_id: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    tags: list[str]
    metadata: dict[str, Any]
    
    model_config = {"from_attributes": True}


# Schedule Schemas
class ScheduleCreate(BaseModel):
    """Schema for creating a schedule."""
    
    name: str
    task_type: str
    task_name: str
    schedule_type: ScheduleType
    task_payload: dict[str, Any] = Field(default_factory=dict)
    task_priority: TaskPriority = TaskPriority.NORMAL
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    run_date: Optional[datetime] = None
    timezone: str = "UTC"
    max_runs: Optional[int] = None
    expires_at: Optional[datetime] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ScheduleResponse(BaseModel):
    """Schema for schedule response."""
    
    id: str
    name: str
    task_type: str
    schedule_type: ScheduleType
    is_active: bool
    is_paused: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    run_count: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Workflow Schemas
class WorkflowCreate(BaseModel):
    """Schema for creating a workflow."""
    
    name: str
    description: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class WorkflowNodeCreate(BaseModel):
    """Schema for creating a workflow node."""
    
    node_key: str
    name: str
    node_type: NodeType = NodeType.TASK
    task_type: Optional[str] = None
    task_config: dict[str, Any] = Field(default_factory=dict)
    condition_expression: Optional[str] = None
    delay_seconds: Optional[int] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None


class WorkflowEdgeCreate(BaseModel):
    """Schema for creating a workflow edge."""
    
    source_node_key: str
    target_node_key: str
    condition_branch: Optional[str] = None
    data_mapping: dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    """Schema for workflow response."""
    
    id: str
    name: str
    description: Optional[str]
    status: WorkflowStatus
    version: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Webhook Schemas
class WebhookCreate(BaseModel):
    """Schema for creating a webhook."""
    
    name: str
    url: str
    events: list[str]
    secret: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    task_filters: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class WebhookResponse(BaseModel):
    """Schema for webhook response."""
    
    id: str
    name: str
    url: str
    events: list[str]
    is_active: bool
    total_deliveries: int
    successful_deliveries: int
    failed_deliveries: int
    last_delivery_at: Optional[datetime]
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Common Schemas
class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    
    items: list[Any]
    total: int
    skip: int
    limit: int


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    error: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)
