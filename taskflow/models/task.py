"""Task model for the distributed task processing system."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskflow.models.base import Base, TimestampMixin


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    TIMEOUT = "timeout"
    DEAD_LETTER = "dead_letter"


class TaskPriority(str, Enum):
    """Task priority levels."""
    
    CRITICAL = "critical"  # Highest priority, processed immediately
    HIGH = "high"          # High priority queue
    NORMAL = "normal"      # Default priority
    LOW = "low"            # Background tasks


# Priority to Celery queue mapping
PRIORITY_QUEUE_MAP = {
    TaskPriority.CRITICAL: "critical",
    TaskPriority.HIGH: "high",
    TaskPriority.NORMAL: "default",
    TaskPriority.LOW: "low",
}

# Priority numeric values for sorting
PRIORITY_VALUES = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 3,
    TaskPriority.NORMAL: 6,
    TaskPriority.LOW: 9,
}


class Task(Base, TimestampMixin):
    """
    Represents a task in the distributed processing system.
    
    Tasks can be submitted for immediate execution or scheduled for later.
    They support priorities, retries, dependencies, and progress tracking.
    """
    
    __tablename__ = "tasks"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Task identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Multi-tenancy support
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    
    # Celery task ID
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )
    
    # Status and priority
    status: Mapped[TaskStatus] = mapped_column(
        String(50),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        String(50),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True,
    )
    
    # Task payload
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    
    # Execution metadata
    queue: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    
    # Progress tracking (0.0 to 1.0)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    progress_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Retry configuration
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, nullable=False)  # seconds
    
    # Timeout configuration
    timeout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    soft_timeout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    
    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    eta: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Execution timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Workflow support
    workflow_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workflow_node_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    parent_task_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Metadata
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Relationships
    result: Mapped[Optional["TaskResult"]] = relationship(
        "TaskResult",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )
    child_tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="parent_task",
        foreign_keys="Task.parent_task_id",
    )
    parent_task: Mapped[Optional["Task"]] = relationship(
        "Task",
        back_populates="child_tasks",
        remote_side="Task.id",
        foreign_keys="Task.parent_task_id",
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index("ix_tasks_status_priority", "status", "priority"),
        Index("ix_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_tasks_scheduled", "scheduled_at", "status"),
        Index("ix_tasks_workflow", "workflow_id", "workflow_node_id"),
    )
    
    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in {
            TaskStatus.SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.DEAD_LETTER,
        }
    
    @property
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return (
            self.status in {TaskStatus.FAILED, TaskStatus.TIMEOUT}
            and self.retry_count < self.max_retries
        )
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def __repr__(self) -> str:
        return f"<Task(id={self.id}, name={self.name}, status={self.status})>"


class TaskResult(Base, TimestampMixin):
    """
    Stores the result of a completed task.
    
    Separated from Task to keep the main table lean and allow
    for larger result payloads.
    """
    
    __tablename__ = "task_results"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    
    # Result data
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    result_type: Mapped[str] = mapped_column(String(50), default="json", nullable=False)
    
    # For binary/large results, store reference
    result_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    result_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationship
    task: Mapped["Task"] = relationship("Task", back_populates="result")
    
    def __repr__(self) -> str:
        return f"<TaskResult(id={self.id}, task_id={self.task_id})>"
