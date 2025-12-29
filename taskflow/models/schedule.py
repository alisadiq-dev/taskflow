"""Schedule model for recurring and scheduled tasks."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from taskflow.models.base import Base, TimestampMixin
from taskflow.models.task import TaskPriority


class ScheduleType(str, Enum):
    """Type of schedule."""
    
    CRON = "cron"           # Cron expression (e.g., "0 0 * * *")
    INTERVAL = "interval"    # Fixed interval (e.g., every 5 minutes)
    DATE = "date"           # One-time at specific date
    SOLAR = "solar"         # Based on sunrise/sunset


class Schedule(Base, TimestampMixin):
    """
    Represents a scheduled or recurring task.
    
    Supports cron expressions, intervals, one-time scheduling,
    and solar-based scheduling.
    """
    
    __tablename__ = "schedules"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Schedule identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Multi-tenancy
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    
    # Task configuration
    task_type: Mapped[str] = mapped_column(String(255), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    task_priority: Mapped[TaskPriority] = mapped_column(
        String(50),
        default=TaskPriority.NORMAL,
        nullable=False,
    )
    task_queue: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    
    # Schedule type and configuration
    schedule_type: Mapped[ScheduleType] = mapped_column(
        String(50),
        default=ScheduleType.CRON,
        nullable=False,
    )
    
    # Cron expression (for CRON type)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Interval configuration (for INTERVAL type)
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # One-time date (for DATE type)
    run_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Solar configuration (for SOLAR type)
    solar_event: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # Timezone
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    
    # Schedule state
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Execution tracking
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Limits
    max_runs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Error handling
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_consecutive_failures: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    
    # APScheduler job ID
    apscheduler_job_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    
    # Metadata
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    @property
    def is_expired(self) -> bool:
        """Check if schedule has expired."""
        if self.expires_at and datetime.now(self.expires_at.tzinfo) > self.expires_at:
            return True
        if self.max_runs and self.run_count >= self.max_runs:
            return True
        return False
    
    @property
    def should_run(self) -> bool:
        """Check if schedule should run."""
        return (
            self.is_active
            and not self.is_paused
            and not self.is_expired
            and self.consecutive_failures < self.max_consecutive_failures
        )
    
    def __repr__(self) -> str:
        return f"<Schedule(id={self.id}, name={self.name}, type={self.schedule_type})>"
